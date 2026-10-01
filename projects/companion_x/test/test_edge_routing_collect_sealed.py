"""License-free host collector checks; fake Docker is not SDK provenance."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import stat
import sys
import tarfile
import traceback
from pathlib import Path

import pytest

from projects.companion_x.test import test_edge_routing_attestation as fixtures

ROOT = Path(__file__).parents[1] / "experiments/edge_models/edge-routing-sdk-001"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


collector = load(ROOT / "collect_sealed.py", "edge_routing_collect_sealed")


def encode(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


class FakeDocker:
    def __init__(self, files: dict[str, bytes], image_id: str):
        self.files = files
        self.image_id = image_id
        self.container_id = "d" * 64
        self.network_id = "c" * 64
        self.exit_code = 0
        self.wait_code = 0
        self.running = False
        self.secret_rw = False
        self.symlink_name: str | None = None
        self.copies: list[str] = []
        self.removals: list[str] = []
        self.network_removals: list[str] = []
        self.extra_network = False
        self.network_attached = False
        self.network_internal = True
        self.nano_cpus = 500_000_000
        self.memory_bytes = 536_870_912
        self.flip_running_on_first_copy = False
        self.flip_restart_on_first_copy = False
        self.restart_count = 0

    def inspect(self, container_id: str) -> dict:
        assert container_id == self.container_id
        networks = {collector.NETWORK: {"NetworkID": self.network_id, "Aliases": [collector.ALIAS]}}
        if self.extra_network:
            networks["bridge"] = {"NetworkID": "b" * 64, "Aliases": []}
        return {"Id": container_id, "Image": self.image_id, "Name": "/edge-routing-sdk",
                "State": {"Running": self.running, "Status": "running" if self.running else "exited",
                          "ExitCode": self.exit_code}, "RestartCount": self.restart_count,
                "Mounts": [{"Destination": collector.SECRET_TARGET, "Type": "bind", "RW": self.secret_rw}],
                "Config": {"Entrypoint": ["/usr/local/bin/python", "/sealed/entrypoint.py"],
                           "Cmd": ["run"], "Labels": collector.expected_labels()},
                "HostConfig": {"NetworkMode": collector.NETWORK, "Privileged": False,
                               "PublishAllPorts": False, "PortBindings": {},
                               "NanoCpus": self.nano_cpus, "Memory": self.memory_bytes},
                "NetworkSettings": {"Ports": {}, "Networks": networks}}

    def network(self, network_id: str) -> dict:
        assert network_id == self.network_id
        return {"Id": network_id, "Name": collector.NETWORK, "Internal": self.network_internal,
                "Labels": {"factory.sandbox.owner": "python-factory",
                           "factory.sandbox.peer_network_id": collector.NETWORK_ID},
                "Containers": {"other": {}} if self.network_attached else {}}

    def wait(self, container_id: str) -> int:
        assert container_id == self.container_id
        return self.wait_code

    def copy_tree(self, container_id: str) -> bytes:
        assert container_id == self.container_id
        self.copies.extend(self.files)
        if self.flip_running_on_first_copy:
            self.running = True
        if self.flip_restart_on_first_copy:
            self.restart_count += 1
        buffer = io.BytesIO()
        root = Path(collector.REMOTE_ROOT).name
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            directory = tarfile.TarInfo(root + "/")
            directory.type = tarfile.DIRTYPE
            archive.addfile(directory)
            if any(name.startswith("peer-queries/") for name in self.files):
                directory = tarfile.TarInfo(root + "/peer-queries/")
                directory.type = tarfile.DIRTYPE
                archive.addfile(directory)
            for name, content in self.files.items():
                member = tarfile.TarInfo(root + "/" + name)
                member.type = tarfile.SYMTYPE if self.symlink_name == name else tarfile.REGTYPE
                member.linkname = "secret" if self.symlink_name == name else ""
                member.size = 0 if self.symlink_name == name else len(content)
                archive.addfile(member, None if self.symlink_name == name else io.BytesIO(content))
        return buffer.getvalue()

    def remove(self, container_id: str) -> None:
        self.removals.append(container_id)

    def remove_network(self, network_id: str) -> None:
        self.network_removals.append(network_id)


def setup() -> tuple[dict, FakeDocker, dict]:
    target = fixtures.valid_attestation()
    pins = target["pins"]
    peer_ids = [peer["peer_id"] for peer in target["peer_readbacks"]]
    policy = {"pins": pins, "peer_ids": peer_ids, "network_id": "c" * 64,
              "group_id": target["group_id"], "session_id": target["session_id"],
              "coordinator_id": target["trusted_coordinator_device_id"],
              "policy_version": target["policy_version"],
              "capability_tags": fixtures.EXPECTED_CAPABILITY_TAGS,
              "expected_probability": fixtures.LOCAL_INFERENCE["probability"],
              "expected_decision": fixtures.LOCAL_INFERENCE["decision"],
              "score_tolerance": 1e-6, "resource_nano_cpus": 500_000_000,
              "resource_memory_bytes": 536_870_912}
    files = {}
    rows = {row["record_id"]: row for row in target["records"]}
    for peer in target["peer_readbacks"]:
        decision_query = peer["decision_query"]
        files[f'peer-queries/{peer["peer_id"]}.json'] = encode({
            "schema_version": 2, "peer_id": peer["peer_id"],
            "sdk_distribution_sha256": peer["sdk_distribution_sha256"],
            "local_write_documents": [rows[item] for item in peer["local_write_record_ids"]],
            "decision_query": ({"queried_at": decision_query["queried_at"],
                                "documents": [rows[item] for item in decision_query["record_sha256_by_id"]]}
                               if decision_query is not None else None),
            "reopen": {"queried_at": peer["reopen"]["queried_at"], "documents": list(rows.values())},
            "after_rejoin": {"queried_at": peer["after_rejoin"]["queried_at"], "documents": list(rows.values())},
            "local_inference": fixtures.LOCAL_INFERENCE,
            "measurements": {
                "disk_usage_before": {"value": 100, "unit": "bytes", "unavailable_reason": None},
                "disk_usage_after": {"value": 180, "unit": "bytes", "unavailable_reason": None},
                "disk_usage_growth": {"value": 80, "unit": "bytes", "unavailable_reason": None},
                "write_total": {"value": 250, "unit": "microseconds", "unavailable_reason": None},
                "query_total": {"value": 500, "unit": "microseconds", "unavailable_reason": None},
            },
            "disconnect_observed": True, "rejoin_observed": True})
    files["run-index.json"] = encode({
        "schema_version": 2, "run_status": "succeeded", "failure_reason": None,
        "pins": pins, "group_id": target["group_id"], "session_id": target["session_id"],
        "coordinator_id": target["trusted_coordinator_device_id"], "policy_version": target["policy_version"],
        "decision": target["decision"], "selected": target["selected"],
        "reducer_as_of": target["reducer_as_of"],
        "measurements": {
            "cgroup_cpu_usage": {"value": 1000, "unit": "microseconds", "unavailable_reason": None},
            "cgroup_memory_peak": {"value": 12000000, "unit": "bytes", "unavailable_reason": None},
            "task_delivery": {"value": 5.0, "unit": "milliseconds", "unavailable_reason": None},
            "rejoin_delivery": {"value": 7.0, "unit": "milliseconds", "unavailable_reason": None},
            "end_to_end": {"value": 25.0, "unit": "milliseconds", "unavailable_reason": None},
            "raw_mesh_bytes": {"value": None, "unit": "bytes",
                                "unavailable_reason": "not_exposed_by_public_sdk"},
        },
        "files_sha256": {name: collector.sha256(content) for name, content in files.items()}})
    return policy, FakeDocker(files, "sha256:" + pins["image_sha256"]), target


def test_host_collects_raw_queries_and_constructs_attestation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy, docker, target = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    output = tmp_path / "collected"
    result = collector.collect(docker.container_id, policy, output, docker)
    names = set(docker.files)
    assert set(docker.copies) == names
    assert docker.removals == [docker.container_id]
    assert docker.network_removals == [docker.network_id]
    assert result["run_status"] == "succeeded"
    attestation = json.loads((output / "attestation.json").read_bytes())
    assert attestation == fixtures.contract.RoutingAttestation.model_validate(target).model_dump(mode="json")
    assert "signature_base64" not in (output / "attestation.json").read_text()


@pytest.mark.parametrize("fault", ["wrong_image", "running", "secret_rw", "extra_network",
                                     "hash", "symlink", "changed_query", "wrong_pins",
                                     "wait_code", "self_key", "wrong_network", "exit_route_mismatch",
                                     "duplicate_json", "wrong_nano_cpus", "wrong_memory"])
def test_fail_closed_and_cleanup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    if fault == "wrong_image":
        docker.image_id = "sha256:" + "0" * 64
    elif fault == "running":
        docker.running = True
    elif fault == "secret_rw":
        docker.secret_rw = True
    elif fault == "extra_network":
        docker.extra_network = True
    elif fault == "hash":
        docker.files["peer-queries/peer-1.json"] += b" "
    elif fault == "symlink":
        docker.symlink_name = "run-index.json"
    elif fault == "changed_query":
        name = "peer-queries/peer-2.json"
        item = json.loads(docker.files[name])
        item["after_rejoin"]["documents"][1]["model_version"] = "2"
        docker.files[name] = encode(item)
        index = json.loads(docker.files["run-index.json"])
        index["files_sha256"][name] = collector.sha256(docker.files[name])
        docker.files["run-index.json"] = encode(index)
    elif fault == "wrong_pins":
        index = json.loads(docker.files["run-index.json"])
        index["pins"]["model_sha256"] = "0" * 64
        docker.files["run-index.json"] = encode(index)
    elif fault == "wait_code":
        docker.wait_code = 1
    elif fault == "self_key":
        index = json.loads(docker.files["run-index.json"])
        index["trusted_reviewer_keys"] = {"self": "ignored"}
        docker.files["run-index.json"] = encode(index)
    elif fault == "wrong_network":
        docker.network_internal = False
    elif fault == "exit_route_mismatch":
        docker.exit_code = docker.wait_code = 1
    elif fault == "duplicate_json":
        docker.files["run-index.json"] = docker.files["run-index.json"].replace(
            b'"schema_version":2,', b'"schema_version":2,"schema_version":2,', 1)
    elif fault == "wrong_nano_cpus":
        docker.nano_cpus += 1
    elif fault == "wrong_memory":
        docker.memory_bytes += 1
    output = tmp_path / "rejected"
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, output, docker)
    assert not output.exists()
    assert docker.removals == ([] if fault in {"wrong_image", "running", "secret_rw", "extra_network", "wrong_network",
                                               "wrong_nano_cpus", "wrong_memory"}
                               else [docker.container_id])


def test_failed_run_cannot_emit_success_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    docker.exit_code = docker.wait_code = 1
    index = json.loads(docker.files["run-index.json"])
    index.update(run_status="failed", failure_reason="sdk_query_failed", decision=None, selected=None,
                 reducer_as_of=None, measurements=None)
    docker.files["run-index.json"] = encode(index)
    result = collector.collect(docker.container_id, policy, tmp_path / "failed", docker)
    assert result["run_status"] == "failed"
    failed = json.loads((tmp_path / "failed" / "attestation.json").read_bytes())
    assert failed["selected"] is None
    assert failed["run_status"] == "failed"


def test_early_failure_needs_only_index_and_no_peer_fabrication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    docker.exit_code = docker.wait_code = 1
    index = json.loads(docker.files["run-index.json"])
    index.update(run_status="failed", failure_reason="sdk_start_failed", decision=None,
                 selected=None, reducer_as_of=None, files_sha256={}, measurements=None)
    docker.files = {"run-index.json": encode(index)}
    output = tmp_path / "early-failure"
    result = collector.collect(docker.container_id, policy, output, docker)
    assert result["run_status"] == "failed"
    assert result["files_sha256"] == {"run-index.json": collector.sha256(docker.files["run-index.json"])}
    assert set(docker.copies) == {"run-index.json"}
    assert json.loads((output / "attestation.json").read_bytes())["peer_readbacks"] == []
    assert json.loads((output / "collection.json").read_bytes())["review_status"] == "unreviewed"


@pytest.mark.parametrize("fault", ["unexpected_file", "unknown_file", "traversal",
                                     "partial_peer", "success_shape", "success_exit"])
def test_early_failure_rejects_unexpected_or_success_shaped_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    docker.exit_code = docker.wait_code = 1
    index = json.loads(docker.files["run-index.json"])
    index.update(run_status="failed", failure_reason="sdk_start_failed", decision=None,
                 selected=None, reducer_as_of=None, files_sha256={}, measurements=None)
    docker.files = {"run-index.json": encode(index)}
    if fault == "unexpected_file":
        docker.files["peer-queries/peer-1.json"] = b"{}"
    elif fault == "unknown_file":
        docker.files["debug.log"] = b"secret-like debug output"
    elif fault == "traversal":
        docker.files["../outside"] = b"secret-like debug output"
    elif fault == "partial_peer":
        index["files_sha256"] = {"peer-queries/peer-1.json": "a" * 64}
        docker.files["run-index.json"] = encode(index)
        docker.files["peer-queries/peer-1.json"] = b"{}"
    elif fault == "success_shape":
        index["selected"] = setup()[2]["selected"]
        docker.files["run-index.json"] = encode(index)
    elif fault == "success_exit":
        docker.exit_code = docker.wait_code = 0
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, tmp_path / "rejected", docker)
    assert not (tmp_path / "rejected").exists()


def test_other_container_keeps_owned_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy, docker, _ = setup()
    docker.network_attached = True
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    collector.collect(docker.container_id, policy, tmp_path / "collected", docker)
    assert docker.removals == [docker.container_id]
    assert docker.network_removals == []


@pytest.mark.parametrize("fault", ["missing", "stale", "wrong_hash", "future", "wrong_peer"])
def test_collector_requires_actual_coordinator_predecision_sdk_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    name = "peer-queries/peer-1.json"
    peer = json.loads(docker.files[name])
    if fault == "missing":
        peer.pop("decision_query")
    elif fault == "stale":
        peer["decision_query"]["queried_at"] = "2026-09-30T12:00:00Z"
    elif fault == "wrong_hash":
        peer["decision_query"]["documents"][1]["model_version"] = "2"
    elif fault == "future":
        peer["decision_query"]["documents"].append(peer["reopen"]["documents"][5])
    elif fault == "wrong_peer":
        other_name = "peer-queries/peer-2.json"
        other = json.loads(docker.files[other_name])
        other["decision_query"] = peer["decision_query"]
        docker.files[other_name] = encode(other)
    docker.files[name] = encode(peer)
    index = json.loads(docker.files["run-index.json"])
    for filename in (name, "peer-queries/peer-2.json"):
        index["files_sha256"][filename] = collector.sha256(docker.files[filename])
    docker.files["run-index.json"] = encode(index)
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, tmp_path / "rejected", docker)
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("fault", ["missing", "wrong_score", "wrong_decision",
                                     "wrong_model", "wrong_source", "wrong_timing",
                                     "coordinator", "wrong_reviewed_cohort", "missing_measurement"])
def test_collector_binds_selected_local_inference_to_reviewed_cohort_and_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    name = "peer-queries/peer-2.json"
    peer = json.loads(docker.files[name])
    if fault == "missing":
        peer.pop("local_inference")
    elif fault == "wrong_score":
        peer["local_inference"]["probability"] = 0.7
    elif fault == "wrong_decision":
        peer["local_inference"]["decision"] = 0
    elif fault == "wrong_model":
        peer["local_inference"]["model_sha256"] = "0" * 64
    elif fault == "wrong_source":
        peer["local_inference"]["source_event_sha256"] = "0" * 64
    elif fault == "wrong_timing":
        peer["local_inference"]["inference_ms"] = 2.0
    elif fault == "wrong_reviewed_cohort":
        policy["expected_probability"] = 0.7
    elif fault == "missing_measurement":
        peer.pop("measurements")
    else:
        coordinator_name = "peer-queries/peer-1.json"
        coordinator = json.loads(docker.files[coordinator_name])
        coordinator["local_inference"]["probability"] = 0.7
        docker.files[coordinator_name] = encode(coordinator)
    docker.files[name] = encode(peer)
    index = json.loads(docker.files["run-index.json"])
    for filename in (name, "peer-queries/peer-1.json"):
        index["files_sha256"][filename] = collector.sha256(docker.files[filename])
    docker.files["run-index.json"] = encode(index)
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, tmp_path / "rejected", docker)
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("fault", ["fabricated_mesh_bytes", "memory_over_limit", "missing_reason"])
def test_collector_requires_truthful_resource_and_network_measurements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    index = json.loads(docker.files["run-index.json"])
    if fault == "fabricated_mesh_bytes":
        index["measurements"]["raw_mesh_bytes"] = {
            "value": 900, "unit": "bytes", "unavailable_reason": None}
    elif fault == "memory_over_limit":
        index["measurements"]["cgroup_memory_peak"]["value"] = policy["resource_memory_bytes"] + 1
    else:
        index["measurements"]["cgroup_cpu_usage"] = {
            "value": None, "unit": "microseconds", "unavailable_reason": None}
    docker.files["run-index.json"] = encode(index)
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, tmp_path / "rejected", docker)
    assert not (tmp_path / "rejected").exists()


def test_zero_monotonic_durations_are_preserved_as_measured_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    index = json.loads(docker.files["run-index.json"])
    for name in ("task_delivery", "rejoin_delivery", "end_to_end"):
        index["measurements"][name]["value"] = 0.0
    for peer_id in policy["peer_ids"]:
        name = f"peer-queries/{peer_id}.json"
        peer = json.loads(docker.files[name])
        peer["measurements"]["write_total"]["value"] = 0
        peer["measurements"]["query_total"]["value"] = 0
        docker.files[name] = encode(peer)
        index["files_sha256"][name] = collector.sha256(docker.files[name])
    docker.files["run-index.json"] = encode(index)
    result = collector.collect(docker.container_id, policy, tmp_path / "zero-timings", docker)
    assert result["run_status"] == "succeeded"


@pytest.mark.parametrize("file_name", ["run-index.json", "peer-queries/peer-1.json"])
def test_v1_collection_input_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, file_name: str,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    item = json.loads(docker.files[file_name])
    item["schema_version"] = 1
    docker.files[file_name] = encode(item)
    if file_name != "run-index.json":
        index = json.loads(docker.files["run-index.json"])
        index["files_sha256"][file_name] = collector.sha256(docker.files[file_name])
        docker.files["run-index.json"] = encode(index)
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, tmp_path / "rejected", docker)


@pytest.mark.parametrize("secret", [
    "DITTO_OFFLINE_LICENSE=employee-private-token",
    "sdk_query_failed: employee-private-token",
])
def test_arbitrary_failure_text_is_rejected_without_persisting_or_leaking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, secret: str,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    docker.exit_code = docker.wait_code = 1
    index = json.loads(docker.files["run-index.json"])
    index.update(run_status="failed", failure_reason=secret, decision=None,
                 selected=None, reducer_as_of=None, measurements=None)
    docker.files["run-index.json"] = encode(index)
    output = tmp_path / "rejected"
    with pytest.raises(collector.CollectionError) as caught:
        collector.collect(docker.container_id, policy, output, docker)
    assert secret not in str(caught.value)
    assert secret not in "".join(traceback.format_exception(caught.value))
    assert not output.exists()


def test_secret_in_unknown_index_field_is_absent_from_exception_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    index = json.loads(docker.files["run-index.json"])
    index["unexpected_secret"] = "SECRET_SENTINEL_employee_private"
    docker.files["run-index.json"] = encode(index)
    with pytest.raises(collector.CollectionError) as caught:
        collector.collect(docker.container_id, policy, tmp_path / "rejected", docker)
    assert "SECRET_SENTINEL" not in "".join(traceback.format_exception(caught.value))


def test_invalid_utf8_evidence_does_not_leak_bytes_in_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    docker.files["run-index.json"] = b'{"secret":"SECRET_SENTINEL_employee_private\xff"}'
    with pytest.raises(collector.CollectionError) as caught:
        collector.collect(docker.container_id, policy, tmp_path / "rejected", docker)
    assert "SECRET_SENTINEL" not in "".join(traceback.format_exception(caught.value))


@pytest.mark.parametrize("change", ["running", "restart"])
def test_state_change_during_copy_cannot_yield_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    if change == "running":
        docker.flip_running_on_first_copy = True
    else:
        docker.flip_restart_on_first_copy = True
    output = tmp_path / "rejected"
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, output, docker)
    assert not output.exists()
    assert set(docker.copies) == set(docker.files)
    assert docker.removals == []


def test_output_failure_retains_stopped_owned_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    docker.exit_code = docker.wait_code = 1
    index = json.loads(docker.files["run-index.json"])
    index.update(run_status="failed", failure_reason="sdk_start_failed", decision=None,
                 selected=None, reducer_as_of=None, files_sha256={}, measurements=None)
    docker.files = {"run-index.json": encode(index)}

    def denied(*_args, **_kwargs):
        raise OSError("cannot create output")

    monkeypatch.setattr(collector.tempfile, "mkdtemp", denied)
    output = tmp_path / "unwritten"
    with pytest.raises(OSError, match="cannot create output"):
        collector.collect(docker.container_id, policy, output, docker)
    assert not output.exists()
    assert docker.removals == []
    assert docker.network_removals == []


def test_cleanup_failure_never_publishes_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    output = tmp_path / "unpublished"

    def fail_remove(_container_id: str) -> None:
        raise OSError("Docker removal failed")

    docker.remove = fail_remove
    with pytest.raises(collector.CollectionError, match="staged evidence retained"):
        collector.collect(docker.container_id, policy, output, docker)
    assert not output.exists()
    assert len(list(tmp_path.glob(".edge-routing-collect-*"))) == 1


def test_new_output_created_during_copy_is_not_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    output = tmp_path / "competing-output"
    original_copy = docker.copy_tree

    def create_competing_output(container_id: str) -> bytes:
        output.write_bytes(b"existing evidence")
        return original_copy(container_id)

    docker.copy_tree = create_competing_output
    with pytest.raises(collector.CollectionError):
        collector.collect(docker.container_id, policy, output, docker)
    assert output.read_bytes() == b"existing evidence"


def test_publish_failure_after_cleanup_retains_private_staged_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    output = tmp_path / "unpublished"
    original_replace = collector.os.replace

    def fail_publish(source: str | Path, destination: str | Path) -> None:
        target = Path(destination)
        if target == output or output in target.parents:
            raise OSError("publication failed")
        original_replace(source, destination)

    monkeypatch.setattr(collector.os, "replace", fail_publish)
    with pytest.raises(collector.CollectionError, match="staged evidence retained"):
        collector.collect(docker.container_id, policy, output, docker)
    assert not output.exists()
    assert docker.removals == [docker.container_id]
    staged = list(tmp_path.glob(".edge-routing-collect-*"))
    assert len(staged) == 1
    assert stat.S_IMODE(staged[0].stat().st_mode) == 0o700
    assert (staged[0] / "attestation.json").is_file()
    assert (staged[0] / "collection.json").is_file()


def test_published_evidence_directory_is_private_under_common_umask(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    previous_umask = os.umask(0o022)
    try:
        output = tmp_path / "private"
        collector.collect(docker.container_id, policy, output, docker)
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    assert not list(tmp_path.glob(".edge-routing-collect-*"))


def test_interrupt_during_publication_retains_stage_without_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))
    output = tmp_path / "interrupted"
    original_replace = collector.os.replace

    def interrupt_publish(source: str | Path, destination: str | Path) -> None:
        if Path(destination) == output / "attestation.json":
            raise KeyboardInterrupt()
        original_replace(source, destination)

    monkeypatch.setattr(collector.os, "replace", interrupt_publish)
    with pytest.raises(KeyboardInterrupt):
        collector.collect(docker.container_id, policy, output, docker)
    assert not output.exists()
    staged = list(tmp_path.glob(".edge-routing-collect-*"))
    assert len(staged) == 1
    assert stat.S_IMODE(staged[0].stat().st_mode) == 0o700
    assert (staged[0] / "attestation.json").is_file()


def test_stage_sync_failure_keeps_docker_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy, docker, _ = setup()
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "locks"))

    def fail_sync(_fd: int) -> None:
        raise OSError("sync failed")

    monkeypatch.setattr(collector.os, "fsync", fail_sync)
    output = tmp_path / "unwritten"
    with pytest.raises(OSError, match="sync failed"):
        collector.collect(docker.container_id, policy, output, docker)
    assert not output.exists()
    assert docker.removals == []
