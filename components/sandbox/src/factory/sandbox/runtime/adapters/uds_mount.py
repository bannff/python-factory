"""Bind-mount a per-launch workload UDS into a sandbox container.

The trusted host (Workflow) creates a per-launch Unix socket for the scoped,
bearer-free MCP proxy; Sandbox bind-mounts it into the container at the
canonical path and forces ``MCP_PROXY_SOCKET`` to match so the two can never
drift. No token/credential is ever mounted — the container dials the socket and
Permissions authorizes upstream. Container removal unmounts the bind; the
orphan sweep reaps crashed/exited labeled containers.
"""
from __future__ import annotations

import stat
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
_SWEEP_FORMAT = "{{.Names}}\t{{.Status}}\t{{.Labels}}"


def _reason_from_status(status: str) -> str:
    """Map a docker status string to the reap-reason enum."""
    return "dead" if "dead" in status.lower() else "exited"


def collect_reapable(run: _RunFn, label: str) -> list[dict[str, Any]]:
    """List exited/dead labeled containers with their workload policy id.

    CRITICAL: called BEFORE ``docker rm -f`` — removal erases labels, so the
    reaper must capture ``factory.workload`` (and the reap reason) first.
    Reuses ``discovery._parse_labels`` for label parsing (no duplication).
    """
    from ..discovery import _parse_labels

    code, stdout, _ = run([
        "docker", "ps", "-a", "--filter", f"label={label}",
        "--filter", "status=exited", "--filter", "status=dead",
        "--format", _SWEEP_FORMAT,
    ])
    if code != 0:
        return []
    reaped: list[dict[str, Any]] = []
    for line in stdout.strip().splitlines():
        parts = line.split("\t")
        name = parts[0] if parts else ""
        if not name:
            continue
        status = parts[1] if len(parts) > 1 else ""
        labels = _parse_labels(parts[2] if len(parts) > 2 else "")
        reaped.append({
            "container_id": name,
            "policy_id": labels.get(_WORKLOAD_LABEL),
            "reason": _reason_from_status(status),
        })
    return reaped


def sweep_orphans(
    run: _RunFn, label: str = "factory.sandbox=true",
) -> list[dict[str, Any]]:
    """Reap exited/dead labeled containers; return the reaped list.

    Ordering matters: collect labels+reason BEFORE ``docker rm -f`` (removal
    erases labels). Returns ``[{container_id, policy_id, reason}]`` — policy_id
    is None for unlabeled (non-workload) orphans.
    """
    reaped = collect_reapable(run, label)
    for item in reaped:
        run(["docker", "rm", "-f", item["container_id"]], timeout=10)
    return reaped


__all__ = [
    "CANONICAL_PROXY_SOCKET", "build_mount_args", "collect_reapable",
    "proxy_env", "sweep_orphans", "validate_socket",
]
