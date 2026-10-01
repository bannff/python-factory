"""Host collector checks use a fake Docker boundary; no SDK or secret is opened."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import fcntl
import os
import sys
import tarfile
import uuid
from pathlib import Path

import pytest

EXPERIMENT = Path(__file__).parents[1] / "experiments/edge_models/edge-ditto-device-flow-001"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_old_contracts, _old_run = sys.modules.get("contracts"), sys.modules.get("run")
contracts = _load(EXPERIMENT / "contracts.py", "collect_test_contracts")
sys.modules["contracts"] = contracts
runner = _load(EXPERIMENT / "run.py", "collect_test_run")
sys.modules["run"] = runner
try:
    collector = _load(EXPERIMENT / "collect_sealed.py", "collect_sealed_test")
finally:
    if _old_contracts is None:
        sys.modules.pop("contracts", None)
    else:
        sys.modules["contracts"] = _old_contracts
    if _old_run is None:
        sys.modules.pop("run", None)
    else:
        sys.modules["run"] = _old_run


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, allow_nan=False) + "\n").encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _tar(name: str, data: bytes, *, symlink: bool = False) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.type = tarfile.SYMTYPE if symlink else tarfile.REGTYPE
        info.linkname = "secret" if symlink else ""
        info.size = 0 if symlink else len(data)
        archive.addfile(info, None if symlink else io.BytesIO(data))
    return buffer.getvalue()


class FakeDocker:
    def __init__(self, files: dict[str, bytes], container_id: str, image_id: str):
        self.files = files
        self.container_id = container_id
        self.image_id = image_id
        self.network_id = "c" * 64
        self.wait_code = 0
        self.exit_code = 0
        self.symlink_name = None
        self.removals: list[str] = []
        self.network_removals: list[str] = []
        self.copies: list[str] = []
        self.remove_fails = False
        self.network_cleanup_fails = False
        self.network_attached = False

    def inspect(self, container_id: str) -> dict:
        assert container_id == self.container_id
        return {
            "Id": container_id, "Image": self.image_id, "Name": "/edge-n2-sdk",
            "State": {"Running": False, "Status": "exited", "ExitCode": self.exit_code},
            "Mounts": [{"Destination": collector.SECRET_TARGET, "Type": "bind", "RW": False}],
            "Config": {"Entrypoint": ["/usr/local/bin/python", "/sealed/entrypoint.py"],
                       "Cmd": ["run"], "Labels": {
                "factory.sandbox": "true",
                "factory.sandbox.peer_network_id": "edge-n2-sdk-lab",
                "factory.sandbox.peer_network_name": collector.NETWORK,
                "factory.sandbox.peer_alias": "edge-n2-sdk",
                "factory.sandbox.peer_port": "17331",
                "factory.sandbox.peer_internal": "true",
                "factory.sandbox.secret_output_suppressed": "true",
            }},
            "HostConfig": {"PortBindings": {}, "NetworkMode": collector.NETWORK,
                           "Privileged": False, "PublishAllPorts": False},
            "NetworkSettings": {"Ports": {}, "Networks": {
                collector.NETWORK: {"NetworkID": self.network_id,
                                    "Aliases": ["edge-n2-sdk"]}}},
        }

    def wait(self, container_id: str) -> int:
        assert container_id == self.container_id
        return self.wait_code

    def network(self, network_id: str) -> dict:
        assert network_id == self.network_id
        return {"Id": network_id, "Name": collector.NETWORK, "Internal": True,
                "Labels": {"factory.sandbox.owner": "python-factory",
                           "factory.sandbox.peer_network_id": "edge-n2-sdk-lab"},
                "Containers": {"other": {}} if self.network_attached else {}}

    def copy_tar(self, container_id: str, name: str) -> bytes:
        assert container_id == self.container_id
        self.copies.append(name)
        if name not in self.files:
            raise collector.CollectionError("missing evidence")
        return _tar(Path(name).name, self.files[name], symlink=name == self.symlink_name)

    def remove(self, container_id: str) -> None:
        self.removals.append(container_id)
        if self.remove_fails:
            raise collector.CollectionError("cleanup failed")

    def remove_network(self, network_id: str) -> None:
        self.network_removals.append(network_id)
        if self.network_cleanup_fails:
            raise collector.CollectionError("network removal failed")


def _peer(spec: dict, index: int, scenario: dict) -> dict:
    other = 1 - index
    ports = (22001, 22002)
    measurements = {
        "schema_version": 1,
        "samples_ms": {name: [10.0 + index] for name in contracts.LATENCY_METRICS},
        "write_failures": 0,
        "db_bytes": {"before_open": 10, "after_first_local_query": 12,
                     "after_reopen": 13, "after_sync": 20},
        "sdk_raw_stream_bytes": {"sent_delta": 5, "received_delta": 7,
                                 "unavailable_reason": None},
    }
    return {
        "status": "passed", "peer_id": spec["peer_id"],
        "device_id_sha256": _sha(spec["device_id"].encode()),
        "sdk_version": "5.2.0.dev0",
        "sdk_distribution_sha256": scenario["sdk_distribution_sha256"],
        "python_version": "3.12.14", "platform": "linux",
        "topology": {"mode": "loopback", "listen_interface": "127.0.0.1",
                     "listen_port": ports[index], "neighbor_host": "127.0.0.1",
                     "neighbor_port": ports[other]},
        "local_persistence": "passed", "exact_replay": "passed",
        "synced_observation_count": 2,
        "predictions": [
            {"observation_id_sha256": digit * 64,
             "input_id_sha256": input_digit * 64,
             "probability": 0.5, "decision": 1}
            for digit, input_digit in (("a", "b"), ("c", "d"))
        ],
        "elapsed_ms": 50.0,
        "measurements": measurements,
    }


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source = tmp_path / "sources"
    source.mkdir()
    scenario_bytes = (EXPERIMENT / "scenario-n2.json").read_bytes()
    scenario = json.loads(scenario_bytes)
    hashes = {}
    for name in ("run.py", "peer.py", "contracts.py", "protocol.md", "scenario-n2.json"):
        data = scenario_bytes if name == "scenario-n2.json" else (EXPERIMENT / name).read_bytes()
        (source / name).write_bytes(data)
        hashes[name] = _sha(data)
    hashes["model.json"] = scenario["model"]["file_sha256"]
    hashes["cohort.json"] = scenario["cohort"]["file_sha256"]
    (source / "sealed_pins.json").write_bytes(_encoded({
        "schema_version": 1, "sdk_distribution_sha256": scenario["sdk_distribution_sha256"],
        "entrypoint_sha256": _sha((EXPERIMENT / "sealed_entrypoint.py").read_bytes()),
        "files": hashes,
    }))
    (source / "sealed_entrypoint.py").write_bytes((EXPERIMENT / "sealed_entrypoint.py").read_bytes())
    monkeypatch.setattr(collector, "HERE", source)
    monkeypatch.setenv("SANDBOX_TMP_ROOT", str(tmp_path / "sandbox-tmp"))
    image_id = "sha256:" + "e" * 64
    build = {
        "schema_version": 1, "status": "license_free_preflight_passed",
        "final_image_id": image_id, "platform": "linux/arm64",
        "sdk_distribution_sha256": scenario["sdk_distribution_sha256"],
        "source_sha256": hashes,
        "entrypoint_sha256": _sha((source / "sealed_entrypoint.py").read_bytes()),
        "context_sha256": {**hashes,
                           "entrypoint.py": _sha((source / "sealed_entrypoint.py").read_bytes())},
        "preflight": {"status": "passed", "license_used": False, "peers_launched": False},
        "profile": {"name": "edge-n2-sdk", "container_name": "edge-n2-sdk",
                    "image": image_id, "secret_refs": ["ditto-offline-license"],
                    "peer_network": {"network_id": "edge-n2-sdk-lab", "alias": "edge-n2-sdk",
                                     "port": 17331, "internal": True}},
    }
    build_path = tmp_path / "build-evidence.json"
    build_path.write_bytes(_encoded(build))
    peers = [_peer(spec, i, scenario) for i, spec in enumerate(scenario["peers"])]
    files = {f"peer-results/{peer['peer_id']}.json": _encoded(peer) for peer in peers}
    run_id = str(uuid.uuid4())
    performance = runner.summarize_performance(peers, scenario["metrics_policy"])
    manifest = {
        "schema_version": 1, "run_id": run_id, "scenario_id": scenario["scenario_id"],
        "scenario_sha256": hashes["scenario-n2.json"],
        "artifact_hashes": {
            "model_file_sha256": hashes["model.json"],
            "model_payload_sha256": scenario["model"]["payload_sha256"],
            "cohort_file_sha256": hashes["cohort.json"],
            "cohort_payload_sha256": scenario["cohort"]["payload_sha256"],
            "sdk_distribution_sha256": scenario["sdk_distribution_sha256"],
        },
        "preflight": {"status": "passed", "parity_rows": 100,
                      "selected_engine_ids": scenario["cohort"]["engine_ids"]},
        "topology": {"transport": "static_tcp", "mode": "loopback", "peer_count": 2,
                     "peers": [peer["topology"] for peer in peers]},
        "source_timestamps_available": False,
        "source_timestamp_note": "The frozen FD001 endpoint cohort contains no event timestamp; none was inferred.",
        "sdk_integration_verified": True,
        "metrics_policy": scenario["metrics_policy"], "performance": performance,
        "eng184_closure_ready": False, "status": "passed",
        "performance_status": "insufficient_samples", "peers": peers,
        "ephemeral_store_sha256": {peer["peer_id"]: "f" * 64 for peer in peers},
        "files_sha256": {name: _sha(data) for name, data in files.items()},
        "finished_at_utc": "2026-09-30T12:00:00+00:00",
    }
    files["run-manifest.json"] = _encoded(manifest)
    files["run-index.json"] = _encoded({
        "schema_version": 1, "run_id": run_id, "status": "passed",
        "performance_status": "insufficient_samples",
        "run_manifest_sha256": _sha(files["run-manifest.json"]),
        "scenario_sha256": hashes["scenario-n2.json"],
        "runner_sha256": hashes["run.py"], "peer_runner_sha256": hashes["peer.py"],
        "contracts_sha256": hashes["contracts.py"], "protocol_sha256": hashes["protocol.md"],
    })
    container_id = "d" * 64
    model_path, cohort_path = source / "model.json", source / "cohort.json"
    model_path.write_bytes(b"fixture model is replaced by pinned artifact test")
    cohort_path.write_bytes(b"fixture cohort is replaced by pinned artifact test")
    expected = {item["observation_id_sha256"]: item for item in peers[0]["predictions"]}
    monkeypatch.setattr(collector, "_expected_predictions", lambda *_: expected)
    return (build_path, source / "scenario-n2.json", model_path, cohort_path,
            FakeDocker(files, container_id, image_id), container_id)


def test_collects_only_four_verified_files_then_removes_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "retained"
    result = collector.collect(container_id, build, scenario, model, cohort, output, docker)
    expected = {"run-index.json", "run-manifest.json", "peer-results/sensor-peer-a.json",
                "peer-results/sensor-peer-b.json"}
    assert set(docker.copies) == expected
    assert {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()} == expected
    assert docker.removals == [container_id]
    assert docker.network_removals == [docker.network_id]
    assert result["managed_network_removed"] is True
    assert result["performance_status"] == "insufficient_samples"
    assert result["eng184_closure_ready"] is False
    assert result["status"] == "passed"


@pytest.mark.parametrize("fault", ["missing", "hash_drift", "symlink", "nonzero_exit",
                                     "duplicate_json", "wrong_image", "cleanup_failed"])
def test_rejects_bad_evidence_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    if fault == "missing":
        del docker.files["run-manifest.json"]
    elif fault == "hash_drift":
        docker.files["peer-results/sensor-peer-a.json"] += b" "
    elif fault == "symlink":
        docker.symlink_name = "run-index.json"
    elif fault == "nonzero_exit":
        docker.wait_code = 1
    elif fault == "duplicate_json":
        docker.files["run-index.json"] = b'{"schema_version":1,"schema_version":1}'
    elif fault == "wrong_image":
        docker.image_id = "sha256:" + "0" * 64
    elif fault == "cleanup_failed":
        docker.remove_fails = True
    output = tmp_path / "retained"
    with pytest.raises(collector.CollectionError):
        collector.collect(container_id, build, scenario, model, cohort, output, docker)
    assert docker.removals == ([] if fault == "wrong_image" else [container_id])
    assert not output.exists()


def test_nonempty_managed_network_is_not_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    docker.network_attached = True
    result = collector.collect(container_id, build, scenario, model, cohort,
                               tmp_path / "retained", docker)
    assert docker.removals == [container_id]
    assert docker.network_removals == []
    assert result["managed_network_removed"] is False
    assert result["managed_network_cleanup"] == "nonempty"


def test_network_cleanup_failure_does_not_discard_verified_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    docker.network_cleanup_fails = True
    output = tmp_path / "retained"
    result = collector.collect(container_id, build, scenario, model, cohort, output, docker)
    assert output.is_dir()
    assert result["managed_network_cleanup"] == "failed"
    assert result["managed_network_removed"] is False
    assert docker.removals == [container_id]


def test_existing_output_rejects_before_container_is_touched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    output = tmp_path / "retained"
    output.mkdir()
    with pytest.raises(collector.CollectionError, match="output must be new"):
        collector.collect(container_id, build, scenario, model, cohort, output, docker)
    assert docker.removals == []
    assert docker.copies == []


def test_exit_one_retains_validated_failure_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario_path, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    scenario = contracts.read_json(scenario_path)
    failed = {"status": "failed", "peer_id": "sensor-peer-b",
              "error_type": "LocalWriteFailure", "write_failures": 1}
    name = "peer-results/sensor-peer-b.json"
    docker.files[name] = _encoded(failed)
    manifest = json.loads(docker.files["run-manifest.json"])
    peers = [manifest["peers"][0], failed]
    performance = runner.summarize_performance(peers, scenario["metrics_policy"])
    manifest.update(peers=peers, status="failed", sdk_integration_verified=False,
                    performance=performance, performance_status=performance["status"],
                    eng184_closure_ready=False)
    manifest["files_sha256"][name] = _sha(docker.files[name])
    docker.files["run-manifest.json"] = _encoded(manifest)
    index = json.loads(docker.files["run-index.json"])
    index.update(status="failed", performance_status=performance["status"],
                 run_manifest_sha256=_sha(docker.files["run-manifest.json"]))
    docker.files["run-index.json"] = _encoded(index)
    docker.exit_code = docker.wait_code = 1
    output = tmp_path / "retained"
    result = collector.collect(container_id, build, scenario_path, model, cohort, output, docker)
    assert result["status"] == "failed"
    assert result["performance_status"] == "failed"
    assert result["eng184_closure_ready"] is False
    assert output.is_dir()
    assert docker.removals == [container_id]


def test_exit_two_reports_bounded_reason_and_cleans_verified_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    docker.exit_code = docker.wait_code = 2
    with pytest.raises(collector.SealedExitError) as raised:
        collector.collect(container_id, build, scenario, model, cohort,
                          tmp_path / "retained", docker)
    assert raised.value.exit_code == 2
    assert docker.copies == []
    assert docker.removals == [container_id]


def test_exit_one_missing_manifest_reports_incomplete_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    docker.exit_code = docker.wait_code = 1
    del docker.files["run-manifest.json"]
    with pytest.raises(collector.IncompleteEvidenceError) as raised:
        collector.collect(container_id, build, scenario, model, cohort,
                          tmp_path / "retained", docker)
    assert raised.value.exit_code == 1
    assert docker.removals == [container_id]


def test_collector_holds_shared_sweeper_lock_through_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    original_remove = docker.remove
    observed = []

    def remove_while_locked(identifier: str) -> None:
        path = tmp_path / "sandbox-tmp" / "collector-locks" / f"{container_id}.lock"
        descriptor = os.open(path, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            observed.append(True)
        finally:
            os.close(descriptor)
        original_remove(identifier)

    docker.remove = remove_while_locked
    collector.collect(container_id, build, scenario, model, cohort,
                      tmp_path / "retained", docker)
    assert observed == [True]


def test_unowned_container_is_never_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    original = docker.inspect

    def unowned(identifier: str) -> dict:
        value = original(identifier)
        value["Config"]["Labels"]["factory.sandbox"] = "false"
        return value

    docker.inspect = unowned
    with pytest.raises(collector.CollectionError):
        collector.collect(container_id, build, scenario, model, cohort,
                          tmp_path / "retained", docker)
    assert docker.removals == []


def test_published_port_or_entrypoint_drift_is_rejected_before_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    original = docker.inspect

    def published(identifier: str) -> dict:
        value = original(identifier)
        value["HostConfig"]["PortBindings"] = {"17331/tcp": [{"HostPort": "17331"}]}
        return value

    docker.inspect = published
    with pytest.raises(collector.CollectionError):
        collector.collect(container_id, build, scenario, model, cohort,
                          tmp_path / "retained", docker)
    assert docker.removals == []
    docker.inspect = original
    def override_command(identifier: str) -> dict:
        value = original(identifier)
        value["Config"]["Cmd"] = ["sleep", "1"]
        return value

    docker.inspect = override_command
    with pytest.raises(collector.CollectionError):
        collector.collect(container_id, build, scenario, model, cohort,
                          tmp_path / "retained", docker)
    assert docker.removals == []
    docker.inspect = original
    (collector.HERE / "sealed_entrypoint.py").write_bytes(b"changed")
    with pytest.raises(collector.CollectionError):
        collector.collect(container_id, build, scenario, model, cohort,
                          tmp_path / "retained", docker)
    assert docker.removals == []


def test_prediction_tamper_rejected_despite_consistent_file_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    build, scenario, model, cohort, docker, container_id = _fixture(tmp_path, monkeypatch)
    name = "peer-results/sensor-peer-a.json"
    peer = json.loads(docker.files[name])
    peer["predictions"][0]["probability"] = 0.9
    docker.files[name] = _encoded(peer)
    manifest = json.loads(docker.files["run-manifest.json"])
    manifest["peers"][0] = peer
    manifest["files_sha256"][name] = _sha(docker.files[name])
    docker.files["run-manifest.json"] = _encoded(manifest)
    index = json.loads(docker.files["run-index.json"])
    index["run_manifest_sha256"] = _sha(docker.files["run-manifest.json"])
    docker.files["run-index.json"] = _encoded(index)
    with pytest.raises(collector.CollectionError, match="peer result"):
        collector.collect(container_id, build, scenario, model, cohort,
                          tmp_path / "retained", docker)
    assert docker.removals == [container_id]


def test_expected_predictions_derive_from_pinned_model_and_cohort(tmp_path: Path) -> None:
    model = {
        "schema_version": 2, "kind": contracts.MODEL_KIND,
        "window_cycles": 20, "channels_per_cycle": 24, "feature_count": 480,
        "threshold": 0.5, "scaler_mean": [0.0] * 480,
        "scaler_scale": [1.0] * 480, "coefficients": [0.0] * 480,
        "intercept": 0.0,
    }
    model["sha256"] = contracts.payload_digest(model)
    cohort = {
        "schema_version": 2, "kind": contracts.COHORT_KIND,
        "model_sha256": model["sha256"],
        "rows": [{"engine_id": index, "features": [0.0] * 480,
                  "expected_probability": 0.5, "expected_decision": 1,
                  "rul_label": 0} for index in range(1, 101)],
    }
    cohort["sha256"] = contracts.payload_digest(cohort)
    model_bytes, cohort_bytes = contracts.canonical_bytes(model), contracts.canonical_bytes(cohort)
    model_path, cohort_path = tmp_path / "model.json", tmp_path / "cohort.json"
    model_path.write_bytes(model_bytes)
    cohort_path.write_bytes(cohort_bytes)
    scenario = contracts.read_json(EXPERIMENT / "scenario-n2.json")
    scenario["model"].update(file_sha256=_sha(model_bytes), payload_sha256=model["sha256"])
    scenario["cohort"].update(file_sha256=_sha(cohort_bytes), payload_sha256=cohort["sha256"])
    build = {"source_sha256": {"model.json": _sha(model_bytes),
                               "cohort.json": _sha(cohort_bytes)}}
    expected = collector._expected_predictions(scenario, build, model_path, cohort_path)
    assert len(expected) == 2
    assert {item["probability"] for item in expected.values()} == {0.5}
    assert all("rul_label" not in item for item in expected.values())
    cohort_path.write_bytes(cohort_bytes + b" ")
    with pytest.raises(collector.CollectionError, match="differs from sealed source"):
        collector._expected_predictions(scenario, build, model_path, cohort_path)


def test_tar_boundary_rejects_extra_file_traversal_and_oversize() -> None:
    with pytest.raises(collector.CollectionError):
        collector._tar_file(_tar("other.json", b"{}"), "run-index.json")
    with pytest.raises(collector.CollectionError):
        collector._tar_file(_tar("../run-index.json", b"{}"), "run-index.json")
    with pytest.raises(collector.CollectionError):
        collector._tar_file(_tar("run-index.json", b"x" * (collector.MAX_FILE_BYTES + 1)),
                            "run-index.json")
    data = _tar("run-index.json", b"{}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        extra = io.BytesIO()
        with tarfile.open(fileobj=extra, mode="w") as second:
            for member in archive:
                second.addfile(member, archive.extractfile(member))
            extra_info = tarfile.TarInfo("license.txt")
            extra_info.size = 1
            second.addfile(extra_info, io.BytesIO(b"x"))
    with pytest.raises(collector.CollectionError):
        collector._tar_file(extra.getvalue(), "run-index.json")
