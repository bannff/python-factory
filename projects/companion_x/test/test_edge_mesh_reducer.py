"""Deterministic, side-effect-free coordination over accepted record sets."""

from __future__ import annotations

import importlib.util
import sys
from itertools import permutations
from pathlib import Path

import pytest
from hypothesis import given, strategies as st


EXPERIMENT = Path(__file__).parents[1] / "experiments/edge_models/edge-mesh-coordinator-001"
SPEC = importlib.util.spec_from_file_location("edge_mesh_reducer", EXPERIMENT / "reducer.py")
assert SPEC is not None and SPEC.loader is not None
reducer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reducer
SPEC.loader.exec_module(reducer)
SHA_A, SHA_B = "a" * 64, "b" * 64
NOW, LATER = "2026-09-30T12:00:00Z", "2026-09-30T12:10:00Z"
AT = "2026-09-30T12:01:00Z"


def record(kind: str, source: str, peer: str = "peer-1", **fields: object) -> dict:
    return {
        "schema_version": 1, "record_type": kind,
        "record_id": reducer.deterministic_record_id(kind, "group-1", "session-1", source),
        "group_id": "group-1", "session_id": "session-1",
        "producer_device_id": peer, "created_at": NOW, "causation_ids": [],
        **fields,
    }


def scenario() -> list[dict]:
    records = [record(
        "session", "session-1:0", session_kind="inspection", opened_at=NOW,
        closed_at=None, policy_version="policy-1", membership_epoch=0,
        status="open", authorized_device_ids=["peer-1", "peer-2"],
        coordinator_device_id="peer-1",
    )]
    for peer in ("peer-1", "peer-2"):
        records.append(record(
            "capability", f"cap-{peer}:0", peer, capability_id=f"cap-{peer}", revision=0,
            role="audio", model_id="tiny-audio", model_version="1",
            artifact_sha256=SHA_A, input_modalities=["audio"],
            output_schema_version=1, runtime_id="arm64-linux", valid_from=NOW,
            expires_at=LATER, status="available", authorization_scope="session",
            policy_version="policy-1",
        ))
    records.extend([
        record(
            "observation", "obs-1", observation_id="obs-1", source_event_id="event-1",
            source_time=NOW, task_kind="inspect", model_id="tiny-audio",
            model_version="1", artifact_sha256=SHA_A, output_schema_version=1,
            bounded_output=[{"name": "signal", "value": True}], confidence_or_score=0.8,
            input_ref=f"sha256:{SHA_B}", retention_class="device-local",
        ),
        record(
            "task", "task-1:0", task_id="task-1", task_kind="inspect", state="proposed",
            expires_at=LATER, required_capabilities=["cap-peer-1", "cap-peer-2"],
            observation_ids=["obs-1"], policy_version="policy-1",
            policy_sha256=SHA_A, scenario_sha256=SHA_B, revision=0,
            terminal_reason=None, authorized_device_ids=["peer-1", "peer-2"],
        ),
    ])
    for peer in ("peer-1", "peer-2"):
        records.append(record(
            "claim", f"claim-{peer}:0", peer, claim_id=f"claim-{peer}", claim_revision=0,
            task_id="task-1", claimant_device_id=peer, capability_id=f"cap-{peer}",
            task_revision=0, issued_at=NOW, expires_at=LATER,
            claim_status="proposed", authorization_scope="session",
            policy_version="policy-1",
        ))
    records.append(record(
        "result", "result-1", result_id="result-1", task_id="task-1",
        claim_id="claim-peer-1", claim_revision=0, worker_device_id="peer-1", task_revision=0,
        outcome="completed", result_ref=f"sha256:{SHA_A}", completed_at=NOW,
        model_id="tiny-audio", artifact_sha256=SHA_A,
        input_ref=f"sha256:{SHA_B}", policy_version="policy-1",
        policy_sha256=SHA_A, scenario_sha256=SHA_B,
    ))
    return records


def reduce(rows: list[dict], *, at: str = AT, policy_sha256: str = SHA_A):
    return reducer.reduce_records(rows, group_id="group-1", session_id="session-1", as_of=at,
                                  trusted_coordinator_device_id="peer-1",
                                  expected_policy_version="policy-1",
                                  expected_policy_sha256=policy_sha256)


def decisions(state) -> dict[str, str]:
    return {entry.claim_id: entry.reason for entry in state.claim_decisions}


def test_complete_set_order_independent_duplicate_replay_and_result_provenance() -> None:
    rows = scenario()
    first = reduce(rows)
    assert first.tasks[0].winner_claim_id == "claim-peer-1"
    assert decisions(first) == {"claim-peer-1": "winner", "claim-peer-2": "loser"}
    assert first.result_decisions[0].reason == "accepted"
    for order in permutations(rows[-3:]):
        replayed = reduce(rows[:-3] + list(order) + [rows[-3], rows[-1]])
        assert replayed.state_digest == first.state_digest
        assert replayed.canonical_bytes == first.canonical_bytes


@given(st.permutations(tuple(range(7))))
def test_seeded_input_permutations_have_identical_state(order: list[int]) -> None:
    rows = scenario()
    original = reduce(rows)
    changed = [rows[index] for index in order] + rows[7:]
    assert reduce(changed).state_digest == original.state_digest


def test_same_id_different_bytes_fails_closed() -> None:
    rows = scenario()
    altered = {**rows[1], "status": "unavailable"}
    with pytest.raises(ValueError, match="different|collision|conflict"):
        reduce(rows + [altered])


def test_state_digest_commits_to_content_even_if_decision_is_unchanged() -> None:
    rows = scenario()
    altered = scenario()
    altered[3] = {**altered[3], "confidence_or_score": 0.81}
    original_state = reduce(rows)
    changed_state = reduce(altered)
    assert original_state.tasks == changed_state.tasks
    assert original_state.accepted_record_ids == changed_state.accepted_record_ids
    assert original_state.accepted_record_set_digest != changed_state.accepted_record_set_digest
    assert original_state.state_digest != changed_state.state_digest


def test_cross_group_and_unauthorized_producer_fail_closed() -> None:
    rows = scenario()
    other = {**rows[3], "group_id": "group-2"}
    other["record_id"] = reducer.deterministic_record_id("observation", "group-2", "session-1", "obs-1")
    with pytest.raises(ValueError, match="group|session"):
        reduce(rows[:3] + [other] + rows[4:])
    rows = scenario()
    rows[3] = {**rows[3], "producer_device_id": "stranger"}
    with pytest.raises(ValueError, match="member|authorized"):
        reduce(rows)


@pytest.mark.parametrize("change,reason", [
    ({"task_revision": 1}, "stale_task_revision"),
    ({"authorization_scope": "group"}, "scope_mismatch"),
    ({"policy_version": "policy-2"}, "policy_mismatch"),
    ({"claim_status": "withdrawn"}, "withdrawn"),
])
def test_ineligible_claims_have_explicit_reasons(change: dict, reason: str) -> None:
    rows = scenario()
    rows[-2] = {**rows[-2], **change}
    state = reduce(rows)
    assert decisions(state)["claim-peer-2"] == reason
    assert state.tasks[0].winner_claim_id == "claim-peer-1"


def test_expiry_and_task_authorization_exclude_claims() -> None:
    rows = scenario()
    rows[2] = {**rows[2], "expires_at": "2026-09-30T12:00:30Z"}
    assert decisions(reduce(rows[:-1]))["claim-peer-2"] == "expired_capability"
    rows = scenario()
    rows[4] = {**rows[4], "authorized_device_ids": ["peer-1"]}
    assert decisions(reduce(rows[:-1]))["claim-peer-2"] == "unauthorized_device"
    assert decisions(reduce(rows[:-1], at=LATER))["claim-peer-1"] == "expired_task"


@pytest.mark.parametrize("field,value,reason", [
    ("policy_sha256", SHA_B, "policy_mismatch"),
    ("scenario_sha256", SHA_A, "scenario_mismatch"),
    ("artifact_sha256", SHA_B, "model_mismatch"),
    ("input_ref", f"sha256:{SHA_A}", "input_mismatch"),
    ("task_revision", 1, "stale_task_revision"),
    ("claim_revision", 1, "stale_claim_revision"),
])
def test_result_provenance_fails_closed(field: str, value: object, reason: str) -> None:
    rows = scenario()
    rows[-1] = {**rows[-1], field: value}
    assert reduce(rows).result_decisions[0].reason == reason


def test_self_consistent_task_and_result_policy_forgery_cannot_route() -> None:
    rows = scenario()
    rows[4] = {**rows[4], "policy_sha256": SHA_B}
    rows[-1] = {**rows[-1], "policy_sha256": SHA_B}
    with pytest.raises(ValueError, match="pinned policy"):
        reduce(rows)


def test_result_for_losing_claim_is_rejected() -> None:
    rows = scenario()
    rows[-1] = {**rows[-1], "claim_id": "claim-peer-2", "worker_device_id": "peer-2",
                "producer_device_id": "peer-2"}
    assert reduce(rows).result_decisions[0].reason == "losing_claim"


def test_completed_result_survives_later_claim_expiry() -> None:
    rows = scenario()
    for index in (5, 6):
        rows[index] = {**rows[index], "expires_at": "2026-09-30T12:02:00Z"}
    state = reduce(rows, at="2026-09-30T12:03:00Z")
    assert state.result_decisions[0].reason == "accepted"
    assert state.tasks[0].state == "completed"


def test_new_task_revision_invalidates_old_claim_and_result() -> None:
    rows = scenario()
    revision = {**rows[4],
                "record_id": reducer.deterministic_record_id("task", "group-1", "session-1", "task-1:1"),
                "created_at": "2026-09-30T12:02:00Z", "revision": 1}
    state = reduce(rows[:-1] + [revision], at="2026-09-30T12:03:00Z")
    assert state.tasks[0].revision == 1
    assert state.tasks[0].accepted_result_id is None
    assert decisions(state)["claim-peer-1"] == "stale_task_revision"


def test_valid_completion_wins_over_later_revision_after_partition() -> None:
    rows = scenario()
    revision = {**rows[4],
                "record_id": reducer.deterministic_record_id("task", "group-1", "session-1", "task-1:1"),
                "created_at": "2026-09-30T12:02:00Z", "revision": 1}
    reconciled = rows + [revision]
    state = reduce(reconciled, at="2026-09-30T12:03:00Z")
    assert state.tasks[0].revision == 0
    assert state.tasks[0].ignored_revisions == (1,)
    assert state.tasks[0].accepted_result_id == "result-1"
    assert state.tasks[0].state == "completed"
    assert reduce(list(reversed(reconciled)), at="2026-09-30T12:03:00Z").state_digest == state.state_digest

    late_claim = {**rows[6], "claim_id": "claim-late", "task_revision": 1,
                  "created_at": "2026-09-30T12:03:00Z", "issued_at": "2026-09-30T12:03:00Z",
                  "record_id": reducer.deterministic_record_id(
                      "claim", "group-1", "session-1", "claim-late:0")}
    late_result = {**rows[-1], "result_id": "result-late", "claim_id": "claim-late",
                   "worker_device_id": "peer-2", "producer_device_id": "peer-2",
                   "task_revision": 1, "created_at": "2026-09-30T12:04:00Z",
                   "completed_at": "2026-09-30T12:04:00Z",
                   "record_id": reducer.deterministic_record_id(
                       "result", "group-1", "session-1", "result-late")}
    with_late = reconciled + [late_claim, late_result]
    state = reduce(with_late, at="2026-09-30T12:05:00Z")
    assert state.tasks[0].accepted_result_id == "result-1"
    assert state.tasks[0].ignored_revisions == (1,)
    assert decisions(state)["claim-late"] == "stale_task_revision"
    assert {item.result_id: item.reason for item in state.result_decisions}["result-late"] == "stale_task_revision"
    assert reduce(list(reversed(with_late)), at="2026-09-30T12:05:00Z").state_digest == state.state_digest


def test_distinct_valid_results_for_same_task_fail_closed() -> None:
    rows = scenario()
    second = {**rows[-1], "result_id": "result-2", "result_ref": f"sha256:{SHA_B}",
              "record_id": reducer.deterministic_record_id("result", "group-1", "session-1", "result-2")}
    with pytest.raises(ValueError, match="conflicting logical results"):
        reduce(rows + [second])


@pytest.mark.parametrize("revision,created_at,reason", [
    (2, "2026-09-30T12:02:00Z", "revision gap"),
    (1, NOW, "advance in time"),
])
def test_task_revision_history_must_be_contiguous_and_temporal(
    revision: int, created_at: str, reason: str,
) -> None:
    rows = scenario()
    changed = {**rows[4], "revision": revision, "created_at": created_at,
               "record_id": reducer.deterministic_record_id(
                   "task", "group-1", "session-1", f"task-1:{revision}")}
    with pytest.raises(ValueError, match=reason):
        reduce(rows + [changed], at="2026-09-30T12:03:00Z")


def test_member_removal_preserves_prior_records_but_blocks_later_writes() -> None:
    rows = scenario()
    epoch_one = {**rows[0],
                 "record_id": reducer.deterministic_record_id("session", "group-1", "session-1", "session-1:1"),
                 "created_at": "2026-09-30T12:02:00Z", "membership_epoch": 1,
                 "authorized_device_ids": ["peer-1"]}
    state = reduce(rows + [epoch_one], at="2026-09-30T12:03:00Z")
    assert state.membership_epoch == 1
    assert state.result_decisions[0].reason == "accepted"
    late = {**rows[2], "created_at": "2026-09-30T12:03:00Z"}
    with pytest.raises(ValueError, match="member|authorized"):
        reduce(rows[:2] + [late] + rows[3:] + [epoch_one], at="2026-09-30T12:04:00Z")


def test_old_claim_does_not_revive_after_member_rejoins() -> None:
    rows = scenario()[:-1]
    epoch_one = {**rows[0],
                 "record_id": reducer.deterministic_record_id("session", "group-1", "session-1", "session-1:1"),
                 "created_at": "2026-09-30T12:02:00Z", "membership_epoch": 1,
                 "authorized_device_ids": ["peer-1"]}
    epoch_two = {**rows[0],
                 "record_id": reducer.deterministic_record_id("session", "group-1", "session-1", "session-1:2"),
                 "created_at": "2026-09-30T12:03:00Z", "membership_epoch": 2}
    old_only = rows[:5] + rows[6:] + [epoch_one, epoch_two]
    state = reduce(old_only, at="2026-09-30T12:04:00Z")
    assert decisions(state)["claim-peer-2"] == "membership_interrupted"
    assert state.tasks[0].winner_claim_id is None
    new_claim = {**rows[6], "claim_id": "claim-peer-2-after-rejoin",
                 "record_id": reducer.deterministic_record_id(
                     "claim", "group-1", "session-1", "claim-peer-2-after-rejoin:0"),
                 "created_at": "2026-09-30T12:03:30Z",
                 "issued_at": "2026-09-30T12:03:30Z"}
    state = reduce(old_only + [new_claim], at="2026-09-30T12:04:00Z")
    assert state.tasks[0].winner_claim_id == "claim-peer-2-after-rejoin"


def test_claim_issue_cannot_predate_device_join() -> None:
    rows = scenario()[:-1]
    rows[0] = {**rows[0], "authorized_device_ids": ["peer-1"]}
    rows[2] = {**rows[2], "created_at": "2026-09-30T12:00:03Z",
               "valid_from": "2026-09-30T12:00:03Z"}
    rows[6] = {**rows[6], "issued_at": "2026-09-30T12:00:02Z",
               "created_at": "2026-09-30T12:00:04Z"}
    join = {**rows[0],
            "record_id": reducer.deterministic_record_id("session", "group-1", "session-1", "session-1:1"),
            "created_at": "2026-09-30T12:00:03Z", "membership_epoch": 1,
            "authorized_device_ids": ["peer-1", "peer-2"]}
    records = rows[:5] + rows[6:] + [join]
    state = reduce(records, at="2026-09-30T12:00:05Z")
    assert decisions(state)["claim-peer-2"] == "unauthorized_at_issue"
    fresh = {**rows[6], "claim_id": "claim-after-join",
             "record_id": reducer.deterministic_record_id(
                 "claim", "group-1", "session-1", "claim-after-join:0"),
             "issued_at": "2026-09-30T12:00:04Z"}
    state = reduce(records + [fresh], at="2026-09-30T12:00:05Z")
    assert state.tasks[0].winner_claim_id == "claim-after-join"


def test_backdated_claim_cannot_precede_task_or_capability() -> None:
    rows = scenario()
    rows[4] = {**rows[4], "created_at": "2026-09-30T12:00:30Z"}
    assert decisions(reduce(rows))["claim-peer-1"] == "claim_before_task"
    rows = scenario()
    rows[2] = {**rows[2], "valid_from": "2026-09-30T12:00:30Z"}
    assert decisions(reduce(rows))["claim-peer-2"] == "claim_before_capability"


def test_specialist_cannot_author_task_or_session() -> None:
    rows = scenario()
    rows[4] = {**rows[4], "producer_device_id": "peer-2"}
    with pytest.raises(ValueError, match="coordinator"):
        reduce(rows)
    rows = scenario()
    rows[0] = {**rows[0], "coordinator_device_id": "peer-2", "producer_device_id": "peer-2"}
    with pytest.raises(ValueError, match="coordinator"):
        reduce(rows)


def test_task_waits_for_all_observations_and_matching_kind() -> None:
    rows = scenario()
    rows[4] = {**rows[4], "observation_ids": ["obs-1", "obs-2"]}
    assert decisions(reduce(rows))["claim-peer-1"] == "missing_observation"
    rows = scenario()
    rows[3] = {**rows[3], "task_kind": "other"}
    assert decisions(reduce(rows))["claim-peer-1"] == "observation_task_mismatch"


@pytest.mark.parametrize("change", [
    {"model_id": "unregistered-model"},
    {"model_version": "2"},
    {"artifact_sha256": SHA_B},
])
def test_observation_requires_matching_available_producer_model_capability(change: dict) -> None:
    rows = scenario()[:-1]
    rows[3] = {**rows[3], **change}
    assert decisions(reduce(rows))["claim-peer-1"] == "untrusted_observation"


def test_historical_completion_persists_after_all_expiry() -> None:
    state = reduce(scenario(), at="2026-09-30T12:11:00Z")
    assert decisions(state)["claim-peer-1"] == "winner"
    assert state.result_decisions[0].reason == "accepted"
    assert state.tasks[0].state == "completed"


def test_completed_task_does_not_route_to_second_claim_after_first_expires() -> None:
    rows = scenario()
    rows[5] = {**rows[5], "expires_at": "2026-09-30T12:02:00Z"}
    state = reduce(rows, at="2026-09-30T12:03:00Z")
    assert state.tasks[0].winner_claim_id == "claim-peer-1"
    assert state.tasks[0].accepted_result_id == "result-1"
    assert decisions(state) == {"claim-peer-1": "winner", "claim-peer-2": "loser"}


def test_fractional_timestamp_expiry_uses_instant_not_string_order() -> None:
    rows = scenario()
    rows[5] = {**rows[5], "expires_at": "2026-09-30T12:00:00.1Z"}
    state = reduce(rows, at="2026-09-30T12:00:00.05Z")
    assert decisions(state)["claim-peer-1"] == "winner"


def test_claim_cannot_precede_observation_creation() -> None:
    rows = scenario()
    rows[3] = {**rows[3], "created_at": "2026-09-30T12:00:30Z",
               "source_time": "2026-09-30T12:00:30Z"}
    assert decisions(reduce(rows))["claim-peer-1"] == "claim_before_observation"


def test_result_can_be_persisted_after_completion_but_not_claim_future_completion() -> None:
    rows = scenario()
    rows[-1] = {**rows[-1], "created_at": "2026-09-30T12:00:30Z"}
    state = reduce(rows)
    assert state.result_decisions[0].reason == "accepted"
    rows = scenario()
    rows[-1] = {**rows[-1], "completed_at": "2026-09-30T12:00:30Z"}
    state = reduce(rows)
    assert state.result_decisions[0].reason == "result_after_record"
    assert state.tasks[0].accepted_result_id is None


def test_delayed_result_write_after_expiry_keeps_valid_historical_completion() -> None:
    rows = scenario()
    rows[-1] = {**rows[-1], "created_at": "2026-09-30T12:11:00Z"}
    state = reduce(rows, at="2026-09-30T12:12:00Z")
    assert state.result_decisions[0].reason == "accepted"
    assert state.tasks[0].accepted_result_id == "result-1"


def test_claim_can_be_persisted_after_issue_but_not_claim_future_issue() -> None:
    rows = scenario()[:-1]
    rows[5] = {**rows[5], "created_at": "2026-09-30T12:00:30Z"}
    assert decisions(reduce(rows))["claim-peer-1"] == "winner"
    rows = scenario()[:-1]
    rows[5] = {**rows[5], "issued_at": "2026-09-30T12:00:30Z"}
    assert decisions(reduce(rows))["claim-peer-1"] == "claim_after_record"


def test_claim_write_must_precede_worker_completion_even_with_delayed_result_write() -> None:
    rows = scenario()
    rows[5] = {**rows[5], "issued_at": "2026-09-30T12:00:02Z",
               "created_at": "2026-09-30T12:00:04Z"}
    rows[-1] = {**rows[-1], "completed_at": "2026-09-30T12:00:03Z",
                "created_at": "2026-09-30T12:00:05Z"}
    state = reduce(rows)
    assert state.result_decisions[0].reason == "claim_not_recorded_at_completion"
    assert state.tasks[0].accepted_result_id is None
    rows[5] = {**rows[5], "created_at": "2026-09-30T12:00:03Z"}
    rows[-1] = {**rows[-1], "completed_at": "2026-09-30T12:00:04Z"}
    state = reduce(rows)
    assert state.result_decisions[0].reason == "accepted"


def test_capability_and_claim_status_events_apply_at_their_event_time() -> None:
    rows = scenario()
    capability_unavailable = {**rows[1], "revision": 1, "status": "unavailable",
                              "created_at": "2026-09-30T12:00:30Z",
                              "record_id": reducer.deterministic_record_id(
                                  "capability", "group-1", "session-1", "cap-peer-1:1")}
    withdrawn = {**rows[6], "claim_revision": 1, "claim_status": "withdrawn",
                 "created_at": "2026-09-30T12:00:30Z",
                 "record_id": reducer.deterministic_record_id(
                     "claim", "group-1", "session-1", "claim-peer-2:1")}
    before = reduce(rows[:-1] + [capability_unavailable, withdrawn],
                    at="2026-09-30T12:00:15Z")
    assert decisions(before) == {"claim-peer-1": "winner", "claim-peer-2": "loser"}
    after = reduce(rows[:-1] + [capability_unavailable, withdrawn])
    assert decisions(after)["claim-peer-1"] == "unavailable_capability"
    assert decisions(after)["claim-peer-2"] == "withdrawn"
    # A result completed before both status changes keeps its historical winner.
    completed = reduce(rows + [capability_unavailable, withdrawn])
    assert completed.result_decisions[0].reason == "accepted"
    assert completed.tasks[0].winner_claim_id == "claim-peer-1"
    assert reduce(list(reversed(rows + [capability_unavailable, withdrawn]))).state_digest == completed.state_digest


def test_result_cannot_cite_withdrawn_claim_revision_at_completion() -> None:
    rows = scenario()
    withdrawn = {**rows[5], "claim_revision": 1, "claim_status": "withdrawn",
                 "created_at": "2026-09-30T12:00:30Z",
                 "record_id": reducer.deterministic_record_id(
                     "claim", "group-1", "session-1", "claim-peer-1:1")}
    result = {**rows[-1], "completed_at": "2026-09-30T12:01:00Z",
              "created_at": "2026-09-30T12:01:00Z"}
    state = reduce(rows[:-1] + [withdrawn, result])
    assert state.result_decisions[0].reason == "stale_claim_revision"
    assert state.tasks[0].accepted_result_id is None


@pytest.mark.parametrize("kind,change,reason", [
    ("capability", {"revision": 2}, "revision gap"),
    ("capability", {"revision": 1, "model_id": "other-model"}, "immutable"),
    ("claim", {"claim_revision": 2}, "revision gap"),
    ("claim", {"claim_revision": 1, "claimant_device_id": "peer-2",
                "producer_device_id": "peer-2"}, "immutable"),
])
def test_status_event_history_rejects_gaps_and_identity_changes(
    kind: str, change: dict, reason: str,
) -> None:
    rows = scenario()
    source = rows[1] if kind == "capability" else rows[5]
    version_field = "revision" if kind == "capability" else "claim_revision"
    version = change[version_field]
    source_id = source["capability_id"] if kind == "capability" else source["claim_id"]
    altered = {**source, **change, "created_at": "2026-09-30T12:00:30Z",
               "status" if kind == "capability" else "claim_status":
                   "unavailable" if kind == "capability" else "withdrawn",
               "record_id": reducer.deterministic_record_id(
                   kind, "group-1", "session-1", f"{source_id}:{version}")}
    with pytest.raises(ValueError, match=reason):
        reduce(rows + [altered])
