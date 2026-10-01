"""Fixed N=2 Ditto SDK routing run; evidence is checked again by the host collector."""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from peer import SDKBoundaryError, SDKPeer, wait_for_records

ROOT = Path("/sealed")
LICENSE = Path("/run/secrets/ditto-offline-license")
OUTPUT = Path("/evidence/routing-run-001")
SOURCE_NAMES = (
    "edge_models/edge-routing-sdk-001/run.py",
    "edge_models/edge-routing-sdk-001/peer.py",
    "edge_models/edge-visual-quality-mesh-001/model.py",
    "edge_models/edge-mesh-coordinator-001/records.py",
    "edge_models/edge-mesh-coordinator-001/reducer.py",
)
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,95}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
UTC_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")
COLLECTION_LIMIT = 64


class RunFailure(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stamp(after: str | None = None) -> str:
    moment = datetime.now(UTC)
    if after is not None:
        previous = datetime.fromisoformat(after)
        deadline = time.monotonic() + 1
        while moment <= previous:
            if time.monotonic() >= deadline:
                raise RunFailure("timed_out")
            time.sleep(0.0001)
            moment = datetime.now(UTC)
    return moment.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _id(value: Any) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise ValueError("invalid bounded ID")
    return value


def _sha(value: Any) -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        raise ValueError("invalid SHA-256 digest")
    return value


def _time(value: Any) -> str:
    if not isinstance(value, str) or UTC_TIME.fullmatch(value) is None:
        raise ValueError("invalid UTC time")
    datetime.fromisoformat(value)
    return value


def _json(path: Path, *, max_bytes: int = 24 * 1024 * 1024) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("sealed input is not a regular file")
    data = path.read_bytes()
    if len(data) > max_bytes:
        raise ValueError("sealed input exceeds size limit")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, item in pairs:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = item
        return out

    value = json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    if type(value) is not dict:
        raise ValueError("sealed input must be a JSON object")
    return value, data


def _fields(value: dict[str, Any], names: set[str]) -> None:
    if set(value) != names:
        raise ValueError("sealed input fields differ from contract")


def _record_id(kind: str, group: str, session: str, source: str) -> str:
    return f"{kind}-{digest(canonical([kind, group, session, source]))}"


def _row(kind: str, scenario: dict[str, Any], producer: str, source: str,
         created: str, **fields: Any) -> dict[str, Any]:
    return {"schema_version": 1, "record_type": kind,
            "record_id": _record_id(kind, scenario["group_id"], scenario["session_id"], source),
            "group_id": scenario["group_id"], "session_id": scenario["session_id"],
            "producer_device_id": producer, "created_at": created, "causation_ids": [], **fields}


def _source_digest(root: Path) -> str:
    entries = {name: digest((root / name).read_bytes()) for name in SOURCE_NAMES}
    return digest(canonical(entries))


def _load_inputs(options: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any],
                                                        dict[str, Any], dict[str, Any], dict[str, Any],
                                                        dict[str, str]]:
    scenario, scenario_bytes = _json(options.scenario, max_bytes=8192)
    model, model_bytes = _json(options.model)
    cohort, cohort_bytes = _json(options.cohort, max_bytes=8192)
    event, event_bytes = _json(options.source_event)
    policy, policy_bytes = _json(options.policy, max_bytes=8192)
    _fields(scenario, {"schema_version", "run_id", "database_id", "group_id", "session_id",
                       "coordinator_id", "peers", "source_sha256", "source_event_sha256",
                       "model_sha256", "cohort_sha256", "policy_sha256", "sdk_distribution_sha256",
                       "records_module_sha256", "reducer_module_sha256",
                       "sync_timeout_seconds", "rejoin_timeout_seconds"})
    if type(scenario["schema_version"]) is not int or scenario["schema_version"] != 1:
        raise ValueError("scenario version differs")
    for name in ("run_id", "database_id", "group_id", "session_id", "coordinator_id"):
        _id(scenario[name])
    for name in ("source_sha256", "source_event_sha256", "model_sha256", "cohort_sha256",
                 "policy_sha256", "sdk_distribution_sha256", "records_module_sha256",
                 "reducer_module_sha256"):
        _sha(scenario[name])
    peers = scenario["peers"]
    if type(peers) is not list or len(peers) != 2:
        raise ValueError("exactly two peers required")
    for peer in peers:
        if type(peer) is not dict:
            raise ValueError("invalid peer")
        _fields(peer, {"peer_id", "listen_port", "capability_id", "candidate_id"})
        for name in ("peer_id", "capability_id", "candidate_id"):
            _id(peer[name])
        if type(peer["listen_port"]) is not int or not 1024 <= peer["listen_port"] <= 65535:
            raise ValueError("invalid peer port")
    for name in ("peer_id", "listen_port", "capability_id", "candidate_id"):
        if len({peer[name] for peer in peers}) != 2:
            raise ValueError("peer values must be distinct")
    if peers[0]["peer_id"] != scenario["coordinator_id"]:
        raise ValueError("first peer must coordinate")
    for name in ("sync_timeout_seconds", "rejoin_timeout_seconds"):
        if type(scenario[name]) is not int or not 1 <= scenario[name] <= 300:
            raise ValueError("invalid timeout")
    expected = {"source_sha256": _source_digest(ROOT), "source_event_sha256": digest(event_bytes),
                "model_sha256": digest(model_bytes), "cohort_sha256": digest(cohort_bytes),
                "policy_sha256": digest(policy_bytes),
                "records_module_sha256": digest((ROOT / SOURCE_NAMES[3]).read_bytes()),
                "reducer_module_sha256": digest((ROOT / SOURCE_NAMES[4]).read_bytes())}
    if any(scenario[name] != value for name, value in expected.items()):
        raise ValueError("sealed scenario pin mismatch")
    image_sha = _sha(os.environ.get("EDGE_ROUTING_IMAGE_SHA256"))
    _fields(event, {"schema_version", "event_id", "source_time", "media_type", "image_base64"})
    if type(event["schema_version"]) is not int or event["schema_version"] != 1 or event["media_type"] != "image/jpeg":
        raise ValueError("source event type differs")
    _id(event["event_id"])
    _time(event["source_time"])
    if not isinstance(event["image_base64"], str) or len(event["image_base64"]) > 22_000_000:
        raise ValueError("source image size differs")
    try:
        image = base64.b64decode(event["image_base64"], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError("source image encoding differs") from error
    if not image or len(image) > 16 * 1024 * 1024:
        raise ValueError("source image size differs")
    _fields(policy, {"schema_version", "policy_version", "group_id", "session_id",
                     "coordinator_id", "task_id", "task_kind", "required_tag",
                     "capability_tags", "candidate_ids", "model_id", "model_version",
                     "runtime_id", "valid_until", "task_expires_at"})
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise ValueError("policy version differs")
    for name in ("policy_version", "group_id", "session_id", "coordinator_id", "task_id",
                 "task_kind", "required_tag", "model_id", "model_version", "runtime_id"):
        _id(policy[name])
    for name in ("group_id", "session_id", "coordinator_id"):
        if policy[name] != scenario[name]:
            raise ValueError("policy identity differs")
    for name in ("valid_until", "task_expires_at"):
        _time(policy[name])
        if datetime.fromisoformat(policy[name]) <= datetime.now(UTC) + timedelta(seconds=30):
            raise ValueError("frozen policy has expired")
    if (type(policy["capability_tags"]) is not dict or
            policy["capability_tags"] != {p["capability_id"]: policy["required_tag"] for p in peers}
            or type(policy["candidate_ids"]) is not dict or
            policy["candidate_ids"] != {p["peer_id"]: p["candidate_id"] for p in peers}):
        raise ValueError("capability policy differs")
    _fields(cohort, {"schema_version", "source_event_sha256", "model_sha256",
                     "expected_probability", "expected_decision", "tolerance"})
    if (type(cohort["schema_version"]) is not int or cohort["schema_version"] != 1 or
            cohort["source_event_sha256"] != digest(event_bytes) or
            cohort["model_sha256"] != digest(model_bytes)):
        raise ValueError("cohort pins differ")
    if (type(cohort["expected_probability"]) not in (int, float) or
            not 0 <= cohort["expected_probability"] <= 1 or
            type(cohort["expected_decision"]) is not int or cohort["expected_decision"] not in (0, 1) or
            type(cohort["tolerance"]) not in (int, float) or not 0 <= cohort["tolerance"] <= 0.001):
        raise ValueError("cohort score contract differs")
    pins = {"run_id": scenario["run_id"], "scenario_sha256": digest(scenario_bytes),
            "image_sha256": image_sha, **{name: scenario[name] for name in expected},
            "sdk_distribution_sha256": scenario["sdk_distribution_sha256"]}
    event["image_bytes"] = image
    return scenario, model, cohort, event, policy, pins


def _query_evidence(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if len(rows) > COLLECTION_LIMIT:
        raise RunFailure("sdk_query_failed")
    return {"queried_at": stamp(), "documents": [rows[key] for key in sorted(rows)]}


def _hash_record(row: dict[str, Any]) -> str:
    return digest(canonical(row))


def _candidate(peer: dict[str, Any], cap: dict[str, Any], tag: str) -> dict[str, str]:
    return {"candidate_id": peer["candidate_id"], "peer_id": peer["peer_id"],
            "capability_record_id": cap["record_id"], "capability_sha256": _hash_record(cap),
            "capability_id": peer["capability_id"], "required_tag": tag}


def _score_peer(peer: SDKPeer, visual: Any, image_bytes: bytes, model: dict[str, Any],
                cohort: dict[str, Any]) -> tuple[dict[str, float | int], float]:
    started_ns = time.monotonic_ns()
    score = peer.score_image(visual, image_bytes, model)
    elapsed_ms = (time.monotonic_ns() - started_ns) / 1_000_000
    if (type(score) is not dict or set(score) != {"probability", "decision"} or
            type(score["probability"]) not in (int, float) or
            not math.isfinite(score["probability"]) or
            type(score["decision"]) is not int or score["decision"] not in (0, 1) or
            abs(score["probability"] - cohort["expected_probability"]) > cohort["tolerance"] or
            score["decision"] != cohort["expected_decision"]):
        raise RunFailure("routing_failed")
    return score, elapsed_ms


def _metric(value: float | None, unit: str, reason: str | None = None) -> dict[str, Any]:
    return {"value": value, "unit": unit, "unavailable_reason": reason}


def _cgroup_integer(filename: str, key: str | None = None) -> tuple[int | None, str | None]:
    """Read one cgroup v2 counter; absence is reported rather than inferred."""
    root = Path("/sys/fs/cgroup")
    if not (root / "cgroup.controllers").is_file():
        return None, "unsupported_cgroup_v2"
    try:
        text = (root / filename).read_text(encoding="ascii")
        if key is not None:
            text = next(line.split()[1] for line in text.splitlines()
                        if len(line.split()) == 2 and line.split()[0] == key)
        value = int(text.strip())
        if value < 0:
            raise ValueError
        return value, None
    except (OSError, StopIteration, ValueError):
        return None, "read_failed"


def _counter_delta(before: tuple[int | None, str | None],
                   after: tuple[int | None, str | None]) -> tuple[int | None, str | None]:
    if before[0] is None:
        return None, before[1]
    if after[0] is None:
        return None, after[1]
    if after[0] < before[0]:
        return None, "counter_reset"
    return after[0] - before[0], None


def _disk_growth(before: tuple[int | None, str | None],
                 after: tuple[int | None, str | None]) -> dict[str, Any]:
    if before[0] is None or after[0] is None:
        return _metric(None, "bytes", before[1] or after[1] or "read_failed")
    if after[0] < before[0]:
        return _metric(None, "bytes", "counter_reset")
    return _metric(after[0] - before[0], "bytes")


def _peer_measurements(peer: SDKPeer, before: tuple[int | None, str | None],
                       after: tuple[int | None, str | None]) -> dict[str, Any]:
    return {
        "disk_usage_before": _metric(before[0], "bytes", before[1]),
        "disk_usage_after": _metric(after[0], "bytes", after[1]),
        "disk_usage_growth": _disk_growth(before, after),
        "write_total": _metric(peer.write_total_ns // 1000, "microseconds"),
        "query_total": _metric(peer.query_total_ns // 1000, "microseconds"),
    }


def _inference_evidence(score: dict[str, float | int], inference_ms: float,
                        pins: dict[str, str]) -> dict[str, Any]:
    return {"schema_version": 1, "source_event_sha256": pins["source_event_sha256"],
            "model_sha256": pins["model_sha256"], "probability": float(score["probability"]),
            "decision": int(score["decision"]), "inference_ms": inference_ms}


def _write_json(path: Path, value: dict[str, Any]) -> str:
    data = canonical(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return digest(data)


def _failure(output: Path, pins: dict[str, str], scenario: dict[str, Any],
             policy: dict[str, Any], reason: str) -> None:
    _write_json(output / "run-index.json", {
        "schema_version": 2, "run_status": "failed", "failure_reason": reason,
        "pins": pins, "group_id": scenario["group_id"], "session_id": scenario["session_id"],
        "coordinator_id": scenario["coordinator_id"], "policy_version": policy["policy_version"],
        "decision": None, "selected": None, "reducer_as_of": None, "files_sha256": {},
        "measurements": None,
    })


def _model_module() -> Any:
    path = ROOT / SOURCE_NAMES[2]
    spec = importlib.util.spec_from_file_location("edge_routing_visual_model", path)
    if spec is None or spec.loader is None:
        raise RunFailure("routing_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _replay_reopened_task(rows: dict[str, dict[str, Any]], scenario: dict[str, Any],
                          policy: dict[str, Any], pins: dict[str, str],
                          claim_id: str, result_id: str, as_of: str) -> None:
    """Require the selected peer's persisted SDK readback to yield the chosen result."""
    path = ROOT / SOURCE_NAMES[4]
    if digest(path.read_bytes()) != pins["reducer_module_sha256"]:
        raise RunFailure("routing_failed")
    try:
        spec = importlib.util.spec_from_file_location("edge_routing_reducer_replay", path)
        if spec is None or spec.loader is None:
            raise RunFailure("routing_failed")
        reducer = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = reducer
        spec.loader.exec_module(reducer)
        state = reducer.reduce_records(tuple(rows.values()), group_id=scenario["group_id"],
                                       session_id=scenario["session_id"], as_of=as_of,
                                       trusted_coordinator_device_id=scenario["coordinator_id"],
                                       expected_policy_version=policy["policy_version"],
                                       expected_policy_sha256=pins["policy_sha256"])
    except Exception as error:
        raise RunFailure("routing_failed") from error
    task = next((item for item in state.tasks if item.task_id == policy["task_id"]), None)
    if (task is None or task.state != "completed" or task.winner_claim_id != claim_id
            or task.accepted_result_id != result_id):
        raise RunFailure("routing_failed")


async def _execute(scenario: dict[str, Any], model: dict[str, Any], cohort: dict[str, Any],
                   event: dict[str, Any], policy: dict[str, Any], pins: dict[str, str],
                   output: Path) -> None:
    end_to_end_started_ns = time.monotonic_ns()
    cgroup_cpu_before = _cgroup_integer("cpu.stat", "usage_usec")
    from ditto import Ditto, DittoConfig, DittoConfigConnect, DittoTransportConfig
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from sealed_entrypoint import observed_sdk_digest

    if observed_sdk_digest() != pins["sdk_distribution_sha256"]:
        raise RunFailure("sdk_start_failed")

    sdk = type("DittoAPI", (), {"Ditto": Ditto, "DittoConfig": DittoConfig,
                               "DittoConfigConnect": DittoConfigConnect,
                               "DittoTransportConfig": DittoTransportConfig})
    token = LICENSE.read_text(encoding="utf-8").strip()
    if not token:
        raise RunFailure("sdk_start_failed")
    visual = _model_module()
    visual.load_artifact(model)
    peer_specs = scenario["peers"]
    peers: list[SDKPeer] = []
    disk_before: dict[str, tuple[int | None, str | None]] = {}
    temporary_stores = tempfile.TemporaryDirectory(prefix="edge-routing-stores-")
    store_root = Path(temporary_stores.name)
    try:
        for spec in peer_specs:
            peers.append(await SDKPeer.open(spec["peer_id"], scenario["database_id"],
                                            store_root / spec["peer_id"], token, sdk))
            disk_before[spec["peer_id"]] = await peers[-1].disk_usage_item()
        coordinator, worker = peers
        now = stamp()
        session = _row("session", scenario, coordinator.peer_id,
                       f'{scenario["session_id"]}:0', now,
                       coordinator_device_id=coordinator.peer_id, session_kind=policy["task_kind"],
                       opened_at=now, closed_at=None, policy_version=policy["policy_version"],
                       membership_epoch=0, status="open",
                       authorized_device_ids=[p["peer_id"] for p in peer_specs])
        await coordinator.write(session)
        caps = []
        for spec, peer in zip(peer_specs, peers, strict=True):
            when = stamp()
            cap = _row("capability", scenario, peer.peer_id,
                       f'{spec["capability_id"]}:0', when,
                       capability_id=spec["capability_id"], revision=0,
                       role=policy["required_tag"], model_id=policy["model_id"],
                       model_version=policy["model_version"], artifact_sha256=pins["model_sha256"],
                       input_modalities=["image"], output_schema_version=1,
                       runtime_id=policy["runtime_id"], valid_from=when,
                       expires_at=policy["valid_until"], status="available",
                       authorization_scope="session", policy_version=policy["policy_version"])
            await peer.write(cap)
            caps.append(cap)
        coordinator_score, coordinator_inference_ms = _score_peer(
            coordinator, visual, event["image_bytes"], model, cohort)
        coordinator_inference = _inference_evidence(coordinator_score, coordinator_inference_ms, pins)
        observed_at = stamp()
        observation = _row("observation", scenario, coordinator.peer_id,
                           event["event_id"], observed_at,
                           observation_id=event["event_id"], source_event_id=event["event_id"],
                           source_time=event["source_time"], task_kind=policy["task_kind"],
                           model_id=policy["model_id"], model_version=policy["model_version"],
                           artifact_sha256=pins["model_sha256"], output_schema_version=1,
                           bounded_output=[{"name": "signal", "value": bool(coordinator_score["decision"])}],
                           confidence_or_score=float(coordinator_score["probability"]),
                           input_ref=f'sha256:{pins["source_event_sha256"]}',
                           retention_class="device-local")
        await coordinator.write(observation)
        task = _row("task", scenario, coordinator.peer_id,
                    f'{policy["task_id"]}:0', stamp(), task_id=policy["task_id"],
                    task_kind=policy["task_kind"], state="proposed",
                    expires_at=policy["task_expires_at"],
                    required_capabilities=[p["capability_id"] for p in peer_specs],
                    observation_ids=[observation["observation_id"]],
                    policy_version=policy["policy_version"], policy_sha256=pins["policy_sha256"],
                    scenario_sha256=pins["scenario_sha256"], revision=0, terminal_reason=None,
                    authorized_device_ids=[p["peer_id"] for p in peer_specs])
        await coordinator.write(task)
        initial = {r["record_id"] for r in (session, *caps, observation, task)}
        task_delivery_started_ns = time.monotonic_ns()
        for index, peer in enumerate(peers):
            peer.start_sync(peer_specs[index]["listen_port"], peer_specs[1 - index]["listen_port"])
        predecision = await wait_for_records(coordinator, initial, scenario["sync_timeout_seconds"])
        if any(predecision[r["record_id"]] != r for r in (session, *caps, observation, task)):
            raise RunFailure("sdk_query_failed")
        worker_predecision = await wait_for_records(worker, initial, scenario["sync_timeout_seconds"])
        task_delivery_ms = (time.monotonic_ns() - task_delivery_started_ns) / 1_000_000
        if worker_predecision != predecision:
            raise RunFailure("sdk_query_failed")
        decision_query = _query_evidence(predecision)
        decision_at = stamp(after=decision_query["queried_at"])
        candidates = [_candidate(spec, cap, policy["required_tag"])
                      for spec, cap in zip(peer_specs, caps, strict=True)]
        decision = {"decision_at": decision_at, "task_record_id": task["record_id"],
                    "task_sha256": _hash_record(task),
                    "observation_record_id": observation["record_id"],
                    "observation_sha256": _hash_record(observation),
                    "session_record_id": session["record_id"],
                    "session_sha256": _hash_record(session),
                    "required_tags": [policy["required_tag"]], "candidates": candidates,
                    "eligible_candidate_ids": [p["candidate_id"] for p in peer_specs]}
        selected_at = stamp(after=decision_at)
        # Both stores persist the proposed task before the physical disconnect.
        for peer in peers:
            await peer.close()
        await worker.reopen()
        if await worker.query() != predecision:
            raise RunFailure("sdk_reopen_failed")
        claim_id = f'claim:{policy["task_id"]}:{worker.peer_id}'
        claim_time = stamp(after=selected_at)
        claim = _row("claim", scenario, worker.peer_id, f"{claim_id}:0", claim_time,
                     claim_id=claim_id, claim_revision=0, task_id=policy["task_id"],
                     claimant_device_id=worker.peer_id,
                     capability_id=peer_specs[1]["capability_id"], task_revision=0,
                     issued_at=claim_time, expires_at=policy["task_expires_at"],
                     claim_status="proposed", authorization_scope="session",
                     policy_version=policy["policy_version"])
        await worker.write(claim)
        # The selected peer reads the locally preloaded image only after selection.
        score, inference_ms = _score_peer(worker, visual, event["image_bytes"], model, cohort)
        local_inference = _inference_evidence(score, inference_ms, pins)
        result_id = f'result:{policy["task_id"]}:{worker.peer_id}'
        completed_at = stamp(after=claim_time)
        result = _row("result", scenario, worker.peer_id, result_id, completed_at,
                      result_id=result_id, task_id=policy["task_id"], claim_id=claim_id,
                      claim_revision=0, worker_device_id=worker.peer_id, task_revision=0,
                      outcome="completed", result_ref=f"sha256:{digest(canonical(local_inference))}",
                      completed_at=completed_at, model_id=policy["model_id"],
                      artifact_sha256=pins["model_sha256"],
                      input_ref=f'sha256:{pins["source_event_sha256"]}',
                      policy_version=policy["policy_version"],
                      policy_sha256=pins["policy_sha256"],
                      scenario_sha256=pins["scenario_sha256"])
        await worker.write(result)
        all_rows = {r["record_id"]: r for r in (session, *caps, observation, task, claim, result)}
        await worker.close()
        reopened = []
        for peer in peers:
            try:
                await peer.reopen()
                rows = await peer.query()
            except SDKBoundaryError as error:
                raise RunFailure("sdk_reopen_failed") from error
            if any(rows.get(row["record_id"]) != row for row in peer.local_writes):
                raise RunFailure("sdk_reopen_failed")
            reopened.append(_query_evidence(rows))
        if ({row["record_id"]: row for row in (session, *caps, observation, task)}
                != {row["record_id"]: row for row in reopened[0]["documents"]}
                or {row["record_id"]: row for row in reopened[1]["documents"]} != all_rows):
            raise RunFailure("sdk_reopen_failed")
        reducer_as_of = stamp(after=completed_at)
        _replay_reopened_task({row["record_id"]: row for row in reopened[1]["documents"]},
                              scenario, policy, pins, claim_id, result_id, reducer_as_of)
        rejoin_delivery_started_ns = time.monotonic_ns()
        for index, peer in enumerate(peers):
            try:
                peer.start_sync(peer_specs[index]["listen_port"], peer_specs[1 - index]["listen_port"])
            except SDKBoundaryError as error:
                raise RunFailure("sdk_rejoin_failed") from error
        after_rejoin = []
        for peer in peers:
            rows = await wait_for_records(peer, set(all_rows), scenario["rejoin_timeout_seconds"])
            if rows != all_rows:
                raise RunFailure("sdk_rejoin_failed")
            query = _query_evidence(rows)
            if query["queried_at"] <= reducer_as_of:
                raise RunFailure("sdk_query_failed")
            after_rejoin.append(query)
        rejoin_delivery_ms = (time.monotonic_ns() - rejoin_delivery_started_ns) / 1_000_000
        disk_after = {peer.peer_id: await peer.disk_usage_item() for peer in peers}
        cpu_after = _cgroup_integer("cpu.stat", "usage_usec")
        cpu_delta, cpu_reason = _counter_delta(cgroup_cpu_before, cpu_after)
        memory_peak = _cgroup_integer("memory.peak")
        run_measurements = {
            "cgroup_cpu_usage": _metric(cpu_delta, "microseconds", cpu_reason),
            "cgroup_memory_peak": _metric(memory_peak[0], "bytes", memory_peak[1]),
            "task_delivery": _metric(task_delivery_ms, "milliseconds"),
            "rejoin_delivery": _metric(rejoin_delivery_ms, "milliseconds"),
            "end_to_end": _metric((time.monotonic_ns() - end_to_end_started_ns) / 1_000_000,
                                   "milliseconds"),
            "raw_mesh_bytes": _metric(None, "bytes", "not_exposed_by_public_sdk"),
        }
        files = {}
        for index, peer in enumerate(peers):
            name = f"peer-queries/{peer.peer_id}.json"
            files[name] = _write_json(output / name, {
                "schema_version": 2, "peer_id": peer.peer_id,
                "sdk_distribution_sha256": pins["sdk_distribution_sha256"],
                "local_write_documents": peer.local_writes,
                "local_inference": coordinator_inference if index == 0 else local_inference,
                "measurements": _peer_measurements(
                    peer, disk_before[peer.peer_id], disk_after[peer.peer_id]),
                "decision_query": decision_query if index == 0 else None,
                "reopen": reopened[index], "after_rejoin": after_rejoin[index],
                "disconnect_observed": peer.disconnected, "rejoin_observed": peer.rejoined,
            })
        selected = {"candidate_id": peer_specs[1]["candidate_id"], "peer_id": worker.peer_id,
                    "claim_record_id": claim["record_id"], "claim_sha256": _hash_record(claim),
                    "result_record_id": result["record_id"], "result_sha256": _hash_record(result),
                    "selected_at": selected_at}
        _write_json(output / "run-index.json", {
            "schema_version": 2, "run_status": "succeeded", "failure_reason": None,
            "pins": pins, "group_id": scenario["group_id"], "session_id": scenario["session_id"],
            "coordinator_id": scenario["coordinator_id"], "policy_version": policy["policy_version"],
            "decision": decision, "selected": selected, "reducer_as_of": reducer_as_of,
            "measurements": run_measurements,
            "files_sha256": files,
        })
    finally:
        try:
            for peer in peers:
                if peer.handle is not None:
                    await peer.close()
        finally:
            temporary_stores.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("scenario", "model", "cohort", "source-event", "policy", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    options = parser.parse_args(argv)
    if (options.scenario != ROOT / "scenario.json" or options.model != ROOT / "model.json"
            or options.cohort != ROOT / "cohort.json" or options.source_event != ROOT / "source-event.json"
            or options.policy != ROOT / "policy.json" or options.output != OUTPUT):
        print('{"status":"failed","reason":"sdk_start_failed"}')
        return 1
    scenario = policy = pins = None
    reason = "sdk_start_failed"
    try:
        scenario, model, cohort, event, policy, pins = _load_inputs(options)
        options.output.mkdir(parents=True, exist_ok=False)
        asyncio.run(_execute(scenario, model, cohort, event, policy, pins, options.output))
        print('{"status":"succeeded"}')
        return 0
    except RunFailure as error:
        reason = error.reason
    except TimeoutError:
        reason = "timed_out"
    except SDKBoundaryError as error:
        reason = error.reason
    except Exception:  # noqa: BLE001 - redact arbitrary SDK, image decoder, and input failures.
        reason = "sdk_start_failed"
    if scenario is not None and policy is not None and pins is not None:
        try:
            if not options.output.exists():
                options.output.mkdir(parents=True)
            for path in options.output.glob("peer-queries/*.json"):
                path.unlink()
            query_dir = options.output / "peer-queries"
            if query_dir.is_dir():
                query_dir.rmdir()
            _failure(options.output, pins, scenario, policy, reason)
        except OSError:
            pass
    print(json.dumps({"status": "failed", "reason": reason}, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
