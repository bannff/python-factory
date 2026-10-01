"""Contracts and Docker lifecycle for separate Sandbox mesh peers."""
from __future__ import annotations

import asyncio
import hashlib
import json
import multiprocessing
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from factory.sandbox.mcp.models import SandboxProvisionRequest
from factory.sandbox.runtime.adapters import docker_adapter
from factory.sandbox.runtime.adapters.mock import MockAdapter
from factory.sandbox.runtime.models import SandboxConfig
from factory.sandbox.runtime.peer_network import PeerNetworkSpec
from factory.sandbox.runtime.profiles import SandboxProfile
from factory.sandbox.runtime.provision_context import build_provision_context
from factory.sandbox.runtime.runtime import SandboxRuntime
from pydantic import ValidationError


def _hold_peer_network_lock(lock_dir: str, acquired, release) -> None:
    docker_adapter._PEER_NETWORK_LOCK_DIR = Path(lock_dir)
    with docker_adapter._peer_network_provision_lock("cross-process-mesh"):
        acquired.set()
        if not release.wait(timeout=10):
            raise TimeoutError("Parent did not release the peer-network lock")


@pytest.mark.parametrize("data", [
    {"network_id": "../host", "alias": "peer-a", "port": 1234},
    {"network_id": "Mesh", "alias": "peer-a", "port": 1234},
    {"network_id": "mesh", "alias": "Peer-A", "port": 1234},
    {"network_id": "mesh", "alias": "peer-a;id", "port": 1234},
    {"network_id": "mesh", "alias": "peer-a", "port": 65536},
    {"network_id": "mesh", "alias": "peer-a", "port": 0},
    {"network_id": "mesh", "alias": "peer-a", "port": "1234"},
    {"network_id": "mesh", "alias": "peer-a", "port": True},
    {"network_id": "mesh", "alias": "peer-a", "port": 1234, "internal": "true"},
    {"network_id": "mesh", "alias": "peer-a", "port": 1234, "extra": True},
])
def test_peer_network_rejects_invalid_boundary_values(data: dict) -> None:
    with pytest.raises(ValidationError):
        PeerNetworkSpec.model_validate(data)


def test_profile_accepts_mesh_and_legacy_profile_unchanged() -> None:
    legacy = SandboxProfile(name="plain", image="alpine:3.20")
    mesh = SandboxProfile(
        name="mesh", image="alpine:3.20",
        peer_network={"network_id": "factory-test", "alias": "peer-a", "port": 4321},
    )
    assert legacy.peer_network is None
    assert mesh.peer_network.endpoint == "peer-a:4321"


def test_profile_provision_context_exposes_endpoint_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(tmp_path))
    (tmp_path / "mesh.yaml").write_text(
        "image: alpine:3.20\n"
        "peer_network:\n"
        "  network_id: factory-test\n"
        "  alias: peer-a\n"
        "  port: 4321\n"
        "  internal: true\n"
    )
    config, metadata, _ = build_provision_context(SandboxConfig(), "mesh")
    assert config["peer_network"] == {
        "network_id": "factory-test", "alias": "peer-a", "port": 4321,
        "internal": True,
    }
    assert metadata["peer_network"]["endpoint"] == "peer-a:4321"
    assert metadata["peer_network"]["internal"] is True


def test_internal_profile_network_rejects_host_port_mapping(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(tmp_path))
    (tmp_path / "mesh.yaml").write_text(
        "image: alpine:3.20\n"
        "ports: {'8080': '80'}\n"
        "peer_network:\n"
        "  network_id: factory-test\n"
        "  alias: peer-a\n"
        "  port: 4321\n"
        "  internal: true\n"
    )
    with pytest.raises(ValueError, match="cannot publish profile ports"):
        build_provision_context(SandboxConfig(), "mesh")


def test_mcp_provision_boundary_accepts_peer_and_requires_profile() -> None:
    request = SandboxProvisionRequest.model_validate({
        "profile": "edge-lab",
        "peer_network": {"network_id": "mesh-a", "alias": "edge-peer-b", "port": 24225},
    })
    assert request.peer_network.endpoint == "edge-peer-b:24225"
    with pytest.raises(ValidationError):
        SandboxProvisionRequest.model_validate({
            "peer_network": {"network_id": "mesh-a", "alias": "edge-peer-b", "port": 24225},
        })


@pytest.mark.asyncio
async def test_invalid_mesh_is_rejected_before_container_replacement(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        return 0, "", ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(ValidationError):
        await docker_adapter.DockerAdapter().provision({
            "container_name": "old-peer", "replace_existing": True,
            "peer_network": {
                "network_id": "bad/name", "alias": "peer-a", "port": 1234,
            },
        })
    assert calls == []


@pytest.mark.asyncio
async def test_internal_network_rejects_host_ports_before_docker_mutation(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        return 0, "", ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(ValueError, match="cannot publish ports to the host"):
        await docker_adapter.DockerAdapter().provision({
            "container_name": "offline-peer", "replace_existing": True,
            "ports": {"8080": "80"},
            "peer_network": {
                "network_id": "offline-mesh", "alias": "offline-peer",
                "port": 24225, "internal": True,
            },
        })
    assert calls == []


@pytest.mark.asyncio
async def test_network_name_collision_does_not_replace_container(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        if command[:3] == ["docker", "network", "inspect"]:
            return 0, "external-owner|false", ""
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(RuntimeError, match="not Sandbox-owned"):
        await docker_adapter.DockerAdapter().provision({
            "container_name": "existing-peer", "replace_existing": True,
            "peer_network": {
                "network_id": "mesh-a", "alias": "peer-a", "port": 24225,
            },
        })
    assert len(calls) == 1
    assert calls[0][:3] == ["docker", "network", "inspect"]


@pytest.mark.asyncio
async def test_existing_bridge_must_match_requested_internal_mode(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        if command[:3] == ["docker", "network", "inspect"]:
            return 0, "python-factory|false", ""
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(RuntimeError, match="different internal mode"):
        await docker_adapter.DockerAdapter().provision({
            "container_name": "offline-peer", "replace_existing": True,
            "peer_network": {
                "network_id": "offline-mesh", "alias": "offline-peer",
                "port": 24225, "internal": True,
            },
        })
    assert len(calls) == 1
    assert calls[0][:3] == ["docker", "network", "inspect"]


@pytest.mark.asyncio
async def test_duplicate_alias_is_rejected_before_replacing_peer(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        if command[:3] == ["docker", "network", "inspect"]:
            if "{{json .Containers}}" in command:
                return 0, json.dumps({"other-id": {"Name": "other-peer"}}), ""
            return 0, "python-factory|true", ""
        if command[:2] == ["docker", "inspect"]:
            return 0, json.dumps({
                "factory-sandbox-offline-mesh": {
                    "Aliases": ["other-peer", "offline-peer"],
                },
            }), ""
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(ValueError, match="already attached to another container"):
        await docker_adapter.DockerAdapter().provision({
            "container_name": "replacement-peer", "replace_existing": True,
            "peer_network": {
                "network_id": "offline-mesh", "alias": "offline-peer",
                "port": 24225, "internal": True,
            },
        })
    assert not any(command[:3] == ["docker", "rm", "-f"] for command in calls)
    assert not any(command[:2] == ["docker", "run"] for command in calls)


def test_concurrent_provision_cannot_claim_same_peer_alias(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        docker_adapter, "_PEER_NETWORK_LOCK_DIR", tmp_path / "peer-locks",
    )
    first_run_started = threading.Event()
    release_first_run = threading.Event()
    second_started = threading.Event()
    calls_lock = threading.Lock()
    calls: list[list[str]] = []
    attached_names: list[str] = []

    def fake_run(command: list[str], timeout: int = 30):
        with calls_lock:
            calls.append(command)
        if command[:3] == ["docker", "network", "inspect"]:
            if "{{json .Containers}}" in command:
                return 0, json.dumps({
                    name: {"Name": name} for name in attached_names
                }), ""
            return 0, "python-factory|false", ""
        if command[:3] == ["docker", "container", "inspect"]:
            return 1, "", "not found"
        if command[:2] == ["docker", "inspect"]:
            return 0, json.dumps({
                "factory-sandbox-mesh": {"Aliases": ["shared-peer"]},
            }), ""
        if command[:2] == ["docker", "run"]:
            name = command[command.index("--name") + 1]
            if name == "peer-one":
                first_run_started.set()
                assert release_first_run.wait(timeout=2)
            with calls_lock:
                attached_names.append(name)
            return 0, f"{name}-container-id\n", ""
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)

    def provision(name: str) -> tuple[str, ValueError | None]:
        if name == "peer-two":
            second_started.set()
        try:
            result = asyncio.run(docker_adapter.DockerAdapter().provision({
                "image": "alpine:3.20", "container_name": name,
                "replace_existing": False,
                "peer_network": {
                    "network_id": "mesh", "alias": "shared-peer", "port": 4321,
                },
            }))
            return result, None
        except ValueError as error:
            return name, error

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(provision, "peer-one")
        assert first_run_started.wait(timeout=2)
        second = executor.submit(provision, "peer-two")
        assert second_started.wait(timeout=2)
        time.sleep(0.05)
        with calls_lock:
            assert sum(call[:2] == ["docker", "run"] for call in calls) == 1
        release_first_run.set()
        first_result = first.result(timeout=2)
        second_result = second.result(timeout=2)

    assert first_result == ("peer-one", None)
    assert second_result[0] == "peer-two"
    assert isinstance(second_result[1], ValueError)
    assert "already attached to another container" in str(second_result[1])
    assert attached_names == ["peer-one"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX flock assertion")
def test_peer_network_lock_is_held_across_processes(tmp_path) -> None:
    import fcntl

    context = multiprocessing.get_context("fork")
    acquired = context.Event()
    release = context.Event()
    lock_dir = tmp_path / "cross-process-locks"
    process = context.Process(
        target=_hold_peer_network_lock,
        args=(str(lock_dir), acquired, release),
    )
    process.start()
    descriptor = None
    try:
        assert acquired.wait(timeout=5)
        lock_name = hashlib.sha256(b"cross-process-mesh").hexdigest() + ".lock"
        descriptor = os.open(lock_dir / lock_name, os.O_CREAT | os.O_RDWR, 0o600)
        with pytest.raises(BlockingIOError):
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        release.set()
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    assert process.exitcode == 0


def test_windows_peer_lock_retries_contention_without_short_timeout(tmp_path, monkeypatch) -> None:
    import errno
    import sys
    import time as time_module
    from types import SimpleNamespace

    attempts = 0

    def locking(_descriptor: int, mode: int, length: int) -> None:
        nonlocal attempts
        assert mode == 1
        assert length == 1
        attempts += 1
        if attempts < 4:
            raise OSError(errno.EACCES, "lock is held")

    sleeps: list[float] = []
    monkeypatch.setitem(
        sys.modules, "msvcrt", SimpleNamespace(LK_NBLCK=1, locking=locking),
    )
    monkeypatch.setattr(time_module, "sleep", sleeps.append)
    lock_path = tmp_path / "windows-lock"
    with lock_path.open("w+b") as lock_file:
        docker_adapter._acquire_windows_peer_network_lock(lock_file.fileno())

    assert attempts == 4
    assert sleeps == [0.1, 0.1, 0.1]


@pytest.mark.asyncio
async def test_replacing_same_container_can_reuse_its_alias(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        if command[:3] == ["docker", "network", "inspect"]:
            if "{{json .Containers}}" in command:
                return 0, json.dumps({"same-id": {"Name": "same-peer"}}), ""
            return 0, "python-factory|true", ""
        if command[:3] == ["docker", "rm", "-f"]:
            return 0, "", ""
        if command[:2] == ["docker", "run"]:
            return 0, "new-container-id\n", ""
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    env_id = await docker_adapter.DockerAdapter().provision({
        "container_name": "same-peer", "replace_existing": True,
        "peer_network": {
            "network_id": "offline-mesh", "alias": "offline-peer",
            "port": 24225, "internal": True,
        },
    })
    assert env_id == "same-peer"
    assert any(command[:3] == ["docker", "rm", "-f"] for command in calls)
    assert any(command[:2] == ["docker", "run"] for command in calls)


@pytest.mark.asyncio
async def test_peer_network_requires_docker_adapter(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(tmp_path))
    (tmp_path / "mesh.yaml").write_text("image: alpine:3.20\n")
    with pytest.raises(ValueError, match="peer networks require the Docker adapter"):
        await SandboxRuntime(adapter=MockAdapter()).provision(
            profile="mesh",
            peer_network=PeerNetworkSpec(
                network_id="mesh-a", alias="peer-a", port=24225,
            ),
        )


@pytest.mark.asyncio
async def test_provision_attaches_peer_and_status_exposes_stable_endpoint(monkeypatch) -> None:
    calls: list[list[str]] = []
    labels = {
        "factory.sandbox.peer_network_id": "factory-test",
        "factory.sandbox.peer_alias": "peer-a",
        "factory.sandbox.peer_port": "4321",
        "factory.sandbox.peer_internal": "false",
    }

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        if command[:3] == ["docker", "container", "inspect"]:
            return 1, "", "not found"
        if command[:3] == ["docker", "network", "inspect"]:
            if "{{json .Containers}}" in command:
                return 0, "{}", ""
            return 1, "", "not found"
        if command[:3] == ["docker", "network", "create"]:
            return 0, "network-id\n", ""
        if command[:2] == ["docker", "run"]:
            return 0, "container-id\n", ""
        if command[0:2] == ["docker", "inspect"] and "{{json .Config.Labels}}" in command:
            return 0, json.dumps(labels), ""
        if command[0:2] == ["docker", "inspect"]:
            return 0, "running\n", ""
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    adapter = docker_adapter.DockerAdapter()
    env_id = await adapter.provision({
        "image": "alpine:3.20", "container_name": "peer-a",
        "replace_existing": False,
        "peer_network": {"network_id": "factory-test", "alias": "peer-a", "port": 4321},
    })
    run = next(command for command in calls if command[:2] == ["docker", "run"])
    assert run[run.index("--network") + 1] == "factory-sandbox-factory-test"
    assert run[run.index("--network-alias") + 1] == "peer-a"
    network_create = next(
        command for command in calls if command[:3] == ["docker", "network", "create"]
    )
    assert "--internal" not in network_create
    assert run[run.index("--label") + 1] == "factory.sandbox=true"
    status = await adapter.get_status(env_id)
    assert status["peer_network"]["endpoint"] == "peer-a:4321"
    assert status["peer_network"]["internal"] is False


@pytest.mark.asyncio
async def test_internal_peer_network_uses_internal_bridge_and_reports_mode(monkeypatch) -> None:
    calls: list[list[str]] = []
    labels = {
        "factory.sandbox.peer_network_id": "offline-mesh",
        "factory.sandbox.peer_alias": "offline-a",
        "factory.sandbox.peer_port": "24225",
        "factory.sandbox.peer_internal": "true",
    }

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        if command[:3] == ["docker", "container", "inspect"]:
            return 1, "", "not found"
        if command[:3] == ["docker", "network", "inspect"]:
            if "{{json .Containers}}" in command:
                return 0, "{}", ""
            return 1, "", "not found"
        if command[:3] == ["docker", "network", "create"]:
            return 0, "network-id\n", ""
        if command[:2] == ["docker", "run"]:
            return 0, "container-id\n", ""
        if command[0:2] == ["docker", "inspect"] and "{{json .Config.Labels}}" in command:
            return 0, json.dumps(labels), ""
        if command[0:2] == ["docker", "inspect"]:
            return 0, "running\n", ""
        raise AssertionError(f"Unexpected Docker command: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    adapter = docker_adapter.DockerAdapter()
    env_id = await adapter.provision({
        "image": "alpine:3.20", "container_name": "offline-a",
        "replace_existing": False,
        "peer_network": {
            "network_id": "offline-mesh", "alias": "offline-a",
            "port": 24225, "internal": True,
        },
    })
    network_create = next(
        command for command in calls if command[:3] == ["docker", "network", "create"]
    )
    assert "--internal" in network_create
    run = next(command for command in calls if command[:2] == ["docker", "run"])
    assert run[run.index("--network") + 1] == "factory-sandbox-offline-mesh"
    assert run[run.index("--network-alias") + 1] == "offline-a"
    status = await adapter.get_status(env_id)
    assert status["peer_network"]["internal"] is True
    assert status["peer_network"]["endpoint"] == "offline-a:24225"


def test_cleanup_only_removes_empty_sandbox_owned_network(monkeypatch) -> None:
    calls: list[list[str]] = []
    outputs = iter([
        (0, 'python-factory|{"peer": {}}', ""),
        (0, 'python-factory|{}', ""),
    ])

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        if command[:3] == ["docker", "network", "inspect"]:
            return next(outputs)
        return 0, "", ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    docker_adapter.DockerAdapter._remove_empty_owned_peer_network(
        "factory-sandbox-factory-test",
    )
    assert not any(command[:3] == ["docker", "network", "rm"] for command in calls)

    calls.clear()
    outputs = iter([(0, 'python-factory|{}', "")])
    docker_adapter.DockerAdapter._remove_empty_owned_peer_network(
        "factory-sandbox-factory-test",
    )
    assert ["docker", "network", "rm", "factory-sandbox-factory-test"] in calls


def test_cleanup_leaves_unowned_network_untouched(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], timeout: int = 30):
        calls.append(command)
        return 0, 'false|{}', ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    docker_adapter.DockerAdapter._remove_empty_owned_peer_network("external")
    assert len(calls) == 1
