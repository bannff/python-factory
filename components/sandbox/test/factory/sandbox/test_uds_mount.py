"""Tests for the workload UDS bind-mount helper."""

from __future__ import annotations

import shutil
import socket
import tempfile
from pathlib import Path

import pytest


from factory.sandbox.runtime.adapters import uds_mount


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
    "wl-1\tExited (0) 1 minute ago\t"
    "factory.sandbox=true,factory.workload=workload:launch-1\n"
    "plain\tDead\tfactory.sandbox=true\n"
)


def test_sweep_orphans_returns_reaped_list_with_policy_ids() -> None:
    def fake_run(cmd, timeout=30):  # noqa: ANN001
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, _PS_LINES, ""
        return 0, "", ""

    reaped = uds_mount.sweep_orphans(fake_run)
    assert reaped == [
        {"container_id": "wl-1", "policy_id": "workload:launch-1", "reason": "exited"},
        {"container_id": "plain", "policy_id": None, "reason": "dead"},
    ]


def test_sweep_orphans_reads_labels_before_removal() -> None:
    """CRITICAL: labels must be read (ps) BEFORE rm -f, else they vanish."""
    calls: list[list[str]] = []

    def fake_run(cmd, timeout=30):  # noqa: ANN001
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-a"]:
            return 0, _PS_LINES, ""
        return 0, "", ""

    uds_mount.sweep_orphans(fake_run)
    ps_idx = next(i for i, c in enumerate(calls) if c[:3] == ["docker", "ps", "-a"])
    rm_idx = next(i for i, c in enumerate(calls) if c[:3] == ["docker", "rm", "-f"])
    assert ps_idx < rm_idx, "labels/status read must precede rm -f"
    assert ["docker", "rm", "-f", "wl-1"] in calls
    assert ["docker", "rm", "-f", "plain"] in calls
