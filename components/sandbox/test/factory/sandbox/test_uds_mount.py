"""Tests for the workload UDS bind-mount helper."""

from __future__ import annotations

import shutil
import socket
import tempfile
import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


from factory.sandbox.runtime.adapters import uds_mount


def _inspect_state(
    container_id: str, *, status: str = "exited",
    finished: str = "2026-09-30T10:00:00Z",
    started: str = "2026-09-30T09:00:00Z",
    labels: dict[str, str] | None = None,
) -> str:
    return "\t".join((
        container_id, status, finished, started,
        json.dumps(labels if labels is not None else {"factory.sandbox": "true"}),
    ))


@pytest.fixture
def short_tmp():
    # macOS AF_UNIX paths cap at ~104 chars; pytest tmp_path is far too long.
    directory = tempfile.mkdtemp(dir="/tmp")
    try:
        yield Path(directory)
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def _make_socket(directory: Path) -> str:
    sock_path = str(directory / "mcp.sock")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    server.listen(1)
    return sock_path


def test_validate_socket_accepts_real_socket(short_tmp: Path) -> None:
    uds_mount.validate_socket(_make_socket(short_tmp))  # no raise


def test_validate_socket_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not found"):
        uds_mount.validate_socket(str(tmp_path / "nope.sock"))


def test_validate_socket_rejects_regular_file(tmp_path: Path) -> None:
    regular = tmp_path / "plain.txt"
    regular.write_text("not a socket")
    with pytest.raises(ValueError, match="not a socket"):
        uds_mount.validate_socket(str(regular))


def test_build_mount_args_proxy_socket(short_tmp: Path) -> None:
    sock = _make_socket(short_tmp)
    args = uds_mount.build_mount_args({"proxy_socket": sock})
    assert args == ["-v", f"{sock}:{uds_mount.CANONICAL_PROXY_SOCKET}"]


def test_build_mount_args_generic_mounts_and_readonly() -> None:
    args = uds_mount.build_mount_args({
        "mounts": [
            {"source": "/host/a", "target": "/ctr/a"},
            {"source": "/host/b", "target": "/ctr/b", "read_only": True},
        ],
    })
    assert args == ["-v", "/host/a:/ctr/a", "-v", "/host/b:/ctr/b:ro"]


def test_build_mount_args_missing_socket_fails_loud() -> None:
    with pytest.raises(ValueError, match="not found"):
        uds_mount.build_mount_args({"proxy_socket": "/does/not/exist.sock"})


def test_proxy_env_forces_canonical_target(short_tmp: Path) -> None:
    sock = _make_socket(short_tmp)
    assert uds_mount.proxy_env({"proxy_socket": sock}) == {
        "MCP_PROXY_SOCKET": uds_mount.CANONICAL_PROXY_SOCKET,
    }
    assert uds_mount.proxy_env({}) == {}


_PS_LINES = (
    f"{'a' * 64}\tExited (0) 1 minute ago\t"
    "factory.sandbox=true,factory.workload=workload:launch-1\n"
    f"{'b' * 64}\tDead\tfactory.sandbox=true\n"
)


def test_sweep_orphans_returns_reaped_list_with_policy_ids() -> None:
    def fake_run(cmd, timeout=30):  # noqa: ANN001
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, _PS_LINES, ""
        if cmd[:2] == ["docker", "inspect"]:
            labels = {"factory.sandbox": "true"}
            if cmd[-1] == "a" * 64:
                labels["factory.workload"] = "workload:launch-1"
            return 0, _inspect_state(
                cmd[-1], status="exited" if cmd[-1] == "a" * 64 else "dead",
                labels=labels,
            ), ""
        return 0, "", ""

    reaped = uds_mount.sweep_orphans(fake_run)
    assert reaped == [
        {"container_id": "a" * 64, "policy_id": "workload:launch-1", "reason": "exited"},
        {"container_id": "b" * 64, "policy_id": None, "reason": "dead"},
    ]


def test_sweep_orphans_reads_labels_before_removal() -> None:
    """CRITICAL: labels must be read (ps) BEFORE rm -f, else they vanish."""
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, _PS_LINES, ""
        if cmd[:2] == ["docker", "inspect"]:
            labels = {"factory.sandbox": "true"}
            if cmd[-1] == "a" * 64:
                labels["factory.workload"] = "workload:launch-1"
            return 0, _inspect_state(cmd[-1], labels=labels), ""
        return 0, "", ""

    uds_mount.sweep_orphans(fake_run)
    ps_idx = next(i for i, c in enumerate(calls) if c[:3] == ["docker", "ps", "-a"])
    rm_idx = next(i for i, c in enumerate(calls) if c[:3] == ["docker", "rm", "-f"])
    assert ps_idx < rm_idx, "labels/status read must precede rm -f"
    assert ["docker", "rm", "-f", "a" * 64] in calls
    assert ["docker", "rm", "-f", "b" * 64] in calls


def test_secret_evidence_container_is_retained_briefly_then_reaped() -> None:
    ps = (
        f"{'c' * 64}\tExited (0) 1 minute ago\t"
        "factory.sandbox=true,factory.sandbox.secret_output_suppressed=true\n"
    )
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, ps, ""
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(
                "c" * 64, finished="2026-09-30T12:00:00Z",
                labels={
                    "factory.sandbox": "true",
                    "factory.sandbox.secret_output_suppressed": "true",
                },
            ), ""
        return 0, "", ""

    now = datetime(2026, 9, 30, 12, 5, tzinfo=timezone.utc)
    assert uds_mount.sweep_orphans(fake_run, now=now) == []
    assert ["docker", "rm", "-f", "c" * 64] not in calls

    later = datetime(2026, 9, 30, 12, 11, tzinfo=timezone.utc)
    assert uds_mount.sweep_orphans(fake_run, now=later) == [
        {"container_id": "c" * 64, "policy_id": None, "reason": "exited"}
    ]
    assert ["docker", "rm", "-f", "c" * 64] in calls


@pytest.mark.parametrize("inspect_code,finished_at", [
    (1, "2026-09-30T10:00:00Z"),
    (0, "not-a-timestamp"),
])
def test_secret_evidence_hold_skips_when_exit_time_unverified(
    inspect_code: int, finished_at: str,
) -> None:
    ps = (
        f"{'c' * 64}\tExited (0) 1 minute ago\t"
        "factory.sandbox=true,factory.sandbox.secret_output_suppressed=true\n"
    )

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, ps, ""
        if cmd[:2] == ["docker", "inspect"]:
            return inspect_code, _inspect_state(
                "c" * 64, finished=finished_at,
                labels={
                    "factory.sandbox": "true",
                    "factory.sandbox.secret_output_suppressed": "true",
                },
            ), "inspect unavailable" if inspect_code else ""
        return 0, "", ""

    assert uds_mount.sweep_orphans(fake_run) == []


def test_sweeper_rechecks_state_under_lock_before_removal() -> None:
    container_id = "3" * 64
    ps = f"{container_id}\tExited (0) 20 minutes ago\tfactory.sandbox=true\n"
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return (0, "", "") if "status=running" in cmd else (0, ps, "")
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(container_id, status="running"), ""
        return 0, "", ""

    assert uds_mount.sweep_orphans(fake_run) == []
    assert ["docker", "rm", "-f", container_id] not in calls


def test_sweeper_rechecks_exact_full_id_under_lock() -> None:
    container_id = "6" * 64
    ps = f"{container_id}\tDead\tfactory.sandbox=true\n"
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return (0, "", "") if "status=running" in cmd else (0, ps, "")
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state("7" * 64, status="dead"), ""
        return 0, "", ""

    assert uds_mount.sweep_orphans(fake_run) == []
    assert ["docker", "rm", "-f", container_id] not in calls


def test_sweeper_rechecks_timeout_after_restart_under_lock() -> None:
    container_id = "4" * 64
    labels = {
        "factory.sandbox": "true",
        "factory.sandbox.secret_output_suppressed": "true",
        "factory.sandbox.timeout_seconds": "3600",
    }
    ps = f"{container_id}\tUp 2 hours\t" + ",".join(
        f"{key}={value}" for key, value in labels.items()
    ) + "\n"
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return (0, ps, "") if "status=running" in cmd else (0, "", "")
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(
                container_id, status="running", started="2026-09-30T11:59:00Z",
                labels=labels,
            ), ""
        return 0, "", ""

    assert uds_mount.sweep_orphans(
        fake_run, now=datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
    ) == []
    assert ["docker", "rm", "-f", container_id] not in calls


def test_sweeper_ignores_flattened_labels_for_secret_hold() -> None:
    container_id = "5" * 64
    ps = (
        f"{container_id}\tExited (0) 20 minutes ago\t"
        "factory.sandbox=true,factory.workload=foo,"
        "factory.sandbox.secret_output_suppressed=false\n"
    )
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return (0, "", "") if "status=running" in cmd else (0, ps, "")
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(
                container_id, finished="2026-09-30T11:59:00Z",
                labels={
                    "factory.sandbox": "true",
                    "factory.workload": "foo,factory.sandbox.secret_output_suppressed=false",
                    "factory.sandbox.secret_output_suppressed": "true",
                },
            ), ""
        return 0, "", ""

    assert uds_mount.sweep_orphans(
        fake_run, now=datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
    ) == []
    assert ["docker", "rm", "-f", container_id] not in calls


def test_sweeper_retries_stale_owned_network_without_container() -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, "", ""
        if cmd[:3] == ["docker", "network", "ls"]:
            return 0, "factory-sandbox-lab\n", ""
        if cmd[:3] == ["docker", "network", "inspect"]:
            if "{{.Created}}" in cmd[4]:
                return 0, "python-factory|{}|2026-09-30T10:00:00Z", ""
            return 0, "python-factory|{}", ""
        return 0, "", ""

    assert uds_mount.sweep_orphans(
        fake_run, now=datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
    ) == []
    assert ["docker", "network", "rm", "factory-sandbox-lab"] in calls


@pytest.mark.parametrize("state", [
    "python-factory|{}|2026-09-30T11:59:30Z",
    'python-factory|{"attached":{}}|2026-09-30T10:00:00Z',
    "other|{}|2026-09-30T10:00:00Z",
])
def test_sweeper_preserves_recent_occupied_or_foreign_network(state: str) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, "", ""
        if cmd[:3] == ["docker", "network", "ls"]:
            return 0, "factory-sandbox-lab\n", ""
        if cmd[:3] == ["docker", "network", "inspect"]:
            return 0, state, ""
        return 0, "", ""

    uds_mount.sweep_orphans(
        fake_run, now=datetime(2026, 9, 30, 12, tzinfo=timezone.utc),
    )
    assert ["docker", "network", "rm", "factory-sandbox-lab"] not in calls


def test_sweeper_skips_collector_lock_then_reaps_after_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path))
    container_id = "d" * 64
    ps = f"{container_id}\tExited (0) 20 minutes ago\tfactory.sandbox=true\n"
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, ps, ""
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(container_id), ""
        return 0, "", ""

    lock_dir = tmp_path / "collector-locks"
    lock_dir.mkdir(mode=0o700)
    lock_file = lock_dir / f"{container_id}.lock"
    lock_file.touch(mode=0o600)
    with lock_file.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert uds_mount.sweep_orphans(fake_run) == []
        assert ["docker", "rm", "-f", container_id] not in calls
        fcntl.flock(handle, fcntl.LOCK_UN)

    assert uds_mount.sweep_orphans(fake_run) == [
        {"container_id": container_id, "policy_id": None, "reason": "exited"}
    ]
    assert lock_file.exists()


@pytest.mark.parametrize("containers_json", ["{}", "null"])
def test_sweeper_removes_only_empty_owned_peer_network_after_reap(
    containers_json: str,
) -> None:
    container_id = "e" * 64
    ps = (
        f"{container_id}\tExited (0) 20 minutes ago\t"
        "factory.sandbox=true,factory.sandbox.peer_network_name=factory-sandbox-lab\n"
    )
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, ps, ""
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(container_id, labels={
                "factory.sandbox": "true",
                "factory.sandbox.peer_network_name": "factory-sandbox-lab",
            }), ""
        if cmd[:3] == ["docker", "network", "inspect"]:
            return 0, f"python-factory|{containers_json}", ""
        return 0, "", ""

    uds_mount.sweep_orphans(fake_run)
    assert ["docker", "network", "rm", "factory-sandbox-lab"] in calls
    assert calls.index(["docker", "rm", "-f", container_id]) < calls.index(
        ["docker", "network", "rm", "factory-sandbox-lab"]
    )


@pytest.mark.parametrize("network_state", ["someone-else|{}", "python-factory|{\"x\":{}}"])
def test_sweeper_preserves_non_owned_or_occupied_network(network_state: str) -> None:
    container_id = "e" * 64
    ps = (
        f"{container_id}\tDead\t"
        "factory.sandbox=true,factory.sandbox.peer_network_name=factory-sandbox-lab\n"
    )
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, ps, ""
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(container_id, status="dead", labels={
                "factory.sandbox": "true",
                "factory.sandbox.peer_network_name": "factory-sandbox-lab",
            }), ""
        if cmd[:3] == ["docker", "network", "inspect"]:
            return 0, network_state, ""
        return 0, "", ""

    uds_mount.sweep_orphans(fake_run)
    assert ["docker", "network", "rm", "factory-sandbox-lab"] not in calls


def test_sweeper_does_not_report_failed_removal() -> None:
    container_id = "f" * 64

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, f"{container_id}\tDead\tfactory.sandbox=true\n", ""
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(container_id, status="dead"), ""
        return 1, "", "removal failed"

    assert uds_mount.sweep_orphans(fake_run) == []


def test_sweeper_reaps_secret_running_past_labeled_timeout() -> None:
    container_id = "1" * 64
    ps = (
        f"{container_id}\tUp 2 hours\t"
        "factory.sandbox=true,factory.sandbox.secret_output_suppressed=true,"
        "factory.sandbox.timeout_seconds=3600\n"
    )
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return (0, ps, "") if "status=running" in cmd else (0, "", "")
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(
                container_id, status="running", started="2026-09-30T10:00:00Z",
                labels={
                    "factory.sandbox": "true",
                    "factory.sandbox.secret_output_suppressed": "true",
                    "factory.sandbox.timeout_seconds": "3600",
                },
            ), ""
        return 0, "", ""

    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    assert uds_mount.sweep_orphans(fake_run, now=now) == [
        {"container_id": container_id, "policy_id": None, "reason": "timeout"}
    ]
    assert ["docker", "rm", "-f", container_id] in calls


@pytest.mark.parametrize("timeout_label,started_at", [
    ("", "2026-09-30T10:00:00Z"),
    ("invalid", "2026-09-30T10:00:00Z"),
    ("86401", "2026-09-30T10:00:00Z"),
    ("3600", "unknown"),
    ("3600", "2026-09-30T11:30:00Z"),
])
def test_sweeper_preserves_running_secret_without_verified_expiry(
    timeout_label: str, started_at: str,
) -> None:
    container_id = "2" * 64
    timeout_part = (
        f",factory.sandbox.timeout_seconds={timeout_label}" if timeout_label else ""
    )
    ps = (
        f"{container_id}\tUp 2 hours\t"
        f"factory.sandbox=true,factory.sandbox.secret_output_suppressed=true{timeout_part}\n"
    )
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return (0, ps, "") if "status=running" in cmd else (0, "", "")
        if cmd[:2] == ["docker", "inspect"]:
            return 0, _inspect_state(
                container_id, status="running", started=started_at,
                labels={
                    "factory.sandbox": "true",
                    "factory.sandbox.secret_output_suppressed": "true",
                    **({"factory.sandbox.timeout_seconds": timeout_label} if timeout_label else {}),
                },
            ), ""
        return 0, "", ""

    now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
    assert uds_mount.sweep_orphans(fake_run, now=now) == []
    assert ["docker", "rm", "-f", container_id] not in calls
