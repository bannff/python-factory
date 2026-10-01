"""Bind-mount a per-launch workload UDS into a sandbox container.

The trusted host (Workflow) creates a per-launch Unix socket for the scoped,
bearer-free MCP proxy; Sandbox bind-mounts it into the container at the
canonical path and forces ``MCP_PROXY_SOCKET`` to match so the two can never
drift. No token/credential is ever mounted — the container dials the socket and
Permissions authorizes upstream. Container removal unmounts the bind; the
orphan sweep reaps crashed/exited labeled containers.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

CANONICAL_PROXY_SOCKET = "/run/companion-x/mcp.sock"

_RunFn = Callable[..., tuple[int, str, str]]


def validate_socket(host_path: str) -> None:
    """Fail loud unless ``host_path`` exists and is a Unix socket."""
    try:
        mode = Path(host_path).stat().st_mode
    except OSError as exc:
        raise ValueError(f"workload proxy socket not found: {host_path}") from exc
    if not stat.S_ISSOCK(mode):
        raise ValueError(f"workload proxy path is not a socket: {host_path}")


def build_mount_args(config: dict[str, Any]) -> list[str]:
    """Build ``docker run -v`` args for generic mounts + the workload UDS."""
    args: list[str] = []
    for mount in config.get("mounts", []) or []:
        suffix = ":ro" if mount.get("read_only") else ""
        args.extend(["-v", f"{mount['source']}:{mount['target']}{suffix}"])
    socket = config.get("proxy_socket")
    if socket:
        validate_socket(socket)
        args.extend(["-v", f"{socket}:{CANONICAL_PROXY_SOCKET}"])
    return args


def proxy_env(config: dict[str, Any]) -> dict[str, str]:
    """Env forced by the mount so ``MCP_PROXY_SOCKET`` always matches target."""
    if not config.get("proxy_socket"):
        return {}
    return {"MCP_PROXY_SOCKET": CANONICAL_PROXY_SOCKET}


_WORKLOAD_LABEL = "factory.workload"
_SWEEP_FORMAT = "{{.ID}}\t{{.Status}}\t{{.Labels}}"
_SECRET_EVIDENCE_HOLD_SECONDS = 600
_EMPTY_NETWORK_GRACE_SECONDS = 120
_FULL_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
_OWNED_NETWORK = re.compile(r"^factory-sandbox-[a-z0-9-]+$")
_RECHECK_FORMAT = (
    "{{.Id}}\t{{.State.Status}}\t{{.State.FinishedAt}}\t"
    "{{.State.StartedAt}}\t{{json .Config.Labels}}"
)


def _reason_from_status(status: str) -> str:
    """Map a docker status string to the reap-reason enum."""
    return "dead" if "dead" in status.lower() else "exited"


def _age_seconds(raw_timestamp: str, now: datetime) -> float | None:
    """Reject missing, future, or unzoned Docker timestamps."""
    try:
        observed = datetime.fromisoformat(raw_timestamp.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    age = (now - observed).total_seconds()
    return age if age >= 0 else None


def _recheck_candidate(
    run: _RunFn, candidate: dict[str, Any], now: datetime,
) -> dict[str, Any] | None:
    """Inspect authoritative state and structured labels while lock is held."""
    container_id = candidate["container_id"]
    code, output, _ = run([
        "docker", "inspect", "--format", _RECHECK_FORMAT, container_id,
    ])
    if code != 0:
        return None
    parts = output.strip().split("\t", 4)
    if len(parts) != 5 or parts[0] != container_id:
        return None
    _, state, finished_at, started_at, raw_labels = parts
    try:
        labels = json.loads(raw_labels)
    except (TypeError, ValueError):
        return None
    if not isinstance(labels, dict) or labels.get("factory.sandbox") != "true":
        return None
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in labels.items()):
        return None
    secret = labels.get("factory.sandbox.secret_output_suppressed") == "true"
    if candidate["reason"] == "timeout":
        raw_timeout = labels.get("factory.sandbox.timeout_seconds", "")
        if state != "running" or not secret or not raw_timeout.isdecimal():
            return None
        timeout_seconds = int(raw_timeout)
        age = _age_seconds(started_at, now)
        if not 60 <= timeout_seconds <= 86400 or age is None or age < timeout_seconds:
            return None
        reason = "timeout"
    else:
        if state not in {"exited", "dead"}:
            return None
        if secret:
            age = _age_seconds(finished_at, now)
            if age is None or age < _SECRET_EVIDENCE_HOLD_SECONDS:
                return None
        elif labels.get("factory.sandbox.secret_output_suppressed") not in (
            None, "false",
        ):
            return None
        reason = state
    return {
        "container_id": container_id,
        "policy_id": labels.get(_WORKLOAD_LABEL),
        "reason": reason,
        "network_name": labels.get("factory.sandbox.peer_network_name"),
    }


def collect_reapable(
    run: _RunFn, label: str, *, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """List exited/dead labeled containers with their workload policy id.

    CRITICAL: called BEFORE ``docker rm -f`` — removal erases labels, so the
    reaper must capture ``factory.workload`` (and the reap reason) first.
    Reuses ``discovery._parse_labels`` for label parsing (no duplication).
    """
    from ..discovery import _parse_labels

    code, stdout, _ = run([
        "docker", "ps", "-a", "--no-trunc", "--filter", f"label={label}",
        "--filter", "status=exited", "--filter", "status=dead",
        "--format", _SWEEP_FORMAT,
    ])
    if code != 0:
        return []
    reaped: list[dict[str, Any]] = []
    for line in stdout.strip().splitlines():
        parts = line.split("\t")
        name = parts[0] if parts else ""
        if not _FULL_CONTAINER_ID.fullmatch(name):
            continue
        status = parts[1] if len(parts) > 1 else ""
        labels = _parse_labels(parts[2] if len(parts) > 2 else "")
        candidate = {
            "container_id": name,
            "policy_id": labels.get(_WORKLOAD_LABEL),
            "reason": _reason_from_status(status),
        }
        if network_name := labels.get("factory.sandbox.peer_network_name"):
            candidate["network_name"] = network_name
        reaped.append(candidate)
    return reaped


def _collect_timed_out_secret(
    run: _RunFn, label: str, *, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Select only running secret containers with a verified elapsed timeout."""
    from ..discovery import _parse_labels

    code, stdout, _ = run([
        "docker", "ps", "-a", "--no-trunc", "--filter", f"label={label}",
        "--filter", "label=factory.sandbox.secret_output_suppressed=true",
        "--filter", "status=running", "--format", _SWEEP_FORMAT,
    ])
    if code != 0:
        return []
    candidates: list[dict[str, Any]] = []
    for line in stdout.strip().splitlines():
        parts = line.split("\t")
        container_id = parts[0] if parts else ""
        if not _FULL_CONTAINER_ID.fullmatch(container_id):
            continue
        labels = _parse_labels(parts[2] if len(parts) > 2 else "")
        candidate = {
            "container_id": container_id,
            "policy_id": labels.get(_WORKLOAD_LABEL),
            "reason": "timeout",
        }
        if network_name := labels.get("factory.sandbox.peer_network_name"):
            candidate["network_name"] = network_name
        candidates.append(candidate)
    return candidates


@contextmanager
def _collector_lock(container_id: str):
    """Hold the collector's per-container advisory lock while mutating Docker.

    A missing lock file is created but never unlinked: removing a lock file
    would allow two processes to lock different inodes for the same container.
    Any uncertain lock state prevents removal.
    """
    root = Path(os.environ.get("SANDBOX_TMP_ROOT", "/tmp/factory-sandbox"))
    directory = root / "collector-locks"
    fd = None
    acquired = False
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        directory_stat = directory.lstat()
        if not stat.S_ISDIR(directory_stat.st_mode) or (
            directory_stat.st_uid != os.getuid()
            or stat.S_IMODE(directory_stat.st_mode) & 0o077
        ):
            raise PermissionError("Collector lock directory is untrusted")
        fd = os.open(
            directory / f"{container_id}.lock",
            os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode) or (
            file_stat.st_uid != os.getuid()
            or stat.S_IMODE(file_stat.st_mode) & 0o077
        ):
            raise PermissionError("Collector lock file is untrusted")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            acquired = True
    except OSError:
        pass
    try:
        yield acquired
    finally:
        if fd is not None:
            if acquired:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _remove_empty_owned_network(run: _RunFn, network_name: str) -> None:
    """Docker arbitrates a remove race after ownership and emptiness checks."""
    if not _OWNED_NETWORK.fullmatch(network_name):
        return
    code, stdout, _ = run([
        "docker", "network", "inspect", "--format",
        '{{ index .Labels "factory.sandbox.owner" }}|{{json .Containers}}',
        network_name,
    ])
    if code != 0:
        return
    owner, _, attached_json = stdout.strip().partition("|")
    try:
        attached = json.loads(attached_json)
    except (TypeError, ValueError):
        return
    if owner == "python-factory" and attached in (None, {}):
        run(["docker", "network", "rm", network_name], timeout=10)


def _retry_empty_owned_networks(run: _RunFn, now: datetime) -> None:
    """Retry cleanup of bridges orphaned by a prior transient Docker error."""
    code, stdout, _ = run([
        "docker", "network", "ls", "--filter",
        "label=factory.sandbox.owner=python-factory", "--format", "{{.Name}}",
    ])
    if code != 0:
        return
    for network_name in stdout.splitlines():
        if not _OWNED_NETWORK.fullmatch(network_name):
            continue
        code, output, _ = run([
            "docker", "network", "inspect", "--format",
            '{{ index .Labels "factory.sandbox.owner" }}|{{json .Containers}}|{{.Created}}',
            network_name,
        ])
        if code != 0:
            continue
        owner, separator, rest = output.strip().partition("|")
        attached_json, separator2, created_at = rest.rpartition("|")
        if owner != "python-factory" or not separator or not separator2:
            continue
        try:
            attached = json.loads(attached_json)
        except (TypeError, ValueError):
            continue
        age = _age_seconds(created_at, now)
        if attached not in (None, {}) or age is None or age < _EMPTY_NETWORK_GRACE_SECONDS:
            continue
        _remove_empty_owned_network(run, network_name)


def sweep_orphans(
    run: _RunFn, label: str = "factory.sandbox=true", *, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Reap exited/dead labeled containers; return the reaped list.

    Ordering matters: collect labels+reason BEFORE ``docker rm -f`` (removal
    erases labels). Returns ``[{container_id, policy_id, reason}]`` — policy_id
    is None for unlabeled (non-workload) orphans.
    """
    reaped: list[dict[str, Any]] = []
    candidates = collect_reapable(run, label, now=now)
    candidates.extend(_collect_timed_out_secret(run, label, now=now))
    clock = now or datetime.now(timezone.utc)
    for candidate in candidates:
        with _collector_lock(candidate["container_id"]) as acquired:
            if not acquired:
                continue
            verified = _recheck_candidate(run, candidate, clock)
            if verified is None:
                continue
            code, _, _ = run(
                ["docker", "rm", "-f", candidate["container_id"]], timeout=10,
            )
            if code != 0:
                continue
            network_name = verified.get("network_name")
            if network_name:
                _remove_empty_owned_network(run, network_name)
            reaped.append({key: verified[key] for key in (
                "container_id", "policy_id", "reason",
            )})
    _retry_empty_owned_networks(run, clock)
    return reaped


__all__ = [
    "CANONICAL_PROXY_SOCKET", "build_mount_args", "collect_reapable",
    "proxy_env", "sweep_orphans", "validate_socket",
]
