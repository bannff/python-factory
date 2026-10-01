"""Sandbox runtime - main orchestration layer."""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core import EnvironmentStatus
from .adapter_factory import create_adapter, create_store
from .cfn_stack_ops import CfnStackOpsMixin
from .discovery import discover_docker_envs
from .event_emitter import emit
from .event_payloads import base_env_payload, lifecycle_payload
from .health import runtime_health
from .models import CommandResult, EnvironmentInfo, SandboxConfig
from .ports import SandboxPort, SandboxStore
from .provision_context import build_provision_context
from .peer_network import PeerNetworkSpec
from .reaper import OrphanSweepMixin
from .workspace import get_or_create_workspace

# Re-exported for backward compatibility; canonical home is adapter_factory.
__all__ = ["SandboxRuntime", "create_adapter"]

_SANDBOX_TMP = Path(os.environ.get("SANDBOX_TMP_ROOT", "/tmp/factory-sandbox"))


class SandboxRuntime(CfnStackOpsMixin, OrphanSweepMixin):
    """Runtime for sandbox environment operations."""

    def __init__(
        self, adapter: SandboxPort, store: SandboxStore | None = None,
    ) -> None:
        """Initialize with a sandbox adapter and optional store."""
        self._adapter = adapter
        self._store: SandboxStore = store or create_store()

    async def provision(
        self, config: SandboxConfig | None = None, profile: str | None = None,
        device_preset: str | None = None,
        peer_network: PeerNetworkSpec | None = None,
    ) -> EnvironmentInfo:
        """Provision a new sandbox environment.

        When profile is set, resolves it and merges Docker config into adapter config.
        """
        cfg = config or SandboxConfig()
        adapter_config, metadata, setup_commands = build_provision_context(
            cfg, profile, device_preset, peer_network,
        )
        if (
            device_preset is not None
            or adapter_config.get("secret_mounts")
            or adapter_config.get("peer_network")
        ):
            from .adapters.docker_adapter import DockerAdapter

            if device_preset is not None and not isinstance(self._adapter, DockerAdapter):
                raise ValueError("Device presets require the Docker adapter")
            if adapter_config.get("secret_mounts") and not isinstance(
                self._adapter, DockerAdapter,
            ):
                raise ValueError("Sandbox secret mounts require the Docker adapter")
            if adapter_config.get("peer_network") and not isinstance(
                self._adapter, DockerAdapter,
            ):
                raise ValueError("Sandbox peer networks require the Docker adapter")

        env_id = await self._adapter.provision(adapter_config)
        self.workspace_dir(env_id)  # create artifact staging dir
        if setup_commands:
            from .setup import run_setup_commands
            setup_results = await run_setup_commands(
                self._adapter, env_id, setup_commands,
            )
            metadata["setup_commands"] = setup_results
            metadata["setup_ok"] = all(r.get("success") for r in setup_results)

        env = EnvironmentInfo(
            env_id=env_id,
            status=EnvironmentStatus.PROVISIONING,
            instance_type=cfg.instance_type,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata,
        )
        self._store.save(env)
        emit("sandbox.provisioned", lifecycle_payload(env))
        return env

    async def terminate(self, env_id: str) -> None:
        """Terminate a sandbox environment."""
        await self._adapter.terminate(env_id)
        ws = _SANDBOX_TMP / env_id
        if ws.exists():
            shutil.rmtree(ws, ignore_errors=True)
        env = self._store.load(env_id)
        if env is not None:
            env.status = EnvironmentStatus.TERMINATED
            self._store.save(env)
            emit("sandbox.terminated", lifecycle_payload(env))

    def workspace_dir(self, env_id: str) -> Path:
        """Return (and create) a contained artifact staging directory."""
        return get_or_create_workspace(_SANDBOX_TMP, env_id)

    def _file_access_denied(self, env_id: str, env: EnvironmentInfo | None) -> bool:
        """Fail closed if secret state is enabled or Docker cannot verify it."""
        if env and env.metadata.get("secret_mounts_enabled", False):
            return True
        from .adapters.docker_adapter import DockerAdapter

        return isinstance(self._adapter, DockerAdapter) and (
            self._adapter.get_secret_output_suppression(env_id) is not False
        )

    async def get_status(self, env_id: str) -> EnvironmentInfo | None:
        """Get environment status."""
        env = self._store.load(env_id)
        if env is None:
            return None
        status = await self._adapter.get_status(env_id)
        env.status = EnvironmentStatus(status.get("status", "unknown"))
        env.public_ip = status.get("public_ip")
        env.private_ip = status.get("private_ip")
        if status.get("peer_network") is not None:
            env.metadata["peer_network"] = status["peer_network"]
        self._store.save(env)
        emit("sandbox.status_observed", lifecycle_payload(env))
        return env

    async def execute(
        self, env_id: str, command: str, timeout_seconds: int = 300
    ) -> CommandResult:
        """Execute command in environment."""
        env = self._store.load(env_id)
        suppress_output = bool(
            env and env.metadata.get("secret_mounts_enabled", False)
        )
        from .adapters.docker_adapter import DockerAdapter

        if not suppress_output:
            if isinstance(self._adapter, DockerAdapter):
                marker = self._adapter.get_secret_output_suppression(env_id)
                # Unknown container state is treated as secret-enabled so a
                # store/daemon failure cannot turn execution or telemetry on.
                suppress_output = marker is not False
        if suppress_output:
            # A mounted host secret is readable by any command in the
            # container. Secret-enabled and unverifiable Docker containers
            # therefore run only their trusted fixed entrypoint.
            result = {
                "exit_code": 126,
                "stdout": "",
                "stderr": "Execution is disabled for secret-enabled or unverified sandboxes",
                "duration_ms": 0,
            }
            execution_denied = True
        else:
            result = await self._adapter.execute(env_id, command, timeout_seconds)
            execution_denied = False
        command_result = CommandResult(
            success=result.get("exit_code", 1) == 0,
            exit_code=result.get("exit_code", 1),
            stdout="" if suppress_output and not execution_denied else result.get("stdout", ""),
            stderr=(
                "" if suppress_output and not execution_denied
                else result.get("stderr", "")
            ),
            duration_ms=result.get("duration_ms", 0),
        )
        from .output_capture import capture_output
        payload = base_env_payload(env_id, env) | {
            "command": (
                "[omitted: secret-enabled sandbox]"
                if suppress_output else command[:160]
            ),
            "success": command_result.success,
            "exit_code": command_result.exit_code,
            "duration_ms": command_result.duration_ms,
        }
        if suppress_output:
            payload["output_suppressed"] = True
        payload |= capture_output(command_result.stdout, command_result.stderr)
        emit("sandbox.command_executed", payload)
        return command_result

    async def write_file(
        self, env_id: str, remote_path: str, content: str, encoding: str = "utf8",
    ) -> dict[str, Any]:
        """Write inline content to a file inside the environment.

        Decodes content (utf8|base64), stages it, and copies it in — no caller
        host staging or shell escaping. Malformed input surfaces as a failure
        result rather than a transport error.
        """
        env = self._store.load(env_id)
        if self._file_access_denied(env_id, env):
            result = {
                "success": False,
                "error": "File operations are disabled for secret-enabled or unverified sandboxes",
            }
        else:
            from .file_ops import write_file as _write
            try:
                result = await _write(
                    self._adapter.upload_file, env_id, remote_path, content, encoding,
                )
            except (ValueError, OSError) as exc:
                result = {"success": False, "error": str(exc)}
        emit("sandbox.file_written", base_env_payload(env_id, env) | {
            "remote_path": remote_path,
            "encoding": encoding,
            "bytes_written": result.get("bytes_written"),
            "success": bool(result.get("success", False)),
        })
        return result

    async def diff(self, env_id: str, path: str = ".") -> dict[str, Any]:
        """Report changed files (tracked + untracked) under ``path`` via git."""
        env = self._store.load(env_id)
        if self._file_access_denied(env_id, env):
            result = {"is_git_repo": False, "path": path, "files": [], "stat": ""}
        else:
            from .diff_ops import git_diff
            result = await git_diff(self._adapter.execute, env_id, path)
        emit("sandbox.files_changed", base_env_payload(env_id, env) | {
            "path": path,
            "is_git_repo": bool(result.get("is_git_repo", False)),
            "changed_count": len(result.get("files", [])),
        })
        return result

    async def upload_file(
        self, env_id: str, local_path: str, remote_path: str
    ) -> dict[str, Any]:
        """Upload file to environment."""
        env = self._store.load(env_id)
        if self._file_access_denied(env_id, env):
            result = {
                "success": False,
                "error": "File operations are disabled for secret-enabled or unverified sandboxes",
            }
        else:
            result = await self._adapter.upload_file(env_id, local_path, remote_path)
        emit("sandbox.file_uploaded", base_env_payload(env_id, env) | {
            "local_path": local_path,
            "remote_path": remote_path,
            "success": bool(result.get("success", False)),
        })
        return result

    async def download_file(
        self, env_id: str, remote_path: str, local_path: str
    ) -> dict[str, Any]:
        """Download file from environment."""
        env = self._store.load(env_id)
        if self._file_access_denied(env_id, env):
            result = {
                "success": False,
                "error": "Downloads are disabled for secret-enabled or unverified sandboxes",
            }
        else:
            result = await self._adapter.download_file(
                env_id, remote_path, local_path,
            )
        emit("sandbox.file_downloaded", base_env_payload(env_id, env) | {
            "remote_path": remote_path,
            "local_path": local_path,
            "success": bool(result.get("success", False)),
            "size_bytes": result.get("size_bytes"),
        })
        return result

    def list_environments(self) -> list[EnvironmentInfo]:
        """List all environments (store + discovered from Docker)."""
        stored = {e.env_id: e for e in self._store.list_environments()}
        # Reconcile: merge discovered Docker envs into the store
        for discovered in discover_docker_envs():
            if discovered.env_id not in stored:
                self._store.save(discovered)
                stored[discovered.env_id] = discovered
        return list(stored.values())

    def health_check(self) -> dict[str, Any]:
        """Check runtime health."""
        return runtime_health(self._adapter, self._store)
