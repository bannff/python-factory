"""Contract tests for the routing runner boundary; the SDK here is fake."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

HERE = Path(__file__).parents[1] / "experiments/edge_models/edge-routing-sdk-001"
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("edge_routing_sdk_run_for_tests", HERE / "run.py")
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
peer_module = sys.modules["peer"]


def _fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "sealed"
    root.mkdir()
    for name in runner.SOURCE_NAMES:
        source = root / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes((Path(__file__).parents[1] / "experiments" / name).read_bytes())
    model = {"model": "pinned"}
    event = {"schema_version": 1, "event_id": "event-1", "source_time": "2026-01-01T00:00:00Z",
             "media_type": "image/jpeg", "image_base64": "/9j/2Q=="}
    policy = {"schema_version": 1, "policy_version": "policy-1", "group_id": "group-1",
              "session_id": "session-1", "coordinator_id": "peer-1", "task_id": "task-1",
              "task_kind": "inspect", "required_tag": "inspect",
              "capability_tags": {"cap-1": "inspect", "cap-2": "inspect"},
              "candidate_ids": {"peer-1": "candidate-1", "peer-2": "candidate-2"},
              "model_id": "visual", "model_version": "1", "runtime_id": "linux-arm64",
              "valid_until": "2099-01-01T00:00:00Z", "task_expires_at": "2099-01-01T00:00:00Z"}
    peers = [{"peer_id": f"peer-{i}", "listen_port": 17330 + i,
              "capability_id": f"cap-{i}", "candidate_id": f"candidate-{i}"} for i in (1, 2)]
    cohort = {"schema_version": 1, "source_event_sha256": runner.digest(runner.canonical(event)),
              "model_sha256": runner.digest(runner.canonical(model)),
              "expected_probability": 0.75, "expected_decision": 1, "tolerance": 0.0}
    files = {"model": model, "cohort": cohort, "source-event": event, "policy": policy}
    for name, value in files.items():
        (root / f"{name}.json").write_bytes(runner.canonical(value))
    scenario = {"schema_version": 1, "run_id": "run-1", "database_id": "routing-test",
                "group_id": "group-1", "session_id": "session-1", "coordinator_id": "peer-1",
                "peers": peers, "source_sha256": runner._source_digest(root),
                "source_event_sha256": runner.digest((root / "source-event.json").read_bytes()),
                "model_sha256": runner.digest((root / "model.json").read_bytes()),
                "cohort_sha256": runner.digest((root / "cohort.json").read_bytes()),
                "policy_sha256": runner.digest((root / "policy.json").read_bytes()),
                "sdk_distribution_sha256": "a" * 64,
                "records_module_sha256": runner.digest((root / runner.SOURCE_NAMES[3]).read_bytes()),
                "reducer_module_sha256": runner.digest((root / runner.SOURCE_NAMES[4]).read_bytes()),
                "sync_timeout_seconds": 1, "rejoin_timeout_seconds": 1}
    (root / "scenario.json").write_bytes(runner.canonical(scenario))
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setenv("EDGE_ROUTING_IMAGE_SHA256", "b" * 64)
    args = SimpleNamespace(**{name.replace("-", "_"): root / f"{name}.json"
                              for name in ("scenario", "model", "cohort", "source-event", "policy")})
    return root, args


def test_strict_pins_and_source_event_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root, args = _fixtures(tmp_path, monkeypatch)
    _, _, _, event, _, pins = runner._load_inputs(args)
    assert pins["source_sha256"] == runner._source_digest(root)
    assert event["image_bytes"] == b"\xff\xd8\xff\xd9"
    (root / "source-event.json").write_bytes((root / "source-event.json").read_bytes() + b" ")
    with pytest.raises(ValueError, match="pin mismatch"):
        runner._load_inputs(args)


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def __iter__(self):
        return iter(SimpleNamespace(value=row.copy()) for row in self.rows)

    def close(self):
        pass


def test_sdk_insert_and_query_durations_have_nonoverlapping_boundaries(
    monkeypatch: pytest.MonkeyPatch,
):
    rows = {}

    class Store:
        async def execute(self, query, params=None):
            if query.startswith("INSERT"):
                row = params["document"]
                rows[row["_id"]] = row
                return FakeResult([])
            return FakeResult(rows.values())

    peer = peer_module.SDKPeer("peer-1", object(), "license", object())
    peer.handle = SimpleNamespace(store=Store())
    ticks = iter((0, 10, 20, 50))
    monkeypatch.setattr(peer_module.time, "monotonic_ns", lambda: next(ticks))
    asyncio.run(peer.write({"record_id": "record-1", "producer_device_id": "peer-1"}))
    assert peer.write_total_ns == 10
    assert peer.query_total_ns == 30


class FakeSync:
    def __init__(self, handle):
        self.handle = handle

    def register_subscription(self, _query):
        return SimpleNamespace(cancel=lambda: None, close=lambda: None)

    def start(self):
        self.handle.connected = True
        self.handle.replicate()


class FakeDiskUsage:
    """Mirror the SDK's DiskUsage.item -> DiskUsageItem.size_in_bytes shape."""

    def __init__(self, handle):
        self.handle = handle

    @property
    def item(self):
        return SimpleNamespace(size_in_bytes=len(self.handle.rows) * 100)


class FakeHandle:
    handles: ClassVar[list[FakeHandle]] = []
    stores: ClassVar[dict[str, dict]] = {}

    def __init__(self, config):
        self.config = config
        self.rows = self.stores.setdefault(config.persistence_directory, {})
        self.store = self
        self.sync = FakeSync(self)
        self.disk_usage = FakeDiskUsage(self)
        self.connected = False
        self.handles.append(self)

    def set_offline_only_license_token(self, token):
        assert token == "mounted-license"

    async def execute(self, query, params=None):
        if query.startswith("INSERT"):
            record = params["document"]
            self.rows.setdefault(record["_id"], record)
            self.replicate()
            return FakeResult([])
        return FakeResult(self.rows.values())

    def replicate(self):
        for other in self.handles:
            if self.connected and other.connected and other is not self:
                other.rows.update(self.rows)
                self.rows.update(other.rows)

    async def close(self):
        self.connected = False
        self.handles.remove(self)


def _install_fake_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, predict):
    license_path = tmp_path / "license"
    license_path.write_text("mounted-license")
    monkeypatch.setattr(runner, "LICENSE", license_path)
    monkeypatch.setattr(runner, "_model_module", lambda: SimpleNamespace(
        load_artifact=lambda _: None, predict_image=predict,
    ))
    fake = types.ModuleType("ditto")
    fake.Ditto = SimpleNamespace(open=lambda config: asyncio.sleep(0, FakeHandle(config)))
    fake.DittoConfig = lambda **kwargs: SimpleNamespace(**kwargs)
    fake.DittoConfigConnect = SimpleNamespace(small_peers_only=lambda: object())
    fake.DittoTransportConfig = lambda: SimpleNamespace(
        listen=SimpleNamespace(tcp=SimpleNamespace()),
        connect=SimpleNamespace(tcp_servers=set()),
    )
    monkeypatch.setitem(sys.modules, "ditto", fake)
    monkeypatch.setitem(sys.modules, "sealed_entrypoint", SimpleNamespace(observed_sdk_digest=lambda: "a" * 64))
    FakeHandle.handles = []
    FakeHandle.stores = {}


def test_two_peer_route_uses_sdk_queries_and_emits_exact_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _, args = _fixtures(tmp_path, monkeypatch)
    scenario, model, cohort, event, policy, pins = runner._load_inputs(args)
    scored_images = []
    worker_scoring_state = []

    def predict(image, _model):
        scored_images.append(image)
        if len(scored_images) == 2:
            worker_scoring_state.append((
                [handle.config.persistence_directory for handle in FakeHandle.handles],
                {row["record_type"] for store in FakeHandle.stores.values()
                 for row in store.values() if row["producer_device_id"] == "peer-2"},
            ))
        return {"probability": 0.75, "decision": 1}

    _install_fake_runtime(tmp_path, monkeypatch, predict)
    cgroup_values = iter(((100, None), (250, None), (24_000_000, None)))
    monkeypatch.setattr(runner, "_cgroup_integer", lambda _name, _key=None: next(cgroup_values))
    output = tmp_path / "evidence"
    output.mkdir()
    asyncio.run(runner._execute(scenario, model, cohort, event, policy, pins, output))
    assert scored_images == [event["image_bytes"], event["image_bytes"]]
    assert len(worker_scoring_state) == 1
    open_stores, worker_records = worker_scoring_state[0]
    assert len(open_stores) == 1 and Path(open_stores[0]).name == "peer-2"
    assert "claim" in worker_records and "result" not in worker_records
    assert {p.relative_to(output).as_posix() for p in output.rglob("*.json")} == {
        "run-index.json", "peer-queries/peer-1.json", "peer-queries/peer-2.json"}
    index = json.loads((output / "run-index.json").read_text())
    coordinator = json.loads((output / "peer-queries/peer-1.json").read_text())
    worker = json.loads((output / "peer-queries/peer-2.json").read_text())
    assert index["run_status"] == "succeeded"
    assert index["selected"]["peer_id"] == "peer-2"
    assert len(coordinator["decision_query"]["documents"]) == 5
    assert coordinator["decision_query"]["queried_at"] < index["decision"]["decision_at"]
    observation = next(row for row in coordinator["local_write_documents"]
                       if row["record_type"] == "observation")
    assert observation["bounded_output"] == [{"name": "signal", "value": True}]
    assert observation["confidence_or_score"] == 0.75
    assert {row["record_type"] for row in worker["local_write_documents"]} == {
        "capability", "claim", "result"}
    result = next(row for row in worker["local_write_documents"] if row["record_type"] == "result")
    assert result["result_ref"] == f'sha256:{runner.digest(runner.canonical(worker["local_inference"]))}'
    assert worker["local_inference"]["probability"] == 0.75
    assert coordinator["local_inference"]["probability"] == 0.75
    assert coordinator["local_inference"]["inference_ms"] >= 0
    assert worker["local_inference"]["probability"] == 0.75
    for peer in (coordinator, worker):
        assert peer["measurements"]["disk_usage_before"]["value"] == 0
        assert peer["measurements"]["disk_usage_after"]["value"] == 700
        assert peer["measurements"]["disk_usage_growth"]["value"] == 700
        assert peer["measurements"]["write_total"]["value"] > 0
        assert peer["measurements"]["query_total"]["value"] > 0
    assert index["measurements"]["cgroup_cpu_usage"] == {
        "value": 150, "unit": "microseconds", "unavailable_reason": None}
    assert index["measurements"]["cgroup_memory_peak"] == {
        "value": 24_000_000, "unit": "bytes", "unavailable_reason": None}
    assert index["measurements"]["task_delivery"]["value"] >= 0
    assert index["measurements"]["rejoin_delivery"]["value"] >= 0
    assert index["measurements"]["end_to_end"]["value"] >= 0
    assert index["measurements"]["raw_mesh_bytes"] == {
        "value": None, "unit": "bytes", "unavailable_reason": "not_exposed_by_public_sdk"}
    assert {row["record_type"] for row in coordinator["reopen"]["documents"]} == {
        "session", "capability", "observation", "task"}
    assert len(coordinator["reopen"]["documents"]) == 5
    assert {row["record_type"] for row in worker["reopen"]["documents"]} == {
        "session", "capability", "observation", "task", "claim", "result"}
    assert len(worker["reopen"]["documents"]) == 7
    assert len(worker["after_rejoin"]["documents"]) == 7
    assert worker["after_rejoin"]["queried_at"] > index["reducer_as_of"]
    assert "image_base64" not in json.dumps(worker["after_rejoin"]["documents"])
    assert "mounted-license" not in json.dumps(worker)
    reducer_path = HERE.parent / "edge-mesh-coordinator-001/reducer.py"
    reducer_spec = importlib.util.spec_from_file_location("edge_routing_reducer_in_runner_test", reducer_path)
    assert reducer_spec and reducer_spec.loader
    reducer = importlib.util.module_from_spec(reducer_spec)
    monkeypatch.setitem(sys.modules, reducer_spec.name, reducer)
    reducer_spec.loader.exec_module(reducer)
    state = reducer.reduce_records(worker["after_rejoin"]["documents"],
                                   group_id=scenario["group_id"], session_id=scenario["session_id"],
                                   as_of=index["reducer_as_of"],
                                   trusted_coordinator_device_id=scenario["coordinator_id"],
                                   expected_policy_version=policy["policy_version"],
                                   expected_policy_sha256=pins["policy_sha256"])
    assert state.tasks[0].state == "completed"
    assert state.tasks[0].accepted_result_id == result["result_id"]
    collector_spec = importlib.util.spec_from_file_location(
        "edge_routing_collector_in_runner_test", HERE / "collect_sealed.py")
    assert collector_spec and collector_spec.loader
    collector = importlib.util.module_from_spec(collector_spec)
    monkeypatch.setitem(sys.modules, collector_spec.name, collector)
    collector_spec.loader.exec_module(collector)
    external_policy = collector.contracts.CollectionPolicy(
        pins=pins, peer_ids=("peer-1", "peer-2"), network_id="a" * 64,
        group_id=scenario["group_id"], session_id=scenario["session_id"],
        coordinator_id=scenario["coordinator_id"], policy_version=policy["policy_version"],
        capability_tags=policy["capability_tags"],
        expected_probability=cohort["expected_probability"],
        expected_decision=cohort["expected_decision"], score_tolerance=cohort["tolerance"],
        resource_nano_cpus=500_000_000, resource_memory_bytes=536_870_912)
    files = {path.relative_to(output).as_posix(): path.read_bytes()
             for path in output.rglob("*.json")}
    attestation = collector._construct(files, external_policy, 0)
    assert attestation.run_status == "succeeded"
    assert not FakeHandle.handles


def test_worker_must_read_task_through_own_sdk_store_before_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _, args = _fixtures(tmp_path, monkeypatch)
    scenario, model, cohort, event, policy, pins = runner._load_inputs(args)
    _install_fake_runtime(tmp_path, monkeypatch,
                          lambda *_: {"probability": 0.75, "decision": 1})
    original_execute = FakeHandle.execute

    async def hidden_task(self, query, params=None):
        result = await original_execute(self, query, params)
        if query == "SELECT * FROM edge_routing_records" and Path(self.config.persistence_directory).name == "peer-2":
            result.rows = [row for row in result.rows if row.get("record_type") != "task"]
        return result

    monkeypatch.setattr(FakeHandle, "execute", hidden_task)
    output = tmp_path / "evidence"
    output.mkdir()
    with pytest.raises(TimeoutError, match="did not converge"):
        asyncio.run(runner._execute(scenario, model, cohort, event, policy, pins, output))
    assert all(row["record_type"] != "claim"
               for store in FakeHandle.stores.values() for row in store.values())


def test_missing_replay_dependency_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _, args = _fixtures(tmp_path, monkeypatch)
    scenario, model, cohort, event, policy, pins = runner._load_inputs(args)
    _install_fake_runtime(tmp_path, monkeypatch,
                          lambda *_: {"probability": 0.75, "decision": 1})
    original_spec = importlib.util.spec_from_file_location

    def missing_reducer(name, location, *args, **kwargs):
        if Path(location) == runner.ROOT / runner.SOURCE_NAMES[4]:
            return None
        return original_spec(name, location, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "spec_from_file_location", missing_reducer)
    output = tmp_path / "evidence"
    output.mkdir()
    with pytest.raises(runner.RunFailure, match="routing_failed"):
        asyncio.run(runner._execute(scenario, model, cohort, event, policy, pins, output))
    assert not (output / "run-index.json").exists()


def test_rejoin_without_backlog_delivery_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _, args = _fixtures(tmp_path, monkeypatch)
    scenario, model, cohort, event, policy, pins = runner._load_inputs(args)
    _install_fake_runtime(tmp_path, monkeypatch,
                          lambda *_: {"probability": 0.75, "decision": 1})
    original_replicate = FakeHandle.replicate

    def lose_rejoin_delivery(self):
        if any(row["record_type"] == "claim"
               for store in FakeHandle.stores.values() for row in store.values()):
            return
        original_replicate(self)

    monkeypatch.setattr(FakeHandle, "replicate", lose_rejoin_delivery)
    output = tmp_path / "evidence"
    output.mkdir()
    with pytest.raises(TimeoutError, match="did not converge"):
        asyncio.run(runner._execute(scenario, model, cohort, event, policy, pins, output))
    assert not (output / "run-index.json").exists()


def test_coordinator_score_mismatch_stops_before_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _, args = _fixtures(tmp_path, monkeypatch)
    scenario, model, cohort, event, policy, pins = runner._load_inputs(args)
    scored_images = []

    def predict(image, _model):
        scored_images.append(image)
        return {"probability": 0.25, "decision": 0}

    _install_fake_runtime(tmp_path, monkeypatch, predict)
    output = tmp_path / "evidence"
    output.mkdir()
    with pytest.raises(runner.RunFailure, match="routing_failed"):
        asyncio.run(runner._execute(scenario, model, cohort, event, policy, pins, output))
    assert scored_images == [event["image_bytes"]]
    assert all(row["record_type"] != "observation"
               for store in FakeHandle.stores.values() for row in store.values())


def test_controlled_failure_is_index_only(tmp_path: Path):
    output = tmp_path / "evidence"
    output.mkdir()
    runner._failure(output, {name: "a" * 64 for name in (
        "run_id", "scenario_sha256", "image_sha256", "source_sha256", "source_event_sha256",
        "model_sha256", "cohort_sha256", "sdk_distribution_sha256", "policy_sha256",
        "records_module_sha256", "reducer_module_sha256")},
        {"group_id": "group-1", "session_id": "session-1", "coordinator_id": "peer-1"},
        {"policy_version": "policy-1"}, "sdk_start_failed")
    assert {p.name for p in output.iterdir()} == {"run-index.json"}
    assert json.loads((output / "run-index.json").read_text())["run_status"] == "failed"
