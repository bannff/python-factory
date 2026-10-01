"""Host-side, bounded collection of one stopped sealed routing SDK run.

This phase validates evidence shape and replay but does not grant SDK provenance
or issue a reviewer receipt. The sibling sealed image/launcher is still required.
"""

from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_SPEC = importlib.util.spec_from_file_location(
    "edge_routing_collection_schema", Path(__file__).with_name("collection_schema.py")
)
assert _SPEC is not None and _SPEC.loader is not None
contracts = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault(_SPEC.name, contracts)
_SPEC.loader.exec_module(contracts)
attestation = contracts.attestation
schema = contracts.schema
records = contracts.records

NETWORK_ID = "edge-routing-sdk-lab"
NETWORK = "factory-sandbox-edge-routing-sdk-lab"
ALIAS = "edge-routing-sdk"
SECRET_TARGET = "/run/secrets/ditto-offline-license"
REMOTE_ROOT = "/evidence/routing-run-001"
MAX_FILE_BYTES = 1_048_576
MAX_DOCKER_BYTES = MAX_FILE_BYTES + 65_536
MAX_TREE_BYTES = 3 * MAX_FILE_BYTES + 131_072
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")


class CollectionError(ValueError):
    """Host collection rejected insufficient or changed evidence."""


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sync_path(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if path.is_dir():
        flags |= getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_tree(root: Path) -> None:
    paths = tuple(root.rglob("*"))
    for path in paths:
        if path.is_file():
            _sync_path(path)
    for path in sorted((root, *(p for p in paths if p.is_dir())),
                       key=lambda item: len(item.parts), reverse=True):
        _sync_path(path)
    _sync_path(root.parent)


def expected_labels() -> dict[str, str]:
    return {"factory.sandbox": "true", "factory.sandbox.peer_network_id": NETWORK_ID,
            "factory.sandbox.peer_network_name": NETWORK, "factory.sandbox.peer_alias": ALIAS,
            "factory.sandbox.peer_internal": "true",
            "factory.sandbox.secret_output_suppressed": "true"}


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CollectionError("duplicate JSON key")
        result[key] = value
    return result


def _json(value: bytes) -> Any:
    try:
        return json.loads(value.decode("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(CollectionError("nonfinite JSON")))
    except (UnicodeError, json.JSONDecodeError):
        raise CollectionError("invalid JSON evidence") from None


@contextmanager
def _container_lock(container_id: str):
    root = Path(os.environ.get("SANDBOX_TMP_ROOT", "/tmp/factory-sandbox")) / "collector-locks"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise CollectionError("collector lock directory is not private")
    fd = os.open(root / f"{container_id}.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise CollectionError("collector lock is not private")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


class DockerBoundary:
    """Docker CLI boundary with bounded output, timeout, and suppressed stderr."""

    def _output(self, args: tuple[str, ...], limit: int = MAX_DOCKER_BYTES) -> bytes:
        process = subprocess.Popen(["docker", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        parts: list[bytes] = []
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
                    size += len(chunk)
                    if size > limit:
                        raise CollectionError("Docker response is oversized")
                    parts.append(chunk)
            if process.wait(timeout=max(0.1, deadline - time.monotonic())) != 0:
                raise CollectionError("Docker operation failed")
            return b"".join(parts)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def inspect(self, container_id: str) -> dict[str, Any]:
        value = _json(self._output(("inspect", "--type", "container", container_id)))
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise CollectionError("invalid Docker container inspect response")
        return value[0]

    def network(self, network_id: str) -> dict[str, Any]:
        value = _json(self._output(("network", "inspect", network_id)))
        if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
            raise CollectionError("invalid Docker network inspect response")
        return value[0]

    def wait(self, container_id: str) -> int:
        value = self._output(("wait", container_id), 64).strip()
        if re.fullmatch(rb"[0-9]{1,3}", value) is None:
            raise CollectionError("invalid Docker wait response")
        return int(value)

    def copy_tree(self, container_id: str) -> bytes:
        return self._output(("cp", f"{container_id}:{REMOTE_ROOT}", "-"), MAX_TREE_BYTES)

    def remove(self, container_id: str) -> None:
        # `rm` fails if another actor restarted it after the final inspect.
        self._output(("rm", container_id), 128)

    def remove_network(self, network_id: str) -> None:
        self._output(("network", "rm", network_id), 128)


def _container_identity(value: dict[str, Any], container_id: str,
                        policy: contracts.CollectionPolicy) -> int:
    state, config, host, settings = (value.get(key) for key in ("State", "Config", "HostConfig", "NetworkSettings"))
    networks = settings.get("Networks") if isinstance(settings, dict) else None
    mounts = value.get("Mounts")
    if (value.get("Id") != container_id or value.get("Image") != "sha256:" + policy.pins.image_sha256
            or value.get("Name") != "/edge-routing-sdk"
            or not isinstance(state, dict) or state.get("Running") is not False
            or state.get("Status") != "exited" or type(state.get("ExitCode")) is not int
            or not 0 <= state["ExitCode"] <= 255
            or not isinstance(config, dict) or not isinstance(config.get("Labels"), dict)
            or any(config["Labels"].get(key) != expected for key, expected in expected_labels().items())
            or config.get("Entrypoint") != ["/usr/local/bin/python", "/sealed/entrypoint.py"]
            or config.get("Cmd") != ["run"]
            or not isinstance(host, dict) or host.get("NetworkMode") != NETWORK
            or host.get("NanoCpus") != policy.resource_nano_cpus
            or host.get("Memory") != policy.resource_memory_bytes
            or host.get("Privileged") is not False or host.get("PublishAllPorts") is not False
            or host.get("PortBindings") not in ({}, None)
            or not isinstance(settings, dict) or bool(settings.get("Ports"))
            or not isinstance(networks, dict) or set(networks) != {NETWORK}
            or not isinstance(networks[NETWORK], dict)
            or networks[NETWORK].get("NetworkID") != policy.network_id
            or not isinstance(networks[NETWORK].get("Aliases"), list)
            or ALIAS not in networks[NETWORK]["Aliases"]
            or not isinstance(mounts, list) or len(mounts) != 1
            or not isinstance(mounts[0], dict)
            or mounts[0].get("Destination") != SECRET_TARGET
            or mounts[0].get("Type") != "bind" or mounts[0].get("RW") is not False):
        raise CollectionError("stopped owned container, image, network, or secret mount differs")
    return state["ExitCode"]


def _network_identity(value: dict[str, Any], policy: contracts.CollectionPolicy) -> None:
    labels = value.get("Labels")
    if (value.get("Id") != policy.network_id or value.get("Name") != NETWORK
            or value.get("Internal") is not True or not isinstance(labels, dict)
            or labels.get("factory.sandbox.owner") != "python-factory"
            or labels.get("factory.sandbox.peer_network_id") != NETWORK_ID
            or not isinstance(value.get("Containers"), dict)):
        raise CollectionError("internal managed network identity differs")


def _tar_tree(value: bytes, peer_ids: tuple[str, str]) -> dict[str, bytes]:
    root = Path(REMOTE_ROOT).name
    allowed = {"run-index.json", *(f"peer-queries/{peer_id}.json" for peer_id in peer_ids)}
    found: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(value), mode="r:") as archive:
            for member in archive:
                name = member.name.removeprefix("./").rstrip("/")
                if (member.name.startswith("/") or ".." in name.split("/")
                        or not (name == root or name.startswith(root + "/"))):
                    raise CollectionError("Docker evidence tree contains an unsafe path")
                relative = name.removeprefix(root + "/")
                if member.isdir():
                    if name not in (root, f"{root}/peer-queries"):
                        raise CollectionError("Docker evidence tree contains an unexpected directory")
                    continue
                if not member.isfile() or relative not in allowed or relative in found:
                    raise CollectionError("Docker evidence tree contains an unexpected file")
                if member.size > MAX_FILE_BYTES:
                    raise CollectionError("Docker evidence file is oversized")
                stream = archive.extractfile(member)
                if stream is None:
                    raise CollectionError("Docker evidence file has no content")
                data = stream.read(MAX_FILE_BYTES + 1)
                if len(data) != member.size:
                    raise CollectionError("Docker evidence file size differs")
                found[relative] = data
            if "run-index.json" not in found:
                raise CollectionError("Docker evidence tree lacks run index")
            return found
    except tarfile.TarError as error:
        raise CollectionError("Docker copy archive is invalid") from error


def _query_map(query: contracts.SDKQuery) -> dict[str, Any]:
    return {row.record_id: row for row in query.documents}


def _verify_local_inference(index: contracts.RunIndex,
                            peer_files: list[contracts.PeerSDKFile],
                            rows: dict[str, Any], policy: contracts.CollectionPolicy) -> None:
    assert index.selected is not None and index.decision is not None
    coordinator = next((peer for peer in peer_files if peer.peer_id == policy.coordinator_id), None)
    selected = next((peer for peer in peer_files if peer.peer_id == index.selected.peer_id), None)
    if (coordinator is None or coordinator.local_inference is None or selected is None
            or selected.local_inference is None or coordinator.peer_id == selected.peer_id
            or any(peer.local_inference is None for peer in peer_files)):
        raise CollectionError("coordinator and selected peer inference evidence are required")
    result = rows.get(index.selected.result_record_id)
    observation = rows.get(index.decision.observation_record_id)
    if result is None or result.record_type != "result" or observation is None or observation.record_type != "observation":
        raise CollectionError("selected Result or source Observation is absent")
    signals = tuple(item.value for item in observation.bounded_output if item.name == "signal")
    for peer in (coordinator, selected):
        inferred = peer.local_inference
        assert inferred is not None
        if (inferred.source_event_sha256 != policy.pins.source_event_sha256
                or inferred.model_sha256 != policy.pins.model_sha256
                or inferred.decision != policy.expected_decision
                or abs(inferred.probability - policy.expected_probability) > policy.score_tolerance):
            raise CollectionError("peer local inference differs from reviewed cohort")
    coordinator_inference = coordinator.local_inference
    selected_inference = selected.local_inference
    assert coordinator_inference is not None and selected_inference is not None
    if (abs(coordinator_inference.probability - observation.confidence_or_score) > policy.score_tolerance
            or signals != (bool(coordinator_inference.decision),)
            or signals != (bool(policy.expected_decision),)
            or result.input_ref != f"sha256:{policy.pins.source_event_sha256}"
            or result.result_ref != f"sha256:{sha256(schema.canonical_bytes(selected_inference))}"):
        raise CollectionError("peer inference, reviewed cohort, and synced records disagree")


def _construct(files: dict[str, bytes], policy: contracts.CollectionPolicy,
               exit_code: int) -> schema.RoutingAttestation:
    index = contracts.RunIndex.model_validate(_json(files["run-index.json"]))
    if index.run_status == "succeeded":
        assert index.measurements is not None
        measurements = index.measurements
        if (measurements.cgroup_memory_peak.value is not None
                and measurements.cgroup_memory_peak.value > policy.resource_memory_bytes):
            raise CollectionError("observed cgroup memory peak exceeds reviewed container limit")
        if any(item.value is None for item in (
            measurements.task_delivery, measurements.rejoin_delivery, measurements.end_to_end,
        )):
            raise CollectionError("successful run lacks measured delivery or end-to-end durations")
    peer_names = {f"peer-queries/{peer_id}.json" for peer_id in policy.peer_ids}
    declared = set(index.files_sha256)
    if (index.pins != policy.pins or index.group_id != policy.group_id
            or index.session_id != policy.session_id or index.coordinator_id != policy.coordinator_id
            or index.policy_version != policy.policy_version
            or declared not in (set(), peer_names)
            or (index.run_status == "succeeded" and declared != peer_names)
            or set(files) != {"run-index.json"} | declared
            or any(index.files_sha256[name] != sha256(files[name]) for name in declared)
            or (exit_code == 0) != (index.run_status == "succeeded")
            or exit_code not in (0, 1)):
        raise CollectionError("external pins, peer files, or run exit disagree")
    peer_files = [contracts.PeerSDKFile.model_validate(_json(files[f"peer-queries/{peer_id}.json"]))
                  for peer_id in policy.peer_ids] if declared else []
    if declared and any(
        peer.peer_id != peer_id or peer.sdk_distribution_sha256 != policy.pins.sdk_distribution_sha256
        for peer, peer_id in zip(peer_files, policy.peer_ids, strict=True)
    ):
        raise CollectionError("peer identity or SDK distribution differs from host policy")
    if index.run_status == "succeeded" and any(
        peer.measurements.write_total.value is None
        or peer.measurements.query_total.value is None
        for peer in peer_files
    ):
        raise CollectionError("successful run lacks measured SDK write or query durations")
    if index.run_status == "failed":
        return schema.RoutingAttestation(schema_version=2, run_status="failed",
            failure_reason=index.failure_reason, pins=policy.pins.model_dump(mode="json"), group_id=policy.group_id,
            session_id=policy.session_id, trusted_coordinator_device_id=policy.coordinator_id,
            policy_version=policy.policy_version, decision=None, selected=None, records=(),
            peer_readbacks=(), reducer_as_of=None, reducer_state_sha256=None,
            accepted_record_set_sha256=None)
    if not all(peer.disconnect_observed and peer.rejoin_observed for peer in peer_files):
        raise CollectionError("declared disconnection/rejoin is absent")
    rows = _query_map(peer_files[0].after_rejoin)
    if not rows or len(rows) > 64:
        raise CollectionError("converged SDK query is empty or oversized")
    _verify_local_inference(index, peer_files, rows, policy)
    hashes = {record_id: sha256(schema.canonical_bytes(row)) for record_id, row in rows.items()}
    readbacks = []
    for peer in peer_files:
        if (peer.peer_id == policy.coordinator_id) != (peer.decision_query is not None):
            raise CollectionError("only coordinator must supply a predecision SDK query")
        local = {row.record_id: row for row in peer.local_write_documents}
        if any(row.producer_device_id != peer.peer_id or rows.get(record_id) != row
               for record_id, row in local.items()):
            raise CollectionError("local SDK write differs from converged query")
        reopen = _query_map(peer.reopen)
        if any(rows.get(record_id) != row for record_id, row in reopen.items()):
            raise CollectionError("reopen SDK query differs from converged documents")
        if _query_map(peer.after_rejoin) != rows:
            raise CollectionError("peer SDK rejoin queries have different record sets")
        decision_query = None
        if peer.decision_query is not None:
            decision_query = {"queried_at": peer.decision_query.queried_at,
                "record_sha256_by_id": {
                    record_id: sha256(schema.canonical_bytes(row))
                    for record_id, row in _query_map(peer.decision_query).items()
                }}
        readbacks.append({
            "peer_id": peer.peer_id, "sdk_distribution_sha256": peer.sdk_distribution_sha256,
            "local_write_record_ids": tuple(local),
            "decision_query": decision_query,
            "reopen": {"queried_at": peer.reopen.queried_at,
                "record_sha256_by_id": {record_id: hashes[record_id] for record_id in reopen}},
            "after_rejoin": {"queried_at": peer.after_rejoin.queried_at,
                "record_sha256_by_id": hashes},
            "disconnect_observed": True, "rejoin_observed": True})
    assert index.reducer_as_of is not None
    state = attestation._reducer.reduce_records(tuple(rows.values()), group_id=policy.group_id,
        session_id=policy.session_id, as_of=index.reducer_as_of,
        trusted_coordinator_device_id=policy.coordinator_id,
        expected_policy_version=policy.policy_version,
        expected_policy_sha256=policy.pins.policy_sha256)
    result = schema.RoutingAttestation(schema_version=2, run_status="succeeded", failure_reason=None,
        pins=policy.pins.model_dump(mode="json"), group_id=policy.group_id, session_id=policy.session_id,
        trusted_coordinator_device_id=policy.coordinator_id, policy_version=policy.policy_version,
        decision=index.decision.model_dump(mode="json") if index.decision else None,
        selected=index.selected.model_dump(mode="json") if index.selected else None,
        records=tuple(row.model_dump(mode="json") for row in rows.values()),
        peer_readbacks=tuple(readbacks), reducer_as_of=index.reducer_as_of,
        reducer_state_sha256=state.state_digest,
        accepted_record_set_sha256=state.accepted_record_set_digest)
    if (sha256((schema.MESH / "records.py").read_bytes()) != policy.pins.records_module_sha256
            or sha256((schema.MESH / "reducer.py").read_bytes()) != policy.pins.reducer_module_sha256):
        raise CollectionError("host replay modules differ from external pins")
    row_map, row_hashes = attestation._record_map(result)
    claim, selected_result = attestation._verify_route(result, row_map, row_hashes, policy.capability_tags)
    attestation._verify_readbacks(result, row_map, row_hashes)
    task_state = next((task for task in state.tasks if task.task_id == claim.task_id), None)
    if (task_state is None or task_state.winner_claim_id != claim.claim_id
            or task_state.accepted_result_id != selected_result.result_id
            or task_state.state != "completed"):
        raise CollectionError("pinned reducer did not accept selected route")
    return result


def _same_stopped_snapshot(docker: DockerBoundary, container_id: str,
                           policy: contracts.CollectionPolicy, initial: dict[str, Any],
                           exit_code: int) -> None:
    observed = docker.inspect(container_id)
    if _container_identity(observed, container_id, policy) != exit_code or observed != initial:
        raise CollectionError("stopped Docker process identity changed during evidence collection")


def _cleanup_owned(docker: DockerBoundary, container_id: str,
                   policy: contracts.CollectionPolicy) -> None:
    docker.remove(container_id)
    network = docker.network(policy.network_id)
    _network_identity(network, policy)
    if not network["Containers"]:
        docker.remove_network(policy.network_id)


def _collect_locked(container_id: str, policy: contracts.CollectionPolicy,
                    output: Path, docker: DockerBoundary) -> dict[str, Any]:
    if output.exists() or output.is_symlink():
        raise CollectionError("collector output must be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.parent.is_symlink() or not output.parent.is_dir():
        raise CollectionError("collector output parent is invalid")
    owned = False
    files: dict[str, bytes] = {}
    try:
        first = docker.inspect(container_id)
        exit_code = _container_identity(first, container_id, policy)
        _network_identity(docker.network(policy.network_id), policy)
        owned = True
        if docker.wait(container_id) != exit_code:
            raise CollectionError("container exit status changed")
        _same_stopped_snapshot(docker, container_id, policy, first, exit_code)
        copied = docker.copy_tree(container_id)
        _same_stopped_snapshot(docker, container_id, policy, first, exit_code)
        files = _tar_tree(copied, policy.peer_ids)
        result = _construct(files, policy, exit_code)
        _same_stopped_snapshot(docker, container_id, policy, first, exit_code)
    except Exception:
        if owned:
            try:
                _same_stopped_snapshot(docker, container_id, policy, first, exit_code)
                _cleanup_owned(docker, container_id, policy)
            except (CollectionError, OSError, TypeError, KeyError):
                pass
        raise
    # Stage validated bytes before removing their only recoverable source. The
    # destination is reserved exclusively, and attestation.json is published
    # last, only after stopped-state and cleanup checks have succeeded.
    temporary = Path(tempfile.mkdtemp(prefix=".edge-routing-collect-", dir=output.parent))
    reserved = False
    cleanup_started = False
    retain_stage = False
    try:
        for name, content in files.items():
            path = temporary / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        encoded = schema.canonical_bytes(result)
        (temporary / "attestation.json").write_bytes(encoded)
        details = {"schema_version": 1, "run_status": result.run_status,
                   "attestation_sha256": sha256(encoded), "container_id": container_id,
                   "image_sha256": policy.pins.image_sha256, "network_id": policy.network_id,
                   "files_sha256": {name: sha256(content) for name, content in files.items()},
                   "review_status": "unreviewed"}
        (temporary / "collection.json").write_bytes(schema.canonical_bytes(details))
        _sync_tree(temporary)
        try:
            output.mkdir(mode=0o700)
        except FileExistsError:
            raise CollectionError("collector output must be new") from None
        reserved = True
        _same_stopped_snapshot(docker, container_id, policy, first, exit_code)
        cleanup_started = True
        _cleanup_owned(docker, container_id, policy)
        for name in files:
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(temporary / name, destination)
        shutil.copyfile(temporary / "collection.json", output / "collection.json")
        shutil.copyfile(temporary / "attestation.json", output / ".attestation.pending")
        _sync_tree(output)
        os.replace(output / ".attestation.pending", output / "attestation.json")
        _sync_path(output)
        _sync_path(output.parent)
        reserved = False
        return details
    except BaseException as error:
        # An interrupt after Docker cleanup may leave this stage as the only
        # recoverable copy. Set retention before attempting output cleanup.
        retain_stage = cleanup_started
        if reserved:
            shutil.rmtree(output)
        if cleanup_started and isinstance(error, Exception):
            raise CollectionError(f"collection failed after cleanup began; staged evidence retained at {temporary}") from None
        raise
    finally:
        if not retain_stage and temporary.exists():
            shutil.rmtree(temporary)


def collect(container_id: str, policy: contracts.CollectionPolicy | dict[str, Any],
            output: Path, docker: DockerBoundary | None = None) -> dict[str, Any]:
    try:
        if CONTAINER_ID.fullmatch(container_id) is None:
            raise CollectionError("container ID must be a full Docker hex ID")
        expected = contracts.CollectionPolicy.model_validate(policy)
        with _container_lock(container_id):
            return _collect_locked(container_id, expected, output, docker or DockerBoundary())
    except (ValueError, TypeError) as error:
        if isinstance(error, CollectionError):
            raise
        raise CollectionError("routing evidence failed host validation") from None
