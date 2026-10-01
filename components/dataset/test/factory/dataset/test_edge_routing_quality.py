"""Contract checks for reviewed live-SDK edge routing evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from factory.dataset.runtime.quality import evaluate_quality


def _evidence(root: Path, record_id: str, name: str, payload: dict) -> dict[str, str]:
    content = json.dumps(payload, sort_keys=True).encode()
    path = root / f"{record_id}-{name}.json"
    path.write_bytes(content)
    return {"uri": path.as_uri(), "sha256": hashlib.sha256(content).hexdigest()}


def stored_routing_example(root: Path, record_id: str, split: str) -> dict:
    """Synthetic contract fixture; never treated as real training evidence."""
    candidate_id = f"device-{record_id}"
    candidate = {
        "candidate_id": candidate_id,
        "capability_id": f"cap-{record_id}",
        "capabilities": ("review",),
        "role": "reviewer", "model_id": "tiny-reviewer",
        "model_artifact_sha256": "d" * 64,
        "observed_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-01-01T00:01:00Z",
        "status": "available", "battery_pct": 80,
        "cpu_utilization_pct": 10, "memory_available_mib": 128,
        "estimated_link_latency_ms": 15,
    }
    common = {"schema_version": "1.0", "record_id": record_id}
    source_id = f"source-{record_id}"
    source_ref = _evidence(root, record_id, "source", {
        **common, "kind": "source_event", "source_event_id": source_id,
        "group_id": f"episode-{record_id}",
        "session_id": f"session-{record_id}", "task_id": f"task-{record_id}",
        "source_event_at": "2026-01-01T00:00:00Z",
    })
    snapshot_ref = _evidence(root, record_id, "snapshot", {
        **common, "kind": "candidate_snapshot",
        "decision_at": "2026-01-01T00:00:01Z",
        "candidates": [candidate], "eligible_candidate_ids": [candidate_id],
    })
    execution_ref = _evidence(root, record_id, "execution", {
        **common, "kind": "route_execution", "source_event_id": source_id,
        "candidate_id": candidate_id, "selected_at": "2026-01-01T00:00:02Z",
        "selection_propensity": 1.0,
    })
    outcome_ref = _evidence(root, record_id, "outcome", {
        **common, "kind": "route_outcome", "run_id": f"run-{record_id}",
        "sdk_version": "5.2.0", "candidate_id": candidate_id,
        "observed_at": "2026-01-01T00:00:03Z",
        "succeeded": record_id != "test",
        "execution_sha256": execution_ref["sha256"],
    })
    adjudication_ref = _evidence(root, record_id, "review", {
        **common, "kind": "route_adjudication", "reviewer_ref": "reviewer-a",
        "verdict": "accepted", "reviewed_at": "2026-01-01T00:00:04Z",
        "outcome_sha256": outcome_ref["sha256"],
    })
    return {
        "schema_version": "1.0", "record_id": record_id, "split": split,
        "features": {
            "group_id": f"episode-{record_id}",
            "session_id": f"session-{record_id}",
            "task_id": f"task-{record_id}",
            "source_event_id": source_id,
            "source_event_ref": source_ref,
            "source_event_at": "2026-01-01T00:00:00Z",
            "decision_at": "2026-01-01T00:00:01Z",
            "task_kind": "review-alert",
            "policy_version": "p1",
            "policy_sha256": "a" * 64,
            "reducer_sha256": "b" * 64,
            "scenario_sha256": "c" * 64,
            "required_capabilities": ("review",),
            "candidate_snapshot_ref": snapshot_ref,
            "candidates": (candidate,),
            "eligible_candidate_ids": (candidate_id,),
        },
        "executed_route": {
            "candidate_id": candidate_id,
            "selection_propensity": 1.0,
            "selected_at": "2026-01-01T00:00:02Z",
            "execution_ref": execution_ref,
        },
        "outcome": {
            "outcome_ref": outcome_ref,
            "run_id": f"run-{record_id}",
            "sdk_version": "5.2.0",
            "provenance_kind": "ditto_sdk_live",
            "observed_at": "2026-01-01T00:00:03Z",
            "succeeded": record_id != "test",
            "review": {
                "reviewer_ref": "reviewer-a",
                "adjudication_ref": adjudication_ref,
                "reviewed_at": "2026-01-01T00:00:04Z",
                "verdict": "accepted",
            },
        },
    }


def _three_records(root: Path) -> list[dict]:
    return [
        stored_routing_example(root, "train", "train"),
        stored_routing_example(root, "validation", "validation"),
        stored_routing_example(root, "test", "test"),
    ]


def test_complete_typed_fixture_still_lacks_trusted_live_provenance(tmp_path: Path) -> None:
    result = evaluate_quality(_three_records(tmp_path), record_schema="edge_routing_example")
    assert not result.passed
    assert result.checks["evidence_integrity"].startswith("passed:")
    assert result.checks["evidence_semantics"].startswith("passed:")
    assert result.checks["reviewed_label_structure"].startswith("passed:")
    assert result.checks["trusted_run_provenance"].startswith("failed:")


def test_empty_records_have_no_labels(tmp_path: Path) -> None:
    result = evaluate_quality([], record_schema="edge_routing_example")
    assert not result.passed
    assert result.checks["record_count"] == "failed: 0 records"
    assert "no reviewed" in result.checks["reviewed_label_structure"]


@pytest.mark.parametrize("change", ["duplicate", "collision"])
def test_duplicate_ids_and_same_id_different_content_fail(tmp_path: Path, change: str) -> None:
    records = _three_records(tmp_path)
    repeated = json.loads(json.dumps(records[0]))
    if change == "collision":
        repeated["features"]["task_kind"] = "different-task"
    records.append(repeated)
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert "train" in result.checks["record_ids"]
    assert ("train" in result.checks["record_id_content_collisions"]) == (change == "collision")


@pytest.mark.parametrize("field,check", [
    ("group_id", "episode_split_isolation"),
    ("session_id", "session_split_isolation"),
    ("task_id", "task_split_isolation"),
    ("source_event_id", "source_event_split_isolation"),
])
def test_identity_cannot_cross_splits(tmp_path: Path, field: str, check: str) -> None:
    records = _three_records(tmp_path)
    records[1]["features"][field] = records[0]["features"][field]
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert result.checks[check].startswith("failed:")


@pytest.mark.parametrize("path,check", [
    (("features", "source_event_ref"), "source_digest_split_isolation"),
    (("features", "candidate_snapshot_ref"), "candidate_snapshot_split_isolation"),
    (("executed_route", "execution_ref"), "execution_digest_split_isolation"),
    (("outcome", "outcome_ref"), "outcome_digest_split_isolation"),
    (("outcome", "review", "adjudication_ref"), "adjudication_digest_split_isolation"),
])
def test_content_digest_cannot_cross_splits(
    tmp_path: Path, path: tuple[str, ...], check: str,
) -> None:
    records = _three_records(tmp_path)
    first, second = records[0], records[1]
    for part in path[:-1]:
        first, second = first[part], second[part]
    second[path[-1]] = first[path[-1]]
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert result.checks[check].startswith("failed:")


@pytest.mark.parametrize("path", [
    ("features", "source_event_ref"),
    ("features", "candidate_snapshot_ref"),
    ("executed_route", "execution_ref"),
    ("outcome", "outcome_ref"),
    ("outcome", "review", "adjudication_ref"),
])
def test_evidence_bytes_must_match_content_digest(
    tmp_path: Path, path: tuple[str, ...],
) -> None:
    records = _three_records(tmp_path)
    ref = records[0]
    for part in path:
        ref = ref[part]
    Path(ref["uri"].removeprefix("file://")).write_bytes(b"tampered")
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert "train" in result.checks["evidence_integrity"]


def test_symlinked_evidence_is_rejected(tmp_path: Path) -> None:
    records = _three_records(tmp_path)
    target = Path(records[0]["outcome"]["outcome_ref"]["uri"].removeprefix("file://"))
    alias = tmp_path / "outcome-alias.json"
    alias.symlink_to(target)
    records[0]["outcome"]["outcome_ref"]["uri"] = alias.as_uri()
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert "train" in result.checks["evidence_integrity"]


@pytest.mark.parametrize("payload", [b"not JSON", b'{"id":1,"id":2}', b"[]"])
def test_referenced_evidence_must_be_unambiguous_json_object(
    tmp_path: Path, payload: bytes,
) -> None:
    records = _three_records(tmp_path)
    ref = records[0]["outcome"]["review"]["adjudication_ref"]
    Path(ref["uri"].removeprefix("file://")).write_bytes(payload)
    ref["sha256"] = hashlib.sha256(payload).hexdigest()
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert "train" in result.checks["evidence_integrity"]


@pytest.mark.parametrize("path,field,replacement", [
    (("features", "source_event_ref"), "record_id", "other-record"),
    (("features", "source_event_ref"), "source_event_id", "other-event"),
    (("features", "candidate_snapshot_ref"), "eligible_candidate_ids", []),
    (("features", "candidate_snapshot_ref"), "candidates", []),
    (("executed_route", "execution_ref"), "candidate_id", "other-device"),
    (("executed_route", "execution_ref"), "selected_at", "2026-01-01T00:00:03Z"),
    (("outcome", "outcome_ref"), "run_id", "other-run"),
    (("outcome", "outcome_ref"), "sdk_version", "0.0.0"),
    (("outcome", "outcome_ref"), "succeeded", False),
    (("outcome", "outcome_ref"), "execution_sha256", "0" * 64),
    (("outcome", "review", "adjudication_ref"), "verdict", "rejected"),
    (("outcome", "review", "adjudication_ref"), "reviewer_ref", "other-reviewer"),
    (("outcome", "review", "adjudication_ref"), "reviewed_at", "2026-01-01T00:00:05Z"),
    (("outcome", "review", "adjudication_ref"), "outcome_sha256", "0" * 64),
])
def test_content_addressed_but_semantically_unrelated_payload_is_rejected(
    tmp_path: Path, path: tuple[str, ...], field: str, replacement: object,
) -> None:
    records = _three_records(tmp_path)
    ref = records[0]
    for part in path:
        ref = ref[part]
    evidence_path = Path(ref["uri"].removeprefix("file://"))
    payload = json.loads(evidence_path.read_bytes())
    payload[field] = replacement
    changed = json.dumps(payload, sort_keys=True).encode()
    evidence_path.write_bytes(changed)
    ref["sha256"] = hashlib.sha256(changed).hexdigest()
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert result.checks["evidence_integrity"].startswith("passed:")
    assert "train" in result.checks["evidence_semantics"]


@pytest.mark.parametrize("change", ["censored", "simulated", "rejected"])
def test_censored_or_nonreviewed_outcomes_never_become_negative_labels(
    tmp_path: Path, change: str,
) -> None:
    records = _three_records(tmp_path)
    if change == "censored":
        records[0]["outcome"] = None
    elif change == "simulated":
        records[0]["outcome"]["provenance_kind"] = "simulated"
    else:
        records[0]["outcome"]["review"]["verdict"] = "rejected"
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert "train" in result.checks["reviewed_label_structure"]


@pytest.mark.parametrize("change", ["ineligible", "early_route", "early_outcome"])
def test_route_and_time_invariants_fail_at_schema_boundary(
    tmp_path: Path, change: str,
) -> None:
    records = _three_records(tmp_path)
    if change == "ineligible":
        records[0]["features"]["eligible_candidate_ids"] = ()
    elif change == "early_route":
        records[0]["executed_route"]["selected_at"] = "2025-12-31T23:59:59Z"
    else:
        records[0]["outcome"]["observed_at"] = "2025-12-31T23:59:59Z"
    result = evaluate_quality(records, record_schema="edge_routing_example")
    assert not result.passed
    assert result.checks["schema"].startswith("failed:")
