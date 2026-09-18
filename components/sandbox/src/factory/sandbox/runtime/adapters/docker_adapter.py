"""Docker sandbox adapter — runs commands in Docker containers.

Implements SandboxPort against the local Docker daemon.
Each environment = one container. Provision pulls/runs an image,
execute runs commands inside it, terminate stops and removes it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "ubuntu:22.04"
_DEFAULT_SHELL = "/bin/sh"


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a subprocess synchronously, return (exit_code, stdout, stderr)."""
    import subprocess

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Command timed out"
    except FileNotFoundError:
        return 1, "", "docker CLI not found"


class DockerAdapter:
    """Docker-backed sandbox implementing SandboxPort."""

    def __init__(self, default_image: str | None = None) -> None:
        self._default_image = default_image or _DEFAULT_IMAGE
        self._containers: dict[str, dict[str, Any]] = {}

    async def provision(self, config: dict[str, Any]) -> str:
        """Provision a new Docker container.

        Supports profile-based config: ports, entrypoint, container_name,
        env_vars. Falls back to random name + sleep infinity for backward compat.
        """
        image = config.get("image", self._default_image)
        container_name = config.get("container_name", f"sandbox-{uuid.uuid4().hex[:8]}")

        # Auto-terminate existing container with same name (ignore errors)
        _run(["docker", "rm", "-f", container_name], timeout=10)

        from .uds_mount import build_mount_args, proxy_env

        cmd = ["docker", "run", "-d", "--name", container_name,
               "--label", "factory.sandbox=true"]
        if policy_id := config.get("env_vars", {}).get("MCP_POLICY_ID"):
            cmd.extend(["--label", f"factory.workload={policy_id}"])
        cmd.extend(build_mount_args(config))

        for host_port, ctr_port in config.get("ports", {}).items():
            cmd.extend(["-p", f"{host_port}:{ctr_port}"])

        for key, value in {**config.get("env_vars", {}), **proxy_env(config)}.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.append(image)

        entrypoint = config.get("entrypoint")
        if entrypoint:
            cmd.extend(entrypoint)
        elif not config.get("ports"):
            # No profile ports → legacy mode: keep container alive
            cmd.extend(["sleep", "infinity"])

        code, stdout, stderr = _run(cmd, timeout=60)
        if code != 0:
            logger.error("Docker provision failed: %s", stderr)
            raise RuntimeError(f"Docker provision failed: {stderr.strip()}")

        container_id = stdout.strip()
        self._containers[container_name] = {
            "container_id": container_id,
            "image": image,
            "status": "running",
        }
        logger.info("Provisioned container %s (%s)", container_name, image)
        return container_name

    async def terminate(self, env_id: str) -> None:
        """Stop and remove a Docker container."""
        _run(["docker", "rm", "-f", env_id], timeout=30)
        if env_id in self._containers:
            self._containers[env_id]["status"] = "terminated"
        logger.info("Terminated container %s", env_id)

    def sweep_orphans(self) -> list[dict[str, Any]]:
        """Reap crashed/exited labeled containers; return the reaped list."""
        from .uds_mount import sweep_orphans
        return sweep_orphans(_run)

    async def get_status(self, env_id: str) -> dict[str, Any]:
        """Get container status via docker inspect."""
        code, stdout, _ = _run([
            "docker", "inspect", "--format",
            "{{.State.Status}}", env_id,
        ])
        if code != 0:
            return {"status": "unknown"}
        status = stdout.strip()
        return {"status": status, "public_ip": None, "private_ip": None}

    async def execute(
        self, env_id: str, command: str, timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        """Execute a command inside the container."""
        import time

        start = time.monotonic()
        code, stdout, stderr = _run(
            ["docker", "exec", env_id, _DEFAULT_SHELL, "-c", command],
            timeout=timeout_seconds,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "exit_code": code,
            "stdout": stdout,
            "stderr": stderr,
            "duration_ms": elapsed_ms,
        }

    async def upload_file(
        self, env_id: str, local_path: str, remote_path: str,
    ) -> dict[str, Any]:
        """Copy a file into the container."""
        code, _, stderr = _run(
            ["docker", "cp", local_path, f"{env_id}:{remote_path}"],
        )
        if code != 0:
            return {"success": False, "error": stderr.strip()}
        return {"success": True, "remote_path": remote_path}

    async def download_file(
        self, env_id: str, remote_path: str, local_path: str,
    ) -> dict[str, Any]:
        """Copy a file out of the container."""
        code, _, stderr = _run(
            ["docker", "cp", f"{env_id}:{remote_path}", local_path],
        )
        if code != 0:
            return {"success": False, "error": stderr.strip()}
        return {"success": True, "local_path": local_path}

    async def list_files(
        self, env_id: str, path: str = "/",
    ) -> list[dict[str, Any]]:
        """List files inside the container."""
        code, stdout, _ = _run(
            ["docker", "exec", env_id, "ls", "-la", path],
        )
        if code != 0:
            return []
        files: list[dict[str, Any]] = []
        for line in stdout.strip().splitlines()[1:]:  # skip "total" line
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[-1]
            if name in (".", ".."):
                continue
            is_dir = parts[0].startswith("d")
            size = 0
            if not is_dir and len(parts) >= 5:
                try:
                    size = int(parts[4])
                except ValueError:
                    size = 0
            files.append({
                "name": name,
                "path": f"{path}/{name}".replace("//", "/"),
                "size_bytes": size,
                "is_directory": is_dir,
            })
        return files

    def health_check(self) -> dict[str, Any]:
        """Check if Docker daemon is reachable."""
        code, stdout, _ = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
        if code != 0:
            return {"healthy": False, "adapter": "docker", "error": "Docker not available"}
        return {
            "healthy": True,
            "adapter": "docker",
            "docker_version": stdout.strip(),
            "active_containers": len(
                [c for c in self._containers.values() if c["status"] == "running"]
            ),
        }
