"""Docker sandbox adapter — runs commands in Docker containers.

Implements SandboxPort against the local Docker daemon.
Each environment = one container. Provision pulls/runs an image,
execute runs commands inside it, terminate stops and removes it.
"""

from __future__ import annotations

import logging
import os
import uuid
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any

from .secret_mounts import DITTO_LICENSE_ENV

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "ubuntu:22.04"
_DEFAULT_SHELL = "/bin/sh"
_PEER_NETWORK_LOCK_DIR = Path.home() / ".cache" / "python-factory" / "peer-network-locks"


@contextmanager
def _peer_network_provision_lock(network_name: str):
    """Serialize peer-network check-and-attach across Sandbox processes.

    Alias inspection and Docker attachment are separate API calls. A stable
    host-local advisory lock keeps those calls atomic with respect to other
    Python Factory processes using the same Docker daemon.
    """
    import hashlib
    import stat

    _PEER_NETWORK_LOCK_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = _PEER_NETWORK_LOCK_DIR.lstat()
    current_uid = getattr(os, "getuid", None)
    if (not stat.S_ISDIR(directory.st_mode)
            or (current_uid is not None and directory.st_uid != current_uid())):
        raise RuntimeError("Peer-network lock directory is not a private owned directory")
    if directory.st_mode & 0o077:
        _PEER_NETWORK_LOCK_DIR.chmod(0o700)
    lock_name = hashlib.sha256(network_name.encode("utf-8")).hexdigest() + ".lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(_PEER_NETWORK_LOCK_DIR / lock_name, flags, 0o600)
    acquired = False
    try:
        if os.name == "nt":
            _acquire_windows_peer_network_lock(descriptor)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        acquired = True
        yield
    finally:
        try:
            if acquired:
                if os.name == "nt":
                    import msvcrt

                    os.lseek(descriptor, 0, os.SEEK_SET)
                    msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _acquire_windows_peer_network_lock(descriptor: int) -> None:
    """Wait until the Windows byte-range lock is available.

    ``LK_LOCK`` retries only for a short, fixed interval. Provisioning can
    take longer than that, so poll the nonblocking operation until it can
    safely proceed. OS process teardown releases the byte-range lock.
    """
    import errno
    import msvcrt
    import time

    if os.fstat(descriptor).st_size == 0:
        os.write(descriptor, b"\0")
    while True:
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            return
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EDEADLK}:
                raise
            time.sleep(0.1)


def _serialize_peer_network_provision(method):
    """Hold a cross-process lock for the whole check-and-attach transaction."""
    @wraps(method)
    async def wrapped(self, config):
        from ..peer_network import validate_peer_network

        spec = validate_peer_network(config.get("peer_network"))
        if spec is None:
            return await method(self, config)
        with _peer_network_provision_lock(spec.docker_network_name):
            return await method(self, config)

    return wrapped


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a subprocess synchronously, return (exit_code, stdout, stderr)."""
    import os
    import subprocess

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
            env={
                key: value for key, value in os.environ.items()
                if key != DITTO_LICENSE_ENV
            },
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

    @_serialize_peer_network_provision
    async def provision(self, config: dict[str, Any]) -> str:
        """Provision a new Docker container.

        Supports profile-based config: ports, entrypoint, container_name,
        env_vars. Falls back to random name + sleep infinity for backward compat.
        """
        image = config.get("image", self._default_image)
        container_name = config.get("container_name", f"sandbox-{uuid.uuid4().hex[:8]}")
        secret_mounts = config.get("secret_mounts", ())
        if secret_mounts:
            if config.get("auto_terminate", True) is not True:
                raise ValueError("Secret mounts require auto-termination")
            timeout_seconds = config.get("timeout_seconds", 3600)
            if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 86400:
                raise ValueError("Secret mounts require a timeout from 60 to 86400 seconds")
            import json

            from ..provision_context import (
                validate_secret_image_entrypoint,
                validate_secret_launch,
            )

            validate_secret_launch(image, config.get("entrypoint"))
            # An image name or registry digest can be replaced or pulled. A
            # local image ID is immutable and must already exist on this host.
            code, image_id, _ = _run([
                "docker", "image", "inspect", "--format", "{{.Id}}", image,
            ])
            if code != 0 or image_id.strip() != image:
                raise ValueError("Secret mount requires an available local image ID")
            code, image_entrypoint, _ = _run([
                "docker", "image", "inspect", "--format",
                "{{json .Config.Entrypoint}}", image,
            ])
            if code != 0:
                raise ValueError("Secret mount requires a trusted fixed image ENTRYPOINT")
            try:
                validate_secret_image_entrypoint(json.loads(image_entrypoint))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Secret mount requires a trusted fixed image ENTRYPOINT"
                ) from exc
        # Validate the whole network boundary before replacement/removal or
        # network creation. Profiles and direct adapter callers share this.
        from ..peer_network import validate_peer_network

        peer_network = validate_peer_network(config.get("peer_network"))
        if secret_mounts and (
            config.get("replace_existing", True)
            or peer_network is None or not peer_network.internal
            or config.get("ports")
        ):
            raise ValueError(
                "Secret mounts require a new container on an internal peer network without published ports"
            )
        if peer_network is not None and peer_network.internal and config.get("ports"):
            raise ValueError(
                "Internal peer networks cannot publish ports to the host"
            )
        device_labels: dict[str, str] = {}
        if config.get("device_labels") is not None:
            from ..device_presets import DeviceRunLabels

            device_labels = DeviceRunLabels.model_validate(
                config["device_labels"]
            ).docker_labels()

        if config.get("replace_existing", True):
            # Legacy profiles intentionally replace a container with this name.
            if peer_network is not None:
                self._ensure_peer_network(peer_network)
                self._assert_peer_alias_available(peer_network, container_name)
            _run(["docker", "rm", "-f", container_name], timeout=10)
        else:
            code, _, _ = _run(
                ["docker", "container", "inspect", container_name], timeout=10,
            )
            if code == 0:
                raise RuntimeError(
                    f"Container {container_name!r} already exists; "
                    "terminate it explicitly before provisioning again"
                )
            if peer_network is not None:
                self._ensure_peer_network(peer_network)
                self._assert_peer_alias_available(peer_network, container_name)

        from .secret_mounts import build_secret_mount_args
        from .uds_mount import build_mount_args, proxy_env

        cmd = ["docker", "run", "-d", "--name", container_name,
               "--label", "factory.sandbox=true"]
        if peer_network is not None:
            for key, value in {
                "factory.sandbox.peer_network_id": peer_network.network_id,
                "factory.sandbox.peer_network_name": peer_network.docker_network_name,
                "factory.sandbox.peer_alias": peer_network.alias,
                "factory.sandbox.peer_port": str(peer_network.port),
                "factory.sandbox.peer_internal": str(peer_network.internal).lower(),
            }.items():
                cmd.extend(["--label", f"{key}={value}"])
        if secret_mounts:
            # Non-sensitive marker lets execution suppress output even if the
            # local environment metadata store is unavailable after restart.
            cmd.extend([
                "--label", "factory.sandbox.secret_output_suppressed=true",
                "--label", f"factory.sandbox.timeout_seconds={timeout_seconds}",
            ])
        for key, value in device_labels.items():
            cmd.extend(["--label", f"{key}={value}"])
        if platform := config.get("platform"):
            cmd.extend(["--platform", platform])
        if cpus := config.get("cpus"):
            cmd.extend(["--cpus", str(cpus)])
        if memory_mb := config.get("memory_mb"):
            cmd.extend(["--memory", f"{memory_mb}m"])
        if peer_network is not None:
            cmd.extend(["--network", peer_network.docker_network_name])
            cmd.extend(["--network-alias", peer_network.alias])
        if policy_id := config.get("env_vars", {}).get("MCP_POLICY_ID"):
            cmd.extend(["--label", f"factory.workload={policy_id}"])
        cmd.extend(build_mount_args(config))
        cmd.extend(build_secret_mount_args(secret_mounts))

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
            if peer_network is not None:
                self._remove_empty_owned_peer_network(
                    peer_network.docker_network_name,
                )
            if secret_mounts:
                # Docker diagnostics can echo bind source paths. Do not expose
                # those host paths through Sandbox logs or the MCP error.
                logger.error("Docker provision failed with a configured secret mount")
                raise RuntimeError(
                    "Docker provision failed while attaching a configured secret"
                )
            logger.error("Docker provision failed: %s", stderr)
            raise RuntimeError(f"Docker provision failed: {stderr.strip()}")

        container_id = stdout.strip()
        self._containers[container_name] = {
            "container_id": container_id,
            "image": image,
            "status": "running",
        }
        if peer_network is not None:
            self._containers[container_name]["peer_network"] = peer_network.public_metadata()
        logger.info("Provisioned container %s (%s)", container_name, image)
        return container_name

    async def terminate(self, env_id: str) -> None:
        """Stop and remove a Docker container."""
        peer_network = self._peer_network_for_container(env_id)
        _run(["docker", "rm", "-f", env_id], timeout=30)
        if peer_network is not None:
            self._remove_empty_owned_peer_network(peer_network["network_name"])
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
        result: dict[str, Any] = {
            "status": status, "public_ip": None, "private_ip": None,
        }
        network = self._peer_network_for_container(env_id)
        if network is not None:
            result["peer_network"] = network
        return result

    @staticmethod
    def _ensure_peer_network(spec: Any) -> None:
        """Create a managed bridge or require an existing one to be ours."""
        name = spec.docker_network_name
        code, stdout, _ = _run([
            "docker", "network", "inspect", "--format",
            '{{ index .Labels "factory.sandbox.owner" }}|{{.Internal}}', name,
        ])
        if code == 0:
            expected = f"python-factory|{str(spec.internal).lower()}"
            if stdout.strip() != expected:
                raise RuntimeError(
                    f"Docker network {name!r} is not Sandbox-owned or has a different internal mode"
                )
            return
        create = ["docker", "network", "create", "--driver", "bridge"]
        if spec.internal:
            create.append("--internal")
        create.extend([
            "--label", "factory.sandbox=true",
            "--label", "factory.sandbox.owner=python-factory",
            "--label", f"factory.sandbox.peer_network_id={spec.network_id}",
            name,
        ])
        code, _, stderr = _run(create)
        if code != 0:
            # A concurrent provision may have created it; accept only an
            # explicitly Sandbox-owned network after re-inspection.
            check, owner, _ = _run([
                "docker", "network", "inspect", "--format",
                '{{ index .Labels "factory.sandbox.owner" }}|{{.Internal}}', name,
            ])
            expected = f"python-factory|{str(spec.internal).lower()}"
            if check == 0 and owner.strip() == expected:
                return
            raise RuntimeError(f"Could not create Sandbox peer network {name!r}: {stderr.strip()}")

    @staticmethod
    def _assert_peer_alias_available(spec: Any, container_name: str) -> None:
        """Reject aliases already bound by a different attached container."""
        network_name = spec.docker_network_name
        code, stdout, _ = _run([
            "docker", "network", "inspect", "--format",
            "{{json .Containers}}", network_name,
        ])
        if code != 0:
            raise RuntimeError(
                f"Could not verify peer alias on Docker network {network_name!r}"
            )
        import json

        try:
            containers = json.loads(stdout or "{}") or {}
            if not isinstance(containers, dict):
                raise TypeError("Docker network container listing is not an object")
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Could not verify peer alias on Docker network {network_name!r}"
            ) from exc

        for container in containers.values():
            attached_name = container.get("Name") if isinstance(container, dict) else None
            if not attached_name:
                raise RuntimeError(
                    f"Could not verify aliases for a container on {network_name!r}"
                )
            if attached_name == container_name:
                continue
            code, stdout, _ = _run([
                "docker", "inspect", "--format",
                "{{json .NetworkSettings.Networks}}", attached_name,
            ])
            if code != 0:
                raise RuntimeError(
                    f"Could not verify aliases for attached peer {attached_name!r}"
                )
            try:
                networks = json.loads(stdout or "{}") or {}
                network_config = networks.get(network_name)
                aliases = (
                    network_config.get("Aliases")
                    if isinstance(network_config, dict) else None
                )
                if not isinstance(aliases, list) or not all(
                    isinstance(alias, str) for alias in aliases
                ):
                    raise ValueError("Docker network aliases are unavailable")
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Could not verify aliases for attached peer {attached_name!r}"
                ) from exc
            if spec.alias in aliases:
                raise ValueError(
                    f"Peer alias {spec.alias!r} is already attached to another container"
                )

    @staticmethod
    def _peer_network_for_container(env_id: str) -> dict[str, Any] | None:
        """Read peer endpoint labels from a container, including after restart."""
        code, stdout, _ = _run([
            "docker", "inspect", "--format",
            '{{json .Config.Labels}}', env_id,
        ])
        if code != 0:
            return None
        import json

        try:
            labels = json.loads(stdout)
            raw = {
                "network_id": labels["factory.sandbox.peer_network_id"],
                "alias": labels["factory.sandbox.peer_alias"],
                "port": int(labels["factory.sandbox.peer_port"]),
                "internal": labels["factory.sandbox.peer_internal"] == "true",
            }
            from ..peer_network import validate_peer_network

            spec = validate_peer_network(raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        assert spec is not None
        return spec.public_metadata()

    @staticmethod
    def _remove_empty_owned_peer_network(network_name: str) -> None:
        """Remove only an empty managed bridge; Docker arbitrates races."""
        code, stdout, _ = _run([
            "docker", "network", "inspect", "--format",
            '{{ index .Labels "factory.sandbox.owner" }}|{{json .Containers}}',
            network_name,
        ])
        if code != 0:
            return
        owner, _, attached_json = stdout.strip().partition("|")
        if owner != "python-factory":
            return
        import json

        try:
            attached = json.loads(attached_json)
        except json.JSONDecodeError:
            return
        if attached:
            return
        # If a peer joins after inspect, Docker refuses removal while attached.
        _run(["docker", "network", "rm", network_name], timeout=10)

    def get_secret_output_suppression(self, env_id: str) -> bool | None:
        """Read the marker; ``None`` means Docker could not verify the label."""
        code, stdout, _ = _run([
            "docker", "inspect", "--format",
            '{{ index .Config.Labels "factory.sandbox.secret_output_suppressed" }}',
            env_id,
        ])
        if code != 0:
            return None
        marker = stdout.strip()
        if marker == "true":
            return True
        if marker in {"false", "", "<no value>"}:
            return False
        return None

    async def execute(
        self, env_id: str, command: str, timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        """Execute a command unless secret state is enabled or unverifiable."""
        if self.get_secret_output_suppression(env_id) is not False:
            return {
                "exit_code": 126,
                "stdout": "",
                "stderr": (
                    "Execution is disabled for secret-enabled or unverified sandboxes"
                ),
                "duration_ms": 0,
            }
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
        if self.get_secret_output_suppression(env_id) is not False:
            return {
                "success": False,
                "error": "File operations are disabled for secret-enabled or unverified sandboxes",
            }
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
        if self.get_secret_output_suppression(env_id) is not False:
            return {
                "success": False,
                "error": "File operations are disabled for secret-enabled or unverified sandboxes",
            }
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
        if self.get_secret_output_suppression(env_id) is not False:
            return []
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
