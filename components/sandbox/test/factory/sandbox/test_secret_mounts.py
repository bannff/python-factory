"""Sandbox mounts expose only allowlisted host secrets at fixed read-only paths."""

from __future__ import annotations

import json
import logging
import subprocess
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from factory.sandbox.runtime.adapters import secret_mounts
from factory.sandbox.runtime.adapters.docker_adapter import DockerAdapter
from factory.sandbox.runtime.adapters import docker_adapter
from factory.sandbox.mcp.operational import register as register_operational
from factory.sandbox.runtime.profiles import SandboxProfile
from factory.sandbox.runtime.models import SandboxConfig
from factory.sandbox.runtime.provision_context import build_provision_context
from factory.sandbox.runtime.runtime import SandboxRuntime
from factory.sandbox.mcp.operational_extended import register as register_extended
from factory.mcp_utils.runtime.tool_catalog import ToolCatalog

PINNED_IMAGE = "sha256:" + "a" * 64
INSPECTED_ENTRYPOINT = '["/usr/local/bin/python", "/sealed/entrypoint.py"]\n'


def test_profile_accepts_only_named_secret_refs() -> None:
    profile = SandboxProfile(
        name="edge-lab", image="python:3.11-slim",
        secret_refs=["ditto-offline-license"],
    )
    assert profile.secret_refs == ["ditto-offline-license"]
    assert "secret_refs" in profile.model_dump()

    for invalid in ("/host/license", "../license", "ditto-admin-token"):
        with pytest.raises(ValidationError):
            SandboxProfile(
                name="bad", image="python:3.11-slim", secret_refs=[invalid],
            )

    with pytest.raises(ValidationError):
        SandboxProfile.model_validate({
            "name": "bad", "image": "python:3.11-slim",
            "secret_mounts": [{"source": "/host/license", "target": "/tmp/license"}],
            })
    with pytest.raises(ValidationError):
        SandboxProfile(
            name="duplicate", image="python:3.11-slim",
            secret_refs=["ditto-offline-license", "ditto-offline-license"],
        )


def test_resolve_secret_ref_requires_regular_host_file_without_echoing_path(tmp_path) -> None:
    secret = tmp_path / "license.sentinel"
    secret.write_text("SYNTHETIC_SECRET_SENTINEL")
    resolved = secret_mounts.resolve_secret_mounts(
        ["ditto-offline-license"],
        {secret_mounts.DITTO_LICENSE_ENV: str(secret)},
    )
    assert len(resolved) == 1
    assert resolved[0].source == secret.resolve()
    assert resolved[0].target == secret_mounts.DITTO_LICENSE_TARGET

    with pytest.raises(ValueError) as missing:
        secret_mounts.resolve_secret_mounts(["ditto-offline-license"], {})
    assert str(secret) not in str(missing.value)

    with pytest.raises(ValueError) as directory:
        secret_mounts.resolve_secret_mounts(
            ["ditto-offline-license"],
            {secret_mounts.DITTO_LICENSE_ENV: str(tmp_path)},
        )
    assert str(tmp_path) not in str(directory.value)


def test_build_mount_args_uses_fixed_target_and_read_only_bind(tmp_path) -> None:
    source = tmp_path / "license"
    source.write_text("SYNTHETIC_SECRET_SENTINEL")
    mounts = secret_mounts.resolve_secret_mounts(
        ["ditto-offline-license"],
        {secret_mounts.DITTO_LICENSE_ENV: str(source)},
    )

    args = secret_mounts.build_secret_mount_args(mounts)
    assert args == [
        "--mount",
        f"type=bind,source={source.resolve()},target={secret_mounts.DITTO_LICENSE_TARGET},readonly",
    ]


def test_docker_cli_does_not_inherit_host_secret_path(monkeypatch) -> None:
    host_path = "/private/host/license"
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, host_path)
    captured: dict = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    docker_adapter._run(["docker", "info"])
    assert secret_mounts.DITTO_LICENSE_ENV not in captured["env"]
    assert host_path not in captured["env"].values()


def test_profile_resolution_keeps_host_path_out_of_metadata(tmp_path, monkeypatch) -> None:
    source = tmp_path / "license"
    source.write_text("SYNTHETIC_SECRET_SENTINEL")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "edge-lab.yaml").write_text(
        f"image: {PINNED_IMAGE}\n"
        "container_name: edge-lab\n"
        "replace_existing: false\n"
        "entrypoint: [run]\n"
        "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, internal: true}\n"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, str(source))

    config, metadata, _ = build_provision_context(SandboxConfig(), "edge-lab")
    assert config["secret_mounts"][0].source == source.resolve()
    serialized_metadata = json.dumps(metadata)
    assert str(source) not in serialized_metadata
    assert "SYNTHETIC_SECRET_SENTINEL" not in serialized_metadata
    assert "secret_mounts" not in metadata


def test_secret_profile_must_not_replace_existing_container(tmp_path, monkeypatch) -> None:
    source = tmp_path / "license"
    source.write_text("SYNTHETIC_SECRET_SENTINEL")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "unsafe.yaml").write_text(
        f"image: {PINNED_IMAGE}\n"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, str(source))
    with pytest.raises(ValueError, match="must not replace"):
        build_provision_context(SandboxConfig(), "unsafe")


@pytest.mark.parametrize(
    "network,override",
    [
        ("", None),
        (
            "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, "
            "internal: false}\n",
            None,
        ),
        (
            "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, "
            "internal: true}\n",
            {
                "network_id": "secret-lab", "alias": "edge-lab",
                "port": 4321, "internal": False,
            },
        ),
    ],
)
def test_secret_profile_requires_explicit_internal_peer_network(
    tmp_path, monkeypatch, network, override,
) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "secret.yaml").write_text(
        f"image: {PINNED_IMAGE}\n"
        "replace_existing: false\n"
        "entrypoint: [/usr/local/bin/ditto-runner]\n"
        f"{network}"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    with pytest.raises(ValueError, match="require an internal peer network"):
        build_provision_context(SandboxConfig(), "secret", peer_network=override)


@pytest.mark.parametrize(
    "trusted_entrypoint,setup_commands,message",
    [
        ("", "", "trusted fixed entrypoint"),
        (
            "entrypoint: [/usr/local/bin/ditto-runner]\n",
            'setup_commands: ["pip install x"]\n',
            "cannot define setup_commands",
        ),
    ],
)
def test_secret_profile_requires_trusted_noninteractive_entrypoint(
    tmp_path, monkeypatch, trusted_entrypoint, setup_commands, message,
) -> None:
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "secret.yaml").write_text(
        f"image: {PINNED_IMAGE}\n"
        "replace_existing: false\n"
        f"{trusted_entrypoint}"
        "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, internal: true}\n"
        f"{setup_commands}"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    with pytest.raises(ValueError, match=message):
        build_provision_context(SandboxConfig(), "secret")


@pytest.mark.asyncio
async def test_secret_source_and_contents_stay_out_of_public_runtime_surfaces(
    tmp_path, monkeypatch, caplog,
) -> None:
    source = tmp_path / "offline-license"
    sentinel = "SYNTHETIC_SECRET_SENTINEL"
    source.write_text(sentinel)
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "edge-lab.yaml").write_text(
        f"image: {PINNED_IMAGE}\n"
        "container_name: edge-lab\n"
        "replace_existing: false\n"
        "entrypoint: [run]\n"
        "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, internal: true}\n"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, str(source))

    adapter = DockerAdapter()
    captured: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        captured.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            if "{{json .Config.Entrypoint}}" in command:
                return 0, INSPECTED_ENTRYPOINT, ""
            return 0, PINNED_IMAGE + "\n", ""
        if command[:3] == ["docker", "run", "-d"]:
            return 0, "container-id\n", ""
        if command[:3] == ["docker", "container", "inspect"]:
            return 1, "", "No such container"
        if command[:3] == ["docker", "network", "inspect"]:
            if command[-1] == "factory-sandbox-secret-lab":
                if "{{json .Containers}}" in command:
                    return 0, "{}", ""
                return 1, "", "No such network"
        return 0, "", ""

    monkeypatch.setattr(
        "factory.sandbox.runtime.adapters.docker_adapter._run", fake_run,
    )
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "factory.sandbox.runtime.runtime.emit",
        lambda event, payload: emitted.append((event, payload)),
    )
    store = MagicMock()
    store.load.return_value = None
    runtime = SandboxRuntime(adapter=adapter, store=store)

    with caplog.at_level(logging.INFO):
        environment = await runtime.provision(SandboxConfig(), profile="edge-lab")

    docker_run = next(command for command in captured if command[:3] == ["docker", "run", "-d"])
    assert docker_run[-2:] == [PINNED_IMAGE, "run"]
    assert "--entrypoint" not in docker_run
    assert "--mount" in docker_run
    assert "factory.sandbox.secret_output_suppressed=true" in docker_run
    assert "factory.sandbox.timeout_seconds=3600" in docker_run
    mount_spec = docker_run[docker_run.index("--mount") + 1]
    assert mount_spec.endswith(",readonly")
    assert f"source={source.resolve()}" in mount_spec
    assert all(
        not (argument.startswith("-e") and str(source) in argument)
        for argument in docker_run
    )

    public_output = json.dumps({
        "environment": environment.model_dump(),
        "events": emitted,
        "logs": caplog.text,
    }, default=str)
    assert str(source) not in public_output
    assert sentinel not in public_output
    assert secret_mounts.DITTO_LICENSE_TARGET not in public_output


@pytest.mark.parametrize("override", [
    {"auto_terminate": False},
    {"timeout_seconds": 0},
    {"timeout_seconds": 86401},
    {"timeout_seconds": True},
])
@pytest.mark.asyncio
async def test_secret_provision_rejects_disabled_or_invalid_timeout_before_docker(
    monkeypatch, override,
) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(
        docker_adapter, "_run",
        lambda command, timeout=30: calls.append(command) or (0, "", ""),
    )
    with pytest.raises(ValueError, match="auto-termination|timeout"):
        await DockerAdapter().provision({
            "image": PINNED_IMAGE,
            "entrypoint": ["run"],
            "secret_mounts": [object()],
            "replace_existing": False,
            **override,
        })
    assert calls == []


@pytest.mark.asyncio
async def test_docker_failure_does_not_echo_secret_source_or_contents(
    tmp_path, monkeypatch, caplog,
) -> None:
    source = tmp_path / "offline-license"
    sentinel = "SYNTHETIC_SECRET_SENTINEL"
    source.write_text(sentinel)
    adapter = DockerAdapter()
    calls: list[list[str]] = []

    def failing_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            if "{{json .Config.Entrypoint}}" in command:
                return 0, INSPECTED_ENTRYPOINT, ""
            return 0, PINNED_IMAGE + "\n", ""
        if command[:3] == ["docker", "container", "inspect"]:
            return 1, "", "No such container"
        if command[:3] == ["docker", "network", "inspect"]:
            if "{{json .Containers}}" in command:
                return 0, "{}", ""
            if any("{{.Internal}}" in part for part in command):
                return 0, "python-factory|true", ""
            if any("{{json .Containers}}" in part for part in command):
                return 0, "python-factory|{}", ""
            raise AssertionError(f"Unexpected Docker network inspect: {command}")
        if command[:3] == ["docker", "run", "-d"]:
            return 1, "", f"invalid mount source {source}: {sentinel}"
        if command[:3] == ["docker", "network", "rm"]:
            return 0, "", ""
        raise AssertionError(f"Unexpected Docker call: {command}")

    monkeypatch.setattr(
        "factory.sandbox.runtime.adapters.docker_adapter._run", failing_run,
    )
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as failure:
            await adapter.provision({
                "image": PINNED_IMAGE,
                "entrypoint": ["run"],
                "replace_existing": False,
                "peer_network": {
                    "network_id": "secret-lab", "alias": "edge-lab",
                    "port": 4321, "internal": True,
                },
                "secret_mounts": secret_mounts.resolve_secret_mounts(
                    ["ditto-offline-license"],
                    {secret_mounts.DITTO_LICENSE_ENV: str(source)},
                ),
            })
    docker_runs = [call for call in calls if call[:3] == ["docker", "run", "-d"]]
    assert len(docker_runs) == 1
    assert "--mount" in docker_runs[0]
    assert docker_runs[0][-2:] == [PINNED_IMAGE, "run"]
    assert "attaching a configured secret" in str(failure.value)
    public_error = f"{failure.value}\n{caplog.text}"
    assert str(source) not in public_error
    assert sentinel not in public_error


@pytest.mark.asyncio
async def test_non_docker_adapter_rejects_secret_mount_before_provision(
    tmp_path, monkeypatch,
) -> None:
    source = tmp_path / "license"
    source.write_text("SYNTHETIC_SECRET_SENTINEL")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "edge-lab.yaml").write_text(
        f"image: {PINNED_IMAGE}\n"
        "container_name: edge-lab\n"
        "replace_existing: false\n"
        "entrypoint: [run]\n"
        "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, internal: true}\n"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, str(source))
    adapter = MagicMock()
    adapter.provision = AsyncMock()
    runtime = SandboxRuntime(adapter=adapter, store=MagicMock())
    with pytest.raises(ValueError, match="require the Docker adapter"):
        await runtime.provision(SandboxConfig(), profile="edge-lab")
    adapter.provision.assert_not_awaited()


@pytest.mark.asyncio
async def test_secret_enabled_execute_is_denied_and_command_is_redacted(
    monkeypatch, caplog,
) -> None:
    from factory.mcp_utils.runtime.tool_catalog import ToolCatalog
    from factory.sandbox.core import EnvironmentStatus
    from factory.sandbox.runtime.models import EnvironmentInfo

    sentinel = "SYNTHETIC_SECRET_SENTINEL"
    environment = EnvironmentInfo(
        env_id="edge-1", status=EnvironmentStatus.RUNNING,
        instance_type="docker", created_at="2026-09-30T00:00:00+00:00",
        metadata={"secret_mounts_enabled": True},
    )
    adapter = MagicMock()
    adapter.execute = AsyncMock(return_value={
        "exit_code": 0, "stdout": sentinel, "stderr": sentinel,
        "duration_ms": 3,
    })
    store = MagicMock()
    store.load.return_value = environment
    runtime = SandboxRuntime(adapter=adapter, store=store)
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "factory.sandbox.runtime.runtime.emit",
        lambda event, payload: emitted.append((event, payload)),
    )
    catalog = ToolCatalog("sandbox-secret-output")
    register_extended(catalog, runtime)
    tool = await catalog.get_tool("sandbox.execute")

    with caplog.at_level(logging.INFO):
        result = await tool.fn(env_id="edge-1", command=sentinel)

    assert result.ok
    assert result.data.success is False
    assert result.data.exit_code == 126
    assert result.data.stdout == ""
    assert "Execution is disabled" in result.data.stderr
    adapter.execute.assert_not_awaited()
    assert len(emitted) == 1
    assert emitted[0][1]["output_suppressed"] is True
    assert emitted[0][1]["command"] == "[omitted: secret-enabled sandbox]"
    public_surfaces = json.dumps({
        "tool_result": result.model_dump(),
        "events": emitted,
        "logs": caplog.text,
    }, default=str)
    assert sentinel not in public_surfaces


@pytest.mark.asyncio
async def test_execute_suppresses_output_when_store_misses_and_inspect_fails(
    monkeypatch,
) -> None:
    from factory.sandbox.runtime.adapters import docker_adapter

    sentinel = "SYNTHETIC_SECRET_SENTINEL"

    calls = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        return 1, "", "Docker unavailable"

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    store = MagicMock()
    store.load.return_value = None
    runtime = SandboxRuntime(adapter=DockerAdapter(), store=store)
    runtime._store.load.return_value = None
    result = await runtime.execute("edge-lab", "cat license")

    assert result.stdout == ""
    assert "Execution is disabled" in result.stderr
    assert calls == [[
        "docker", "inspect", "--format",
        '{{ index .Config.Labels "factory.sandbox.secret_output_suppressed" }}',
        "edge-lab",
    ]]


def test_secret_profile_serialization_contains_reference_only(tmp_path, monkeypatch) -> None:
    source = tmp_path / "secret-file"
    source.write_text("SYNTHETIC_SECRET_SENTINEL")
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, str(source))
    profile = SandboxProfile(
        name="edge-lab", image="python:3.11-slim",
        secret_refs=["ditto-offline-license"],
    )
    serialized = profile.model_dump_json()
    assert "ditto-offline-license" in serialized
    assert str(source) not in serialized
    assert "SYNTHETIC_SECRET_SENTINEL" not in serialized


def test_docker_secret_suppression_marker_survives_store_miss(monkeypatch) -> None:
    def fake_run(command, timeout=30):  # noqa: ANN001
        assert command[:3] == ["docker", "inspect", "--format"]
        return 0, "true\n", ""

    monkeypatch.setattr(
        "factory.sandbox.runtime.adapters.docker_adapter._run", fake_run,
    )
    assert DockerAdapter().get_secret_output_suppression("edge-lab") is True


def test_docker_secret_suppression_marker_is_unknown_on_inspect_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "factory.sandbox.runtime.adapters.docker_adapter._run",
        lambda command, timeout=30: (1, "", "Docker unavailable"),
    )
    assert DockerAdapter().get_secret_output_suppression("edge-lab") is None


@pytest.mark.parametrize(
    "inspect_result",
    [
        (0, "true\n", ""),
        (1, "", "Docker unavailable"),
        (0, "unexpected marker output\n", ""),
    ],
)
@pytest.mark.asyncio
async def test_docker_adapter_execute_denies_secret_or_unverified_container(
    monkeypatch, inspect_result,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        if command[:3] == ["docker", "inspect", "--format"]:
            return inspect_result
        raise AssertionError("secret-enabled container must not receive docker exec")

    monkeypatch.setattr(
        "factory.sandbox.runtime.adapters.docker_adapter._run", fake_run,
    )
    result = await DockerAdapter().execute("edge-lab", "cat /run/secrets/license")

    assert result["exit_code"] == 126
    assert "Execution is disabled" in result["stderr"]
    assert calls == [[
        "docker", "inspect", "--format",
        '{{ index .Config.Labels "factory.sandbox.secret_output_suppressed" }}',
        "edge-lab",
    ]]


@pytest.mark.asyncio
async def test_diff_cannot_bypass_docker_secret_execute_guard(monkeypatch) -> None:
    from factory.sandbox.runtime.adapters import docker_adapter

    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        return 0, "true\n", ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    store = MagicMock()
    store.load.return_value = None
    runtime = SandboxRuntime(adapter=DockerAdapter(), store=store)

    result = await runtime.diff("edge-lab")

    assert result == {
        "is_git_repo": False, "path": ".", "files": [], "stat": "",
    }
    assert calls and all(call[:2] == ["docker", "inspect"] for call in calls)


@pytest.mark.asyncio
async def test_cfn_deploy_cannot_bypass_docker_secret_execute_guard(monkeypatch) -> None:
    from factory.sandbox.runtime.adapters import docker_adapter

    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        return 0, "true\n", ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    runtime = SandboxRuntime(adapter=DockerAdapter(), store=MagicMock())

    result = await runtime.deploy_stack(
        "edge-lab", "stack", "Resources: {}",
    )

    assert result["success"] is False
    assert calls and all(call[:2] == ["docker", "inspect"] for call in calls)


def test_discovery_restores_secret_suppression_marker(monkeypatch) -> None:
    from factory.sandbox.runtime import discovery

    monkeypatch.setattr(
        discovery, "_docker_ps_lines", lambda args: [
            "edge-lab\tUp 1 minute\tjust now\t"
            "factory.sandbox=true,factory.sandbox.secret_output_suppressed=true"
        ],
    )
    environments = discovery.discover_docker_envs()
    assert environments[0].metadata["secret_mounts_enabled"] is True


@pytest.mark.asyncio
async def test_secret_enabled_download_is_blocked_before_host_copy(monkeypatch) -> None:
    from factory.sandbox.core import EnvironmentStatus
    from factory.sandbox.runtime.models import EnvironmentInfo

    sentinel = "SYNTHETIC_SECRET_SENTINEL"
    adapter = MagicMock()
    adapter.download_file = AsyncMock(return_value={
        "success": True, "contents": sentinel,
    })
    store = MagicMock()
    store.load.return_value = EnvironmentInfo(
        env_id="edge-1", status=EnvironmentStatus.RUNNING,
        instance_type="docker", created_at="2026-09-30T00:00:00+00:00",
        metadata={"secret_mounts_enabled": True},
    )
    runtime = SandboxRuntime(adapter=adapter, store=store)
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "factory.sandbox.runtime.runtime.emit",
        lambda event, payload: emitted.append((event, payload)),
    )

    result = await runtime.download_file("edge-1", "/run/secrets/license", "/tmp/license")

    assert result["success"] is False
    assert "disabled" in result["error"]
    adapter.download_file.assert_not_awaited()
    assert sentinel not in json.dumps({"result": result, "events": emitted})


@pytest.mark.asyncio
async def test_download_fails_closed_when_store_misses_and_docker_is_unavailable(
    monkeypatch,
) -> None:
    from factory.sandbox.runtime.adapters import docker_adapter

    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        return 1, "", "Docker unavailable"

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    runtime = SandboxRuntime(adapter=DockerAdapter(), store=MagicMock())
    runtime._store.load.return_value = None
    result = await runtime.download_file("edge-lab", "/secret", "/tmp/secret")

    assert result["success"] is False
    assert calls == [[
        "docker", "inspect", "--format",
        '{{ index .Config.Labels "factory.sandbox.secret_output_suppressed" }}',
        "edge-lab",
    ]]


@pytest.mark.asyncio
async def test_secret_source_is_not_an_mcp_parameter_or_result() -> None:
    from factory.sandbox.core import EnvironmentStatus
    from factory.sandbox.runtime.models import EnvironmentInfo

    runtime = MagicMock()
    runtime.provision = AsyncMock(return_value=EnvironmentInfo(
        env_id="edge-1", status=EnvironmentStatus.PROVISIONING,
        instance_type="docker", created_at="2026-09-30T00:00:00+00:00",
    ))
    catalog = ToolCatalog("sandbox-secret-reference")
    register_operational(catalog, runtime)
    tool = await catalog.get_tool("sandbox.provision")
    schema = tool.fn._mcp_input_model.model_json_schema(mode="validation")
    assert "secret_refs" not in schema["properties"]
    assert "secret_mounts" not in schema["properties"]
    output = json.dumps(schema)
    assert "SANDBOX_SECRET_DITTO_OFFLINE_LICENSE_FILE" not in output
    result = await tool.fn(profile="edge-lab")
    assert result.data.environment.env_id == "edge-1"
    assert "secret_mount" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_invalid_secret_profile_path_is_hidden_from_tool_errors_and_logs(
    tmp_path, monkeypatch, caplog,
) -> None:
    host_path = "/private/synthetic/license-path-sentinel"
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "invalid-secret.yaml").write_text(
        "image: python:3.11-slim\n"
        "replace_existing: false\n"
        f"secret_refs: [{host_path}]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    adapter = MagicMock()
    adapter.provision = AsyncMock()
    runtime = SandboxRuntime(adapter=adapter, store=MagicMock())
    catalog = ToolCatalog("sandbox-secret-validation")
    register_operational(catalog, runtime)
    tool = await catalog.get_tool("sandbox.provision")

    with caplog.at_level(logging.ERROR, logger="factory.mcp_utils.runtime.tool_failure"):
        result = await tool.fn(profile="invalid-secret")

    assert result.ok is False
    assert host_path not in caplog.text
    assert host_path not in result.model_dump_json()
    adapter.provision.assert_not_awaited()


@pytest.mark.parametrize("image,entrypoint,message", [
    ("python:3.11-slim", ["/usr/local/bin/runner"], "local image ID"),
    ("repo@sha256:" + "a" * 64, ["/usr/local/bin/runner"], "local image ID"),
    (PINNED_IMAGE, [], "fixed nonempty command"),
    (PINNED_IMAGE, ["/usr/local/bin/runner", ""], "fixed nonempty command"),
    (PINNED_IMAGE, ["/bin/sh", "-c", "cat /run/secrets/ditto-offline-license"],
     "fixed noninteractive command"),
])
def test_secret_profile_requires_pinned_image_and_fixed_argv(
    tmp_path, monkeypatch, image, entrypoint, message,
) -> None:
    source = tmp_path / "license"
    source.write_text("synthetic")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "secret.yaml").write_text(
        f"image: {image}\n"
        "replace_existing: false\n"
        f"entrypoint: {json.dumps(entrypoint)}\n"
        "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, internal: true}\n"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, str(source))
    with pytest.raises(ValueError, match=message):
        build_provision_context(SandboxConfig(), "secret")


def test_secret_profile_accepts_fixed_command_for_baked_image_entrypoint(
    tmp_path, monkeypatch,
) -> None:
    source = tmp_path / "license"
    source.write_text("synthetic")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "secret.yaml").write_text(
        f"image: {PINNED_IMAGE}\n"
        "replace_existing: false\n"
        "entrypoint: [run]\n"
        "peer_network: {network_id: secret-lab, alias: edge-lab, port: 4321, internal: true}\n"
        "secret_refs: [ditto-offline-license]\n"
    )
    monkeypatch.setenv("SANDBOX_PROFILES_DIR", str(profiles))
    monkeypatch.setenv(secret_mounts.DITTO_LICENSE_ENV, str(source))

    config, _, _ = build_provision_context(SandboxConfig(), "secret")
    assert config["entrypoint"] == ["run"]


@pytest.mark.asyncio
async def test_runtime_file_mutations_and_diff_stop_at_secret_boundary(monkeypatch) -> None:
    from factory.sandbox.core import EnvironmentStatus
    from factory.sandbox.runtime.models import EnvironmentInfo

    environment = EnvironmentInfo(
        env_id="edge-1", status=EnvironmentStatus.RUNNING,
        instance_type="docker", created_at="2026-09-30T00:00:00+00:00",
        metadata={"secret_mounts_enabled": True},
    )
    adapter = MagicMock()
    adapter.upload_file = AsyncMock(return_value={"success": True})
    adapter.execute = AsyncMock(return_value={"exit_code": 0, "stdout": "secret"})
    adapter.download_file = AsyncMock(return_value={"success": True})
    store = MagicMock()
    store.load.return_value = environment
    runtime = SandboxRuntime(adapter=adapter, store=store)
    monkeypatch.setattr("factory.sandbox.runtime.runtime.emit", lambda *_: None)

    assert (await runtime.write_file("edge-1", "/tmp/x", "payload"))["success"] is False
    assert (await runtime.upload_file("edge-1", "/tmp/x", "/tmp/y"))["success"] is False
    assert await runtime.diff("edge-1") == {
        "is_git_repo": False, "path": ".", "files": [], "stat": "",
    }
    assert (await runtime.download_file("edge-1", "/tmp/x", "/tmp/y"))["success"] is False
    adapter.upload_file.assert_not_awaited()
    adapter.execute.assert_not_awaited()
    adapter.download_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_file_mutations_fail_closed_if_docker_inspect_fails(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        return 1, "", "Docker unavailable"

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    store = MagicMock()
    store.load.return_value = None
    runtime = SandboxRuntime(adapter=DockerAdapter(), store=store)
    assert (await runtime.write_file("edge-lab", "/tmp/x", "payload"))["success"] is False
    assert (await runtime.upload_file("edge-lab", "/tmp/x", "/tmp/y"))["success"] is False
    assert (await runtime.download_file("edge-lab", "/tmp/x", "/tmp/y"))["success"] is False
    assert (await runtime.diff("edge-lab"))["files"] == []
    assert calls and all(command[:2] == ["docker", "inspect"] for command in calls)


@pytest.mark.parametrize("marker", [(0, "true\n", ""), (1, "", "unavailable")])
@pytest.mark.asyncio
async def test_direct_docker_file_ops_deny_secret_or_unverifiable_container(
    monkeypatch, marker,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        if command[:3] == ["docker", "inspect", "--format"]:
            return marker
        raise AssertionError("secret container must not receive docker cp/exec")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    adapter = DockerAdapter()
    assert (await adapter.upload_file("edge-lab", "/tmp/x", "/tmp/y"))["success"] is False
    assert (await adapter.download_file("edge-lab", "/tmp/x", "/tmp/y"))["success"] is False
    assert await adapter.list_files("edge-lab") == []
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_direct_docker_file_ops_continue_for_verified_nonsecret_container(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        if command[:3] == ["docker", "inspect", "--format"]:
            return 0, "<no value>\n", ""
        if command[:2] == ["docker", "cp"]:
            return 0, "", ""
        if command[:2] == ["docker", "exec"]:
            return 0, "total 0\n", ""
        raise AssertionError(f"Unexpected Docker call: {command}")

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    adapter = DockerAdapter()
    assert (await adapter.upload_file("ordinary", "/tmp/x", "/tmp/y"))["success"]
    assert (await adapter.download_file("ordinary", "/tmp/y", "/tmp/x"))["success"]
    assert isinstance(await adapter.list_files("ordinary"), list)
    assert sum(call[:2] == ["docker", "cp"] for call in calls) == 2
    assert sum(call[:2] == ["docker", "exec"] for call in calls) == 1


@pytest.mark.asyncio
async def test_direct_docker_secret_provision_rejects_wrong_local_image_id_before_mutation(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        return 0, "sha256:" + "b" * 64 + "\n", ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(ValueError, match="local image ID"):
        await DockerAdapter().provision({
            "image": PINNED_IMAGE, "entrypoint": ["/usr/local/bin/runner"],
            "secret_mounts": [object()], "replace_existing": False,
        })
    assert calls == [["docker", "image", "inspect", "--format", "{{.Id}}", PINNED_IMAGE]]


@pytest.mark.parametrize("image_entrypoint", [
    "null\n", "[]\n", '"/usr/local/bin/runner"\n',
    '["sh", "-c", "cat /run/secrets/ditto-offline-license"]\n',
    '["/bin/sh", "-c", "cat /run/secrets/ditto-offline-license"]\n',
    '["runner", "run"]\n',
    '["/usr/local/bin/runner", "--eval", "payload"]\n',
    "not json\n",
])
@pytest.mark.asyncio
async def test_secret_provision_rejects_untrusted_image_entrypoint_before_mutation(
    monkeypatch, image_entrypoint,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        if command[:3] != ["docker", "image", "inspect"]:
            raise AssertionError("Container or network mutation reached")
        if "{{.Id}}" in command:
            return 0, PINNED_IMAGE + "\n", ""
        return 0, image_entrypoint, ""

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(ValueError, match="image ENTRYPOINT"):
        await DockerAdapter().provision({
            "image": PINNED_IMAGE, "entrypoint": ["run"],
            "secret_mounts": [object()], "replace_existing": False,
        })
    assert len(calls) == 2
    assert all(command[:3] == ["docker", "image", "inspect"] for command in calls)


@pytest.mark.asyncio
async def test_secret_provision_fails_closed_if_image_entrypoint_inspect_fails(
    monkeypatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(command, timeout=30):  # noqa: ANN001
        calls.append(command)
        if command[:3] != ["docker", "image", "inspect"]:
            raise AssertionError("Container or network mutation reached")
        if "{{.Id}}" in command:
            return 0, PINNED_IMAGE + "\n", ""
        return 1, "", "Docker metadata unavailable"

    monkeypatch.setattr(docker_adapter, "_run", fake_run)
    with pytest.raises(ValueError, match="image ENTRYPOINT"):
        await DockerAdapter().provision({
            "image": PINNED_IMAGE, "entrypoint": ["run"],
            "secret_mounts": [object()], "replace_existing": False,
        })
    assert len(calls) == 2
