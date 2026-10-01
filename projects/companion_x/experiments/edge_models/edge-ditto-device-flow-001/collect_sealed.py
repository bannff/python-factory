"""Collect only verified N=2 evidence from one stopped, sealed Ditto container."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import uuid
from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import contracts
import run as runner

HERE = Path(__file__).resolve().parent
SOURCE_FILES = frozenset({"run.py", "peer.py", "contracts.py", "protocol.md",
                          "scenario-n2.json", "model.json", "cohort.json"})
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}\Z")
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
NETWORK = "factory-sandbox-edge-n2-sdk-lab"
SECRET_TARGET = "/run/secrets/ditto-offline-license"
REMOTE_ROOT = "/evidence/run-001"
MAX_FILE_BYTES = 1_048_576
MAX_DOCKER_BYTES = MAX_FILE_BYTES + 65_536


class CollectionError(ValueError):
    """Evidence failed a host-side integrity or provenance check."""


class SealedExitError(CollectionError):
    """A verified sealed container stopped without a complete run."""

    def __init__(self, exit_code: int):
        super().__init__("sealed container exited without complete run evidence")
        self.exit_code = exit_code


class IncompleteEvidenceError(CollectionError):
    """A verified run exit did not leave all four declared evidence files."""

    def __init__(self, exit_code: int):
        super().__init__("sealed run left incomplete evidence")
        self.exit_code = exit_code


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise CollectionError("duplicate JSON key")
        value[key] = item
    return value


def _json(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(CollectionError("nonfinite JSON")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CollectionError("invalid JSON evidence") from error


def _host_file(path: Path) -> bytes:
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode) or path.stat().st_size > MAX_FILE_BYTES:
        raise CollectionError("host evidence is not a bounded regular file")
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise CollectionError("host evidence is oversized")
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@contextmanager
def _container_lock(container_id: str):
    """Serialize collector with the Sandbox host sweeper for this Docker ID."""
    base = Path(os.environ.get("SANDBOX_TMP_ROOT", "/tmp/factory-sandbox"))
    directory = base / "collector-locks"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory_stat = directory.lstat()
    if (not stat.S_ISDIR(directory_stat.st_mode)
            or directory_stat.st_uid != os.getuid()
            or directory_stat.st_mode & 0o077):
        raise CollectionError("container lock directory is not private")
    path = directory / f"{container_id}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        lock_stat = os.fstat(descriptor)
        if (not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != os.getuid()
                or lock_stat.st_mode & 0o077):
            raise CollectionError("container lock is not a regular file")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


class DockerBoundary:
    """Small Docker CLI boundary; never requests logs or container secrets."""

    def _output(self, args: tuple[str, ...], limit: int = MAX_DOCKER_BYTES) -> bytes:
        process = subprocess.Popen(["docker", *args], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL)
        chunks: list[bytes] = []
        size = 0
        deadline = time.monotonic() + 30
        try:
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    ready = selector.select(max(0, deadline - time.monotonic()))
                    if not ready:
                        raise CollectionError("Docker operation timed out")
                    chunk = os.read(process.stdout.fileno(), min(65_536, limit + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > limit:
                        raise CollectionError("Docker response is oversized")
            if process.wait(timeout=max(0.1, deadline - time.monotonic())) != 0:
                raise CollectionError("Docker operation failed")
            return b"".join(chunks)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def inspect(self, container_id: str) -> dict[str, Any]:
        value = _json(self._output(("inspect", "--type", "container", container_id)))
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise CollectionError("container inspect schema is invalid")
        return value[0]

    def wait(self, container_id: str) -> int:
        output = self._output(("wait", container_id), 64).strip()
        if not re.fullmatch(rb"[0-9]{1,3}", output):
            raise CollectionError("container wait result is invalid")
        return int(output)

    def network(self, network_id: str) -> dict[str, Any]:
        value = _json(self._output(("network", "inspect", network_id)))
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise CollectionError("network inspect schema is invalid")
        return value[0]

    def copy_tar(self, container_id: str, relative_path: str) -> bytes:
        return self._output(("cp", f"{container_id}:{REMOTE_ROOT}/{relative_path}", "-"))

    def remove(self, container_id: str) -> None:
        self._output(("rm", "-f", container_id), 128)

    def remove_network(self, network_id: str) -> None:
        self._output(("network", "rm", network_id), 128)


def _build_identity(build_path: Path, scenario_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    runner._verify_startup_source(runner.CODE_SOURCES, runner.STARTUP_SOURCE_SHA256)
    build = _json(_host_file(build_path))
    pins = _json(_host_file(HERE / "sealed_pins.json"))
    scenario_bytes = _host_file(scenario_path)
    scenario = contracts.validate_scenario(contracts.parse_json_bytes(scenario_bytes))
    if (not isinstance(build, dict) or not isinstance(pins, dict)
            or type(build.get("schema_version")) is not int or build["schema_version"] != 1
            or build.get("status") != "license_free_preflight_passed"
            or not isinstance(build.get("final_image_id"), str)
            or IMAGE_ID.fullmatch(build["final_image_id"]) is None
            or build.get("platform") != "linux/arm64"
            or not isinstance(build.get("source_sha256"), dict)
            or type(pins.get("schema_version")) is not int or pins["schema_version"] != 1
            or set(pins) != {"schema_version", "sdk_distribution_sha256",
                             "entrypoint_sha256", "files"}
            or not isinstance(pins.get("files"), dict)
            or set(build["source_sha256"]) != SOURCE_FILES
            or set(pins.get("files", {})) != SOURCE_FILES
            or build["source_sha256"] != pins["files"]
            or not isinstance(pins.get("entrypoint_sha256"), str)
            or HASH.fullmatch(pins["entrypoint_sha256"]) is None
            or build.get("entrypoint_sha256") != pins["entrypoint_sha256"]
            or not isinstance(build.get("context_sha256"), dict)
            or build["context_sha256"].get("entrypoint.py") != pins["entrypoint_sha256"]
            or any(build["context_sha256"].get(name) != digest
                   for name, digest in build["source_sha256"].items())
            or any(not isinstance(digest, str) or HASH.fullmatch(digest) is None
                   for digest in pins["files"].values())
            or build.get("sdk_distribution_sha256") != scenario["sdk_distribution_sha256"]
            or pins.get("sdk_distribution_sha256") != scenario["sdk_distribution_sha256"]
            or not isinstance(build.get("preflight"), dict)
            or build["preflight"].get("status") != "passed"
            or build["preflight"].get("license_used") is not False
            or build["preflight"].get("peers_launched") is not False
            or not isinstance(build.get("profile"), dict)
            or build["profile"].get("image") != build["final_image_id"]
            or not isinstance(build["profile"].get("peer_network"), dict)
            or build["profile"].get("name") != "edge-n2-sdk"
            or build["profile"].get("container_name") != "edge-n2-sdk"
            or build["profile"].get("secret_refs") != ["ditto-offline-license"]
            or build["profile"]["peer_network"] != {
                "network_id": "edge-n2-sdk-lab", "alias": "edge-n2-sdk",
                "port": 17331, "internal": True}):
        raise CollectionError("build identity or source pins are invalid")
    for name in ("run.py", "peer.py", "contracts.py", "protocol.md"):
        if _sha(_host_file(HERE / name)) != pins["files"][name]:
            raise CollectionError("local verifier source differs from sealed source")
    if _sha(scenario_bytes) != pins["files"]["scenario-n2.json"]:
        raise CollectionError("scenario differs from sealed source")
    if _sha(_host_file(HERE / "sealed_entrypoint.py")) != pins["entrypoint_sha256"]:
        raise CollectionError("local sealed entrypoint differs from build")
    return build, scenario


def _expected_predictions(scenario: dict[str, Any], build: dict[str, Any],
                          model_path: Path, cohort_path: Path) -> dict[str, dict[str, Any]]:
    if (_sha(_host_file(model_path)) != build["source_sha256"]["model.json"]
            or _sha(_host_file(cohort_path)) != build["source_sha256"]["cohort.json"]):
        raise CollectionError("local model or cohort differs from sealed source")
    model, cohort = contracts.load_pinned_artifacts(scenario, model_path, cohort_path)
    scores = contracts.verify_parity(model, cohort)
    if len(scores) != 100:
        raise CollectionError("sealed cohort parity is incomplete")
    predicted = {}
    for peer in scenario["peers"]:
        document = contracts.observation_document(
            scenario, peer, model, cohort, scores[peer["engine_id"]]
        )
        identity = _sha(document["_id"].encode())
        predicted[identity] = {
            "observation_id_sha256": identity,
            "input_id_sha256": document["input_id_sha256"],
            "probability": document["probability"],
            "decision": document["decision"],
        }
    return predicted


def _container_identity(value: dict[str, Any], container_id: str, image_id: str) -> str:
    state = value.get("State")
    mounts = value.get("Mounts")
    settings = value.get("NetworkSettings")
    networks = settings.get("Networks") if isinstance(settings, dict) else None
    config = value.get("Config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    host = value.get("HostConfig")
    expected_labels = {
        "factory.sandbox": "true",
        "factory.sandbox.peer_network_id": "edge-n2-sdk-lab",
        "factory.sandbox.peer_network_name": NETWORK,
        "factory.sandbox.peer_alias": "edge-n2-sdk",
        "factory.sandbox.peer_port": "17331",
        "factory.sandbox.peer_internal": "true",
        "factory.sandbox.secret_output_suppressed": "true",
    }
    if (value.get("Id") != container_id or value.get("Image") != image_id
            or value.get("Name") != "/edge-n2-sdk"
            or not isinstance(labels, dict)
            or any(labels.get(key) != expected for key, expected in expected_labels.items())
            or config.get("Entrypoint") != ["/usr/local/bin/python", "/sealed/entrypoint.py"]
            or config.get("Cmd") != ["run"]
            or not isinstance(host, dict)
            or host.get("NetworkMode") != NETWORK
            or host.get("Privileged") is not False
            or host.get("PublishAllPorts") is not False
            or host.get("PortBindings") not in ({}, None)
            or settings is None or not isinstance(settings.get("Ports"), (dict, type(None)))
            or bool(settings.get("Ports"))
            or not isinstance(state, dict) or state.get("Running") is not False
            or state.get("Status") != "exited" or type(state.get("ExitCode")) is not int
            or not 0 <= state["ExitCode"] <= 255 or not isinstance(mounts, list)
            or len([mount for mount in mounts if isinstance(mount, dict)
                    and mount.get("Destination") == SECRET_TARGET]) != 1
            or not any(mount.get("Destination") == SECRET_TARGET
                       and mount.get("Type") == "bind" and mount.get("RW") is False
                       for mount in mounts if isinstance(mount, dict))
            or not isinstance(networks, dict) or set(networks) != {NETWORK}
            or not isinstance(networks[NETWORK], dict)
            or not isinstance(networks[NETWORK].get("Aliases"), list)
            or "edge-n2-sdk" not in networks[NETWORK]["Aliases"]):
        raise CollectionError("stopped container identity or isolation is invalid")
    network_id = networks[NETWORK].get("NetworkID")
    if not isinstance(network_id, str) or not re.fullmatch(r"[0-9a-f]{64}", network_id):
        raise CollectionError("container network identity is invalid")
    return network_id


def _tar_file(data: bytes, expected_name: str) -> bytes:
    import io

    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
            members = archive.getmembers()
            if len(members) != 1:
                raise CollectionError("Docker copy is not a single file")
            member = members[0]
            if (member.name.removeprefix("./") != expected_name or not member.isfile()
                    or member.size > MAX_FILE_BYTES):
                raise CollectionError("Docker copy is not the requested regular file")
            stream = archive.extractfile(member)
            if stream is None:
                raise CollectionError("Docker copy has no file bytes")
            content = stream.read(MAX_FILE_BYTES + 1)
            if len(content) != member.size or len(content) > MAX_FILE_BYTES:
                raise CollectionError("Docker copy file size is invalid")
            return content
    except tarfile.TarError as error:
        raise CollectionError("Docker copy archive is invalid") from error


def _remove_empty_owned_network(boundary: DockerBoundary, network_id: str) -> bool:
    network = boundary.network(network_id)
    labels = network.get("Labels")
    if (network.get("Id") != network_id or network.get("Name") != NETWORK
            or network.get("Internal") is not True or not isinstance(labels, dict)
            or labels.get("factory.sandbox.owner") != "python-factory"
            or labels.get("factory.sandbox.peer_network_id") != "edge-n2-sdk-lab"
            or not isinstance(network.get("Containers"), dict)):
        raise CollectionError("managed network identity changed before cleanup")
    if network["Containers"]:
        return False
    boundary.remove_network(network_id)
    return True


def _validate_files(files: dict[str, bytes], scenario: dict[str, Any],
                    build: dict[str, Any],
                    expected_predictions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    index = _json(files["run-index.json"])
    manifest = _json(files["run-manifest.json"])
    peer_ids = [peer["peer_id"] for peer in scenario["peers"]]
    names = [f"peer-results/{peer_id}.json" for peer_id in peer_ids]
    peers = [_json(files[name]) for name in names]
    expected_index = {"schema_version", "run_id", "status", "performance_status",
                      "run_manifest_sha256", "scenario_sha256", "runner_sha256",
                      "peer_runner_sha256", "contracts_sha256", "protocol_sha256"}
    expected_manifest = {
        "schema_version", "run_id", "scenario_id", "scenario_sha256", "artifact_hashes",
        "preflight", "topology", "source_timestamps_available", "source_timestamp_note",
        "sdk_integration_verified", "metrics_policy", "performance", "eng184_closure_ready",
        "status", "performance_status", "peers", "ephemeral_store_sha256",
        "files_sha256", "finished_at_utc",
    }
    if (not isinstance(index, dict) or set(index) != expected_index
            or type(index["schema_version"]) is not int or index["schema_version"] != 1
            or not isinstance(manifest, dict) or set(manifest) != expected_manifest
            or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1
            or index["run_manifest_sha256"] != _sha(files["run-manifest.json"])
            or index["scenario_sha256"] != build["source_sha256"]["scenario-n2.json"]
            or manifest.get("scenario_sha256") != index["scenario_sha256"]
            or manifest.get("scenario_id") != scenario["scenario_id"]
            or manifest.get("run_id") != index["run_id"]
            or manifest.get("metrics_policy") != scenario["metrics_policy"]
            or not isinstance(manifest.get("artifact_hashes"), dict)
            or manifest["artifact_hashes"].get("sdk_distribution_sha256")
               != build["sdk_distribution_sha256"]
            or manifest["artifact_hashes"].get("model_file_sha256")
               != build["source_sha256"]["model.json"]
            or manifest["artifact_hashes"].get("cohort_file_sha256")
               != build["source_sha256"]["cohort.json"]
            or manifest["artifact_hashes"].get("model_payload_sha256")
               != scenario["model"]["payload_sha256"]
            or manifest["artifact_hashes"].get("cohort_payload_sha256")
               != scenario["cohort"]["payload_sha256"]
            or set(manifest["artifact_hashes"]) != {
                "model_file_sha256", "model_payload_sha256", "cohort_file_sha256",
                "cohort_payload_sha256", "sdk_distribution_sha256"}
            or manifest.get("preflight") != {
                "status": "passed", "parity_rows": 100,
                "selected_engine_ids": scenario["cohort"]["engine_ids"]}
            or manifest.get("source_timestamps_available") is not False
            or manifest.get("source_timestamp_note") !=
               "The frozen FD001 endpoint cohort contains no event timestamp; none was inferred."
            or not isinstance(manifest.get("ephemeral_store_sha256"), dict)
            or set(manifest["ephemeral_store_sha256"]) != set(peer_ids)
            or any(not isinstance(value, str) or HASH.fullmatch(value) is None
                   for value in manifest["ephemeral_store_sha256"].values())
            or manifest.get("files_sha256") != {name: _sha(files[name]) for name in names}
            or manifest.get("peers") != peers
            or index["runner_sha256"] != build["source_sha256"]["run.py"]
            or index["peer_runner_sha256"] != build["source_sha256"]["peer.py"]
            or index["contracts_sha256"] != build["source_sha256"]["contracts.py"]
            or index["protocol_sha256"] != build["source_sha256"]["protocol.md"]):
        raise CollectionError("run index, manifest, or source hashes differ")
    try:
        if str(uuid.UUID(index["run_id"])) != index["run_id"]:
            raise ValueError("noncanonical run ID")
        finished = datetime.fromisoformat(manifest["finished_at_utc"])
        if finished.utcoffset() is None or finished.utcoffset().total_seconds() != 0:
            raise ValueError("finish time is not UTC")
    except (ValueError, TypeError, AttributeError) as error:
        raise CollectionError("run identity or finish time is invalid") from error
    topology = manifest.get("topology")
    if (not isinstance(topology, dict) or set(topology) != {"transport", "mode", "peer_count", "peers"}
            or topology["transport"] != "static_tcp" or topology["mode"] != "loopback"
            or topology["peer_count"] != 2 or not isinstance(topology["peers"], list)
            or len(topology["peers"]) != 2):
        raise CollectionError("run topology differs from sealed N=2 topology")
    validated = []
    for peer, spec, expected_topology in zip(peers, scenario["peers"], topology["peers"], strict=True):
        if not isinstance(peer, dict):
            raise CollectionError("peer result is invalid")
        candidate = peer
        if peer.get("status") == "failed":
            if set(peer) != {"status", "peer_id", "error_type", "write_failures"} or (
                peer["peer_id"] != spec["peer_id"]
            ):
                raise CollectionError("failed peer result is invalid")
            candidate = {key: value for key, value in peer.items() if key != "peer_id"}
        item = runner._validated_result(
            candidate, spec["peer_id"], expected_topology, expected_predictions,
            expected_sdk_digest=build["sdk_distribution_sha256"],
            expected_device_digest=_sha(spec["device_id"].encode()),
        )
        if item is None:
            raise CollectionError("peer result fails bounded contract")
        validated.append(item)
    computed_status = "passed" if all(peer["status"] == "passed" for peer in validated) else "failed"
    performance = runner.summarize_performance(validated, scenario["metrics_policy"])
    if (manifest.get("status") != computed_status or index["status"] != computed_status
            or manifest.get("sdk_integration_verified") is not (computed_status == "passed")
            or manifest.get("performance") != performance
            or manifest.get("performance_status") != performance["status"]
            or index["performance_status"] != performance["status"]
            or manifest.get("eng184_closure_ready") is not
               (computed_status == "passed" and performance["closure_ready"])):
        raise CollectionError("run outcomes or recomputed performance differ")
    return {"status": computed_status, "performance_status": performance["status"],
            "eng184_closure_ready": computed_status == "passed" and performance["closure_ready"],
            "run_id": index["run_id"]}


def _collect_locked(container_id: str, build_path: Path, scenario_path: Path,
                    model_path: Path, cohort_path: Path, output: Path,
                    docker: DockerBoundary) -> dict[str, Any]:
    boundary = docker
    if output.exists() or output.is_symlink():
        raise CollectionError("evidence output must be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise CollectionError("evidence output parent is invalid")
    files: dict[str, bytes] = {}
    result: dict[str, Any]
    owned = False
    network_removed = False
    network_cleanup = "not_attempted"
    try:
        build, scenario = _build_identity(build_path, scenario_path)
        expected_predictions = _expected_predictions(scenario, build, model_path, cohort_path)
        first = boundary.inspect(container_id)
        network_id = _container_identity(first, container_id, build["final_image_id"])
        network = boundary.network(network_id)
        if (network.get("Id") != network_id or network.get("Name") != NETWORK
                or network.get("Internal") is not True
                or not isinstance(network.get("Labels"), dict)
                or network["Labels"].get("factory.sandbox.owner") != "python-factory"
                or network["Labels"].get("factory.sandbox.peer_network_id") != "edge-n2-sdk-lab"):
            raise CollectionError("peer network is not the declared internal Sandbox network")
        owned = True
        exit_code = first["State"]["ExitCode"]
        waited_code = boundary.wait(container_id)
        if exit_code != waited_code:
            raise CollectionError("sealed container exit status changed")
        second = boundary.inspect(container_id)
        if (_container_identity(second, container_id, build["final_image_id"]) != network_id
                or second["State"]["ExitCode"] != exit_code):
            raise CollectionError("container identity changed after wait")
        if exit_code not in (0, 1):
            raise SealedExitError(exit_code)
        names = ["run-index.json", "run-manifest.json"] + [
            f"peer-results/{peer['peer_id']}.json" for peer in scenario["peers"]
        ]
        for name in names:
            try:
                files[name] = _tar_file(boundary.copy_tar(container_id, name), Path(name).name)
            except (CollectionError, OSError) as error:
                raise IncompleteEvidenceError(exit_code) from error
        result = _validate_files(files, scenario, build, expected_predictions)
        if ((exit_code == 0 and result["status"] != "passed")
                or (exit_code == 1 and (result["status"] != "failed"
                                        or result["eng184_closure_ready"]))):
            raise CollectionError("container exit code disagrees with validated run status")
    finally:
        if owned:
            boundary.remove(container_id)
            try:
                network_removed = _remove_empty_owned_network(boundary, network_id)
                network_cleanup = "removed" if network_removed else "nonempty"
            except (CollectionError, OSError, TypeError, KeyError, ValueError):
                network_cleanup = "failed"
    result["managed_network_removed"] = network_removed
    result["managed_network_cleanup"] = network_cleanup
    temporary = Path(tempfile.mkdtemp(prefix=".edge-n2-collect-", dir=output.parent))
    try:
        for name, content in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        os.replace(temporary, output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return result


def collect(container_id: str, build_path: Path, scenario_path: Path,
            model_path: Path, cohort_path: Path, output: Path,
            docker: DockerBoundary | None = None) -> dict[str, Any]:
    if CONTAINER_ID.fullmatch(container_id) is None:
        raise CollectionError("container ID must be a full Docker hex ID")
    with _container_lock(container_id):
        return _collect_locked(container_id, build_path, scenario_path,
                               model_path, cohort_path, output,
                               docker or DockerBoundary())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-id", required=True)
    parser.add_argument("--build-evidence", type=Path, required=True)
    parser.add_argument("--scenario", type=Path, default=HERE / "scenario-n2.json")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = collect(args.container_id, args.build_evidence, args.scenario,
                         args.model, args.cohort, args.output)
    except SealedExitError as error:
        print(json.dumps({"status": "rejected", "reason": "sealed_exit_without_complete_run",
                          "exit_code": error.exit_code}, sort_keys=True))
        return 2
    except IncompleteEvidenceError as error:
        print(json.dumps({"status": "rejected", "reason": "incomplete_run_evidence",
                          "exit_code": error.exit_code}, sort_keys=True))
        return 2
    except (CollectionError, OSError, TypeError, KeyError, ValueError):
        print(json.dumps({"status": "rejected", "reason": "integrity_check_failed"}, sort_keys=True))
        return 2
    print(json.dumps({"status": "collected", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
