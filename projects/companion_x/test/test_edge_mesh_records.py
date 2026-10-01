"""Boundary and replay invariants for the proposed edge mesh records."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError


EXPERIMENT = Path(__file__).parents[1] / "experiments/edge_models/edge-mesh-coordinator-001"
SPEC = importlib.util.spec_from_file_location("edge_mesh_records", EXPERIMENT / "records.py")
assert SPEC is not None and SPEC.loader is not None
records = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = records
SPEC.loader.exec_module(records)
SHA = "a" * 64
SHA_B = "b" * 64
NOW = "2026-09-30T12:00:00Z"
LATER = "2026-09-30T12:10:00Z"


def envelope(kind: str, source_id: str, **changes: object) -> dict:
    value = {
        "schema_version": 1,
        "record_type": kind,
        "record_id": records.deterministic_record_id(kind, "group-1", "session-1", source_id),
        "group_id": "group-1",
        "session_id": "session-1",
        "producer_device_id": "peer-1",
        "created_at": NOW,
        "causation_ids": [],
    }
    value.update(changes)
    return value


def examples() -> list[dict]:
    return [
        envelope(
            "capability", "cap-1:0", capability_id="cap-1", revision=0,
            role="audio", model_id="tiny-audio",
            model_version="1", artifact_sha256=SHA, input_modalities=["audio"],
            output_schema_version=1, runtime_id="arm64-linux", valid_from=NOW,
            expires_at=LATER, status="available", authorization_scope="session",
            policy_version="policy-1",
        ),
        envelope(
            "observation", "obs-1", observation_id="obs-1", source_event_id="event-1",
            source_time=NOW, task_kind="inspect", model_id="tiny-audio", model_version="1",
            artifact_sha256=SHA, output_schema_version=1,
            bounded_output=[{"name": "class_id", "value": 1}], confidence_or_score=0.8,
            input_ref=f"sha256:{SHA_B}", retention_class="device-local",
        ),
        envelope(
            "task", "task-1:0", task_id="task-1", task_kind="inspect", state="proposed",
            expires_at=LATER, required_capabilities=["cap-1"], observation_ids=["obs-1"],
            policy_version="policy-1", policy_sha256=SHA, scenario_sha256=SHA_B,
            revision=0, terminal_reason=None, authorized_device_ids=["peer-1"],
        ),
        envelope(
            "claim", "claim-1:0", claim_id="claim-1", claim_revision=0,
            task_id="task-1",
            claimant_device_id="peer-1", capability_id="cap-1", task_revision=0,
            issued_at=NOW, expires_at=LATER, claim_status="proposed",
            authorization_scope="session", policy_version="policy-1",
        ),
        envelope(
            "result", "result-1", result_id="result-1", task_id="task-1",
            claim_id="claim-1", claim_revision=0,
            worker_device_id="peer-1", task_revision=0,
            outcome="completed", result_ref=f"sha256:{SHA}", completed_at=NOW,
            model_id="tiny-audio", artifact_sha256=SHA,
            input_ref=f"sha256:{SHA_B}", policy_version="policy-1", policy_sha256=SHA,
            scenario_sha256=SHA_B,
        ),
        envelope(
            "session", "session-1:0", coordinator_device_id="peer-1",
            session_kind="inspection", opened_at=NOW,
            closed_at=None, policy_version="policy-1", membership_epoch=0, status="open",
            authorized_device_ids=["peer-1"],
        ),
    ]


@pytest.mark.parametrize("index", range(6))
def test_each_record_parses_to_frozen_typed_model_with_stable_bytes(index: int) -> None:
    raw = examples()[index]
    model = records.parse_record(raw)
    assert model.record_type == raw["record_type"]
    assert records.canonical_bytes(model) == records.canonical_bytes(records.parse_record(records.canonical_bytes(model)))
    with pytest.raises(ValidationError):
        model.group_id = "other"


@pytest.mark.parametrize("index", range(6))
def test_unknown_fields_bad_version_and_forged_id_fail_closed(index: int) -> None:
    raw = examples()[index]
    for key, value in (("private_audio", "data"), ("schema_version", 2), ("record_id", "forged")):
        altered = {**raw, key: value}
        with pytest.raises((ValidationError, ValueError)):
            records.parse_record(altered)


def test_duplicate_json_keys_and_nonfinite_scores_are_rejected() -> None:
    raw = examples()[1]
    with pytest.raises(ValueError, match="duplicate"):
        records.parse_record(b'{"schema_version":1,"schema_version":1}')
    raw["confidence_or_score"] = float("nan")
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(raw)


@pytest.mark.parametrize("field,value", [
    ("group_id", "../group"), ("session_id", "a/b"),
    ("producer_device_id", " peer"), ("created_at", "2026-09-30T12:00:00-07:00"),
    ("created_at", "2026-09-30T12:00:00"),
    ("created_at", "2026-09-30T12:00:00.1234567Z"),
])
def test_unsafe_identity_or_non_utc_time_is_rejected(field: str, value: str) -> None:
    raw = examples()[1]
    raw[field] = value
    if field != "created_at":
        raw["record_id"] = records.deterministic_record_id("observation", raw["group_id"], raw["session_id"], "obs-1")
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(raw)


def test_output_allows_only_bounded_numeric_or_boolean_schema() -> None:
    raw = examples()[1]
    for name, value in (
        ("raw_audio", "abc"), ("transcript", "hello"),
        ("gps_latitude", 37.7), ("email_address", "a@example.com"),
        ("label", "alert"), ("class_id", 65536),
        ("score", float("nan")), ("score", 1.1),
        ("signal", "true"), ("severity_code", 6),
    ):
        altered = {**raw, "bounded_output": [{"name": name, "value": value}]}
        with pytest.raises((ValidationError, ValueError)):
            records.parse_record(altered)
    for name, value in (("signal", True), ("class_id", 1), ("score", 0.75),
                        ("count", 3), ("severity_code", 2)):
        records.parse_record({**raw, "bounded_output": [{"name": name, "value": value}]})


def test_result_requires_input_policy_and_scenario_provenance() -> None:
    for field in ("input_ref", "policy_version", "policy_sha256", "scenario_sha256",
                  "task_revision", "claim_revision"):
        raw = examples()[4]
        del raw[field]
        with pytest.raises((ValidationError, ValueError)):
            records.parse_record(raw)


@pytest.mark.parametrize("index", [0, 1])
def test_unknown_output_schema_version_fails_closed(index: int) -> None:
    raw = examples()[index]
    raw["output_schema_version"] = 2
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(raw)


def test_status_transitions_have_distinct_deterministic_record_ids() -> None:
    capability, claim = examples()[0], examples()[3]
    transition_at = "2026-09-30T12:05:00Z"
    capability_update = {
        **capability, "revision": 1, "status": "unavailable", "created_at": transition_at,
        "record_id": records.deterministic_record_id(
            "capability", "group-1", "session-1", "cap-1:1"
        ),
    }
    claim_update = {
        **claim, "claim_revision": 1, "claim_status": "withdrawn", "created_at": transition_at,
        "record_id": records.deterministic_record_id(
            "claim", "group-1", "session-1", "claim-1:1"
        ),
    }
    assert records.parse_record(capability_update).record_id != capability["record_id"]
    assert records.parse_record(claim_update).record_id != claim["record_id"]


@pytest.mark.parametrize("state", ["active", "completed", "abstained", "cancelled"])
def test_task_proposal_cannot_assert_derived_state(state: str) -> None:
    raw = examples()[2]
    raw["state"] = state
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(raw)


def test_task_proposal_cannot_assert_terminal_reason() -> None:
    raw = examples()[2]
    raw["terminal_reason"] = "completed"
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(raw)


def test_session_declares_its_coordinator_and_matching_producer() -> None:
    valid = examples()[5]
    assert records.parse_record(valid).coordinator_device_id == "peer-1"
    for change in ({"coordinator_device_id": "peer-2"}, {"producer_device_id": "peer-2"},
                   {"coordinator_device_id": "../peer"}):
        with pytest.raises((ValidationError, ValueError)):
            records.parse_record({**valid, **change})
    missing = {key: value for key, value in valid.items() if key != "coordinator_device_id"}
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(missing)


def test_fractional_utc_instants_drive_window_order_not_string_sort() -> None:
    capability = examples()[0]
    capability["valid_from"] = "2026-09-30T12:00:00.1Z"
    capability["expires_at"] = "2026-09-30T12:00:00Z"
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(capability)
    capability["expires_at"] = "2026-09-30T12:00:00.2Z"
    assert records.parse_record(capability).expires_at == capability["expires_at"]

    task = examples()[2]
    task["created_at"] = "2026-09-30T12:00:00.1Z"
    task["expires_at"] = "2026-09-30T12:00:00Z"
    with pytest.raises((ValidationError, ValueError)):
        records.parse_record(task)


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=20))
def test_record_id_determinism_and_identity_separation(source: str) -> None:
    first = records.deterministic_record_id("observation", "group-1", "session-1", source)
    assert first == records.deterministic_record_id("observation", "group-1", "session-1", source)
    assert first != records.deterministic_record_id("observation", "group-2", "session-1", source)
    assert first != records.deterministic_record_id("task", "group-1", "session-1", source)


def test_canonical_form_independent_of_input_key_order() -> None:
    raw = examples()[0]
    reverse = dict(reversed(list(raw.items())))
    assert records.canonical_bytes(records.parse_record(raw)) == records.canonical_bytes(records.parse_record(reverse))
    assert json.loads(records.canonical_bytes(records.parse_record(raw))) == raw
