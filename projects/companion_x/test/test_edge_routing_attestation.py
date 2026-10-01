"""License-free contract tests; signed fixtures do not assert an SDK run."""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

ROOT = Path(__file__).parents[1] / "experiments/edge_models"
SPEC = importlib.util.spec_from_file_location("edge_routing_attestation", ROOT / "edge-routing-sdk-001/attestation.py")
assert SPEC is not None and SPEC.loader is not None
contract = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = contract
SPEC.loader.exec_module(contract)
RECORD_SPEC = importlib.util.spec_from_file_location("edge_mesh_records_for_attestation", ROOT / "edge-mesh-coordinator-001/records.py")
assert RECORD_SPEC is not None and RECORD_SPEC.loader is not None
records = importlib.util.module_from_spec(RECORD_SPEC)
sys.modules[RECORD_SPEC.name] = records
RECORD_SPEC.loader.exec_module(records)
H = "a" * 64
J = "b" * 64
T0, T1, T2, T3 = "2026-09-30T12:00:00Z", "2026-09-30T12:01:00Z", "2026-09-30T12:02:00Z", "2026-09-30T12:03:00Z"
T4, T5 = "2026-09-30T12:04:00Z", "2026-09-30T12:10:00Z"
T_PRE = "2026-09-30T12:01:30Z"
LOCAL_INFERENCE = {
    "schema_version": 1, "source_event_sha256": J, "model_sha256": H,
    "probability": 0.8, "decision": 1, "inference_ms": 1.0,
}


def row(kind: str, source: str, peer: str = "peer-1", *, created: str = T0, **fields: object) -> dict:
    return {
        "schema_version": 1, "record_type": kind,
        "record_id": records.deterministic_record_id(kind, "group-1", "session-1", source),
        "group_id": "group-1", "session_id": "session-1", "producer_device_id": peer,
        "created_at": created, "causation_ids": [], **fields,
    }


def fixture_rows() -> list[dict]:
    session = row("session", "session-1:0", session_kind="inspection", opened_at=T0,
                  closed_at=None, policy_version="policy-1", membership_epoch=0,
                  status="open", authorized_device_ids=["peer-1", "peer-2"],
                  coordinator_device_id="peer-1")
    capabilities = [row("capability", f"cap-{peer}:0", peer, capability_id=f"cap-{peer}",
                        revision=0, role="audio", model_id="tiny-audio", model_version="1",
                        artifact_sha256=H, input_modalities=["audio"], output_schema_version=1,
                        runtime_id="arm64-linux", valid_from=T0, expires_at=T5,
                        status="available", authorization_scope="session", policy_version="policy-1")
                    for peer in ("peer-1", "peer-2")]
    observation = row("observation", "obs-1", created=T1, observation_id="obs-1",
                      source_event_id="event-1", source_time=T0, task_kind="inspect",
                      model_id="tiny-audio", model_version="1", artifact_sha256=H,
                      output_schema_version=1, bounded_output=[{"name": "signal", "value": True}],
                      confidence_or_score=0.8, input_ref=f"sha256:{J}",
                      retention_class="device-local")
    task = row("task", "task-1:0", created=T1, task_id="task-1", task_kind="inspect",
               state="proposed", expires_at=T5, required_capabilities=["cap-peer-1", "cap-peer-2"],
               observation_ids=["obs-1"], policy_version="policy-1", policy_sha256=H,
               scenario_sha256=J, revision=0, terminal_reason=None,
               authorized_device_ids=["peer-1", "peer-2"])
    claim = row("claim", "claim-1:0", "peer-2", created=T3, claim_id="claim-1",
                claim_revision=0, task_id="task-1", claimant_device_id="peer-2",
                capability_id="cap-peer-2", task_revision=0, issued_at=T3,
                expires_at=T5, claim_status="proposed", authorization_scope="session",
                policy_version="policy-1")
    result = row("result", "result-1", "peer-2", created=T4, result_id="result-1",
                 task_id="task-1", claim_id="claim-1", claim_revision=0,
                 worker_device_id="peer-2", task_revision=0, outcome="completed",
                 result_ref=f"sha256:{contract.sha256(contract.canonical_bytes(LOCAL_INFERENCE))}",
                 completed_at=T4, model_id="tiny-audio",
                 artifact_sha256=H, input_ref=f"sha256:{J}", policy_version="policy-1",
                 policy_sha256=H, scenario_sha256=J)
    return [session, *capabilities, observation, task, claim, result]


def digest(row: dict) -> str:
    return contract.sha256(records.canonical_bytes(row))


def valid_attestation() -> dict:
    rows = fixture_rows()
    session, cap1, cap2, observation, task, claim, result = rows
    pins = {
        "run_id": "run-1", "scenario_sha256": J, "image_sha256": H,
        "source_sha256": J, "source_event_sha256": J, "model_sha256": H,
        "cohort_sha256": J, "sdk_distribution_sha256": J,
        "policy_sha256": H,
        "records_module_sha256": contract.sha256((ROOT / "edge-mesh-coordinator-001/records.py").read_bytes()),
        "reducer_module_sha256": contract.sha256((ROOT / "edge-mesh-coordinator-001/reducer.py").read_bytes()),
    }
    candidates = [
        {"candidate_id": peer, "peer_id": peer, "capability_record_id": cap["record_id"],
         "capability_sha256": digest(cap), "required_tag": "inspect", "capability_id": cap["capability_id"]}
        for peer, cap in (("peer-1", cap1), ("peer-2", cap2))
    ]
    record_hashes = {r["record_id"]: digest(r) for r in rows}
    readbacks = [
        {"peer_id": peer, "sdk_distribution_sha256": J,
         "local_write_record_ids": ([cap2["record_id"], claim["record_id"], result["record_id"]]
                                    if peer == "peer-2" else
                                    [session["record_id"], cap1["record_id"], observation["record_id"], task["record_id"]]),
         "decision_query": ({"queried_at": T_PRE, "record_sha256_by_id": {
             record_id: record_hashes[record_id] for record_id in (
                 session["record_id"], cap1["record_id"], cap2["record_id"],
                 observation["record_id"], task["record_id"])
         }} if peer == "peer-1" else None),
         "reopen": {"queried_at": T4, "record_sha256_by_id": record_hashes},
         "after_rejoin": {"queried_at": T5, "record_sha256_by_id": record_hashes},
         "disconnect_observed": True, "rejoin_observed": True}
        for peer in ("peer-1", "peer-2")
    ]
    return {
        "schema_version": 2, "run_status": "succeeded", "failure_reason": None,
        "pins": pins, "group_id": "group-1", "session_id": "session-1",
        "trusted_coordinator_device_id": "peer-1", "policy_version": "policy-1",
        "decision": {"decision_at": T2, "task_record_id": task["record_id"],
                     "task_sha256": digest(task), "observation_record_id": observation["record_id"],
                     "observation_sha256": digest(observation),
                     "session_record_id": session["record_id"], "session_sha256": digest(session),
                     "required_tags": ["inspect"], "candidates": candidates,
                     "eligible_candidate_ids": ["peer-1", "peer-2"]},
        "selected": {"candidate_id": "peer-2", "peer_id": "peer-2",
                     "claim_record_id": claim["record_id"], "claim_sha256": digest(claim),
                     "result_record_id": result["record_id"], "result_sha256": digest(result),
                     "selected_at": T3},
        "records": rows, "peer_readbacks": readbacks,
        "reducer_as_of": T4, "reducer_state_sha256": contract.replay_digest(
            rows, group_id="group-1", session_id="session-1", as_of=T4,
            coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H),
        "accepted_record_set_sha256": contract.replay_record_set_digest(
            rows, group_id="group-1", session_id="session-1", as_of=T4,
            coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H),
    }


def receipt(attestation: dict, key: Ed25519PrivateKey, *, verdict: str = "accepted",
            key_id: str = "reviewer-1", reviewer_id: str = "reviewer-1") -> dict:
    payload = {
        "schema_version": 2, "attestation_sha256": contract.attestation_digest(attestation),
        "execution_sha256": contract.execution_digest(attestation),
        "outcome_sha256": contract.outcome_digest(attestation),
        "reviewer_id": reviewer_id, "key_id": key_id,
        "verdict": verdict, "reviewed_at": T5,
    }
    return {**payload, "signature_base64": base64.b64encode(key.sign(contract.receipt_signing_bytes(payload))).decode("ascii")}


def trusted_keys(key: Ed25519PrivateKey) -> dict[str, tuple[str, bytes]]:
    return {"reviewer-1": ("reviewer-1", key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw))}


EXPECTED_CAPABILITY_TAGS = {"cap-peer-1": "inspect", "cap-peer-2": "inspect"}


def verify(attestation: dict, key: Ed25519PrivateKey, review: dict | None = None) -> object:
    return contract.verify_attestation(attestation, review or receipt(attestation, key),
                                       expected_pins=attestation["pins"],
                                       trusted_reviewer_keys=trusted_keys(key),
                                       expected_capability_tags=EXPECTED_CAPABILITY_TAGS)


def add_signed_history_row(value: dict, new_row: dict) -> None:
    """Keep the synthetic SDK readbacks and reducer digests consistent with a new row."""
    value["records"].append(new_row)
    row_hash = digest(new_row)
    for peer in value["peer_readbacks"]:
        if peer["peer_id"] == new_row["producer_device_id"]:
            peer["local_write_record_ids"].append(new_row["record_id"])
        for stage in ("reopen", "after_rejoin"):
            peer[stage]["record_sha256_by_id"][new_row["record_id"]] = row_hash
    value["reducer_state_sha256"] = contract.replay_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H,
    )
    value["accepted_record_set_sha256"] = contract.replay_record_set_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H,
    )


def test_valid_fixture_replays_and_verifies_external_reviewer_key() -> None:
    value = valid_attestation()
    key = Ed25519PrivateKey.generate()
    verified = verify(value, key)
    assert verified.attestation_sha256 == contract.attestation_digest(value)
    assert verified.selected_peer_id == "peer-2"
    assert verified.accepted_result_id == "result-1"


@pytest.mark.parametrize("record_index", [0, 1, 2, 3, 4])
def test_coordinator_decision_query_requires_each_cited_record(record_index: int) -> None:
    value = valid_attestation()
    record_id = value["records"][record_index]["record_id"]
    del value["peer_readbacks"][0]["decision_query"]["record_sha256_by_id"][record_id]
    with pytest.raises(ValueError, match="decision query"):
        verify(value, Ed25519PrivateKey.generate())


def test_coordinator_decision_query_requires_matching_record_hash() -> None:
    value = valid_attestation()
    record_id = value["decision"]["task_record_id"]
    value["peer_readbacks"][0]["decision_query"]["record_sha256_by_id"][record_id] = J
    with pytest.raises(ValueError, match="decision query"):
        verify(value, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("query_at", [T0, T2, T3])
def test_coordinator_decision_query_must_follow_writes_and_precede_decision(query_at: str) -> None:
    value = valid_attestation()
    value["peer_readbacks"][0]["decision_query"]["queried_at"] = query_at
    with pytest.raises(ValueError, match="decision query"):
        verify(value, Ed25519PrivateKey.generate())


def test_decision_query_cannot_include_future_or_absent_final_record() -> None:
    value = valid_attestation()
    query = value["peer_readbacks"][0]["decision_query"]["record_sha256_by_id"]
    query[value["selected"]["claim_record_id"]] = value["selected"]["claim_sha256"]
    with pytest.raises(ValueError, match="decision query"):
        verify(value, Ed25519PrivateKey.generate())
    del query[value["selected"]["claim_record_id"]]
    query["absent-record"] = H
    with pytest.raises(ValueError, match="decision query"):
        verify(value, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("change", ["missing", "wrong_peer"])
def test_only_coordinator_can_provide_decision_query(change: str) -> None:
    value = valid_attestation()
    if change == "missing":
        value["peer_readbacks"][0]["decision_query"] = None
    else:
        value["peer_readbacks"][1]["decision_query"] = value["peer_readbacks"][0]["decision_query"]
        value["peer_readbacks"][0]["decision_query"] = None
    with pytest.raises(ValueError, match="decision query"):
        verify(value, Ed25519PrivateKey.generate())


def test_v1_attestation_or_receipt_is_not_accepted_by_v2_verifier() -> None:
    value = valid_attestation()
    key = Ed25519PrivateKey.generate()
    v1_attestation = copy.deepcopy(value)
    v1_attestation["schema_version"] = 1
    with pytest.raises(ValueError):
        contract.verify_attestation(v1_attestation, receipt(value, key),
                                    expected_pins=value["pins"],
                                    trusted_reviewer_keys=trusted_keys(key),
                                    expected_capability_tags=EXPECTED_CAPABILITY_TAGS)
    v1_receipt = receipt(value, key)
    v1_receipt["schema_version"] = 1
    with pytest.raises(ValueError):
        verify(value, key, v1_receipt)
    v1_domain_receipt = receipt(value, key)
    payload = {k: v for k, v in v1_domain_receipt.items() if k != "signature_base64"}
    v1_domain_receipt["signature_base64"] = base64.b64encode(
        key.sign(b"edge-routing-review-receipt-v1\x00" + contract.canonical_bytes(payload))
    ).decode("ascii")
    with pytest.raises(ValueError, match="signature"):
        verify(value, key, v1_domain_receipt)


@pytest.mark.parametrize("path,value", [
    (("selected", "peer_id"), "peer-1"),
    (("selected", "claim_record_id"), "claim-other"),
    (("selected", "result_record_id"), "result-other"),
    (("selected", "claim_sha256"), J),
    (("selected", "result_sha256"), J),
    (("selected", "candidate_id"), "peer-1"),
    (("decision", "eligible_candidate_ids"), ["peer-1"]),
    (("decision", "candidates", 1, "capability_id"), "cap-peer-1"),
    (("peer_readbacks", 1, "after_rejoin", "record_sha256_by_id"), {}),
    (("peer_readbacks",), []),
    (("peer_readbacks", 1, "local_write_record_ids"), [fixture_rows()[2]["record_id"]]),
    (("peer_readbacks", 1, "rejoin_observed"), False),
    (("records", 5, "claimant_device_id"), "peer-1"),
    (("reducer_state_sha256",), J),
    (("accepted_record_set_sha256",), J),
])
def test_wrong_route_or_evidence_fails_even_with_fresh_signature(path: tuple, value: object) -> None:
    attestation = valid_attestation()
    current = attestation
    for part in path[:-1]:
        current = current[part]
    current[path[-1]] = value
    with pytest.raises((ValueError, TypeError)):
        verify(attestation, Ed25519PrivateKey.generate())


def test_changed_attestation_rejects_prior_receipt_and_pins() -> None:
    attestation = valid_attestation()
    key = Ed25519PrivateKey.generate()
    signed = receipt(attestation, key)
    altered = copy.deepcopy(attestation)
    altered["pins"]["image_sha256"] = J
    with pytest.raises(ValueError):
        contract.verify_attestation(altered, signed, expected_pins=attestation["pins"],
                                    trusted_reviewer_keys=trusted_keys(key),
                                    expected_capability_tags=EXPECTED_CAPABILITY_TAGS)


def test_signed_matching_external_pin_still_rejects_wrong_executed_reducer_bytes() -> None:
    attestation = valid_attestation()
    attestation["pins"]["reducer_module_sha256"] = H
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="executed records or reducer"):
        verify(attestation, key)


def test_rejected_failed_and_untrusted_signer_never_produce_accepted_attestation() -> None:
    attestation = valid_attestation()
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError):
        verify(attestation, key, receipt(attestation, key, verdict="rejected"))
    attestation["run_status"] = "failed"
    attestation["failure_reason"] = "sdk_query_failed"
    with pytest.raises(ValueError):
        verify(attestation, key)
    attestation = valid_attestation()
    outsider = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError):
        contract.verify_attestation(attestation, receipt(attestation, outsider),
                                    expected_pins=attestation["pins"],
                                    trusted_reviewer_keys=trusted_keys(key),
                                    expected_capability_tags=EXPECTED_CAPABILITY_TAGS)
    with pytest.raises(ValueError):
        contract.verify_attestation(attestation, receipt(attestation, key, key_id="untrusted"),
                                    expected_pins=attestation["pins"],
                                    trusted_reviewer_keys=trusted_keys(key),
                                    expected_capability_tags=EXPECTED_CAPABILITY_TAGS)


def test_early_failed_run_has_distinct_parseable_status_but_no_accepted_label() -> None:
    failed = valid_attestation()
    failed.update(run_status="failed", failure_reason="sdk_start_failed", decision=None,
                  selected=None, records=[], peer_readbacks=[], reducer_as_of=None,
                  reducer_state_sha256=None, accepted_record_set_sha256=None)
    parsed = contract.RoutingAttestation.model_validate(failed)
    assert parsed.run_status == "failed"
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="failed runs"):
        verify(failed, key)


def test_json_boundary_rejects_duplicate_keys_and_nonfinite_values() -> None:
    value = valid_attestation()
    encoded = json.dumps(value, separators=(",", ":")).encode()
    assert contract.parse_attestation_json_bytes(encoded).pins.run_id == "run-1"
    with pytest.raises(ValueError, match="duplicate"):
        contract.parse_attestation_json_bytes(encoded.replace(b'"schema_version":1,',
                                                               b'"schema_version":1,"schema_version":1,', 1))
    with pytest.raises(ValueError):
        contract.parse_attestation_json_bytes(encoded.replace(b'"schema_version":1,',
                                                               b'"schema_version":NaN,', 1))
    with pytest.raises(ValueError):
        contract.parse_attestation_json_bytes(b"{}" * 600_000)


def test_receipt_cannot_supply_its_own_trust_key() -> None:
    attestation = valid_attestation()
    key = Ed25519PrivateKey.generate()
    forged = {**receipt(attestation, key), "reviewer_public_key": trusted_keys(key)["reviewer-1"][1].hex()}
    with pytest.raises(ValueError):
        verify(attestation, key, forged)


def test_contract_values_are_frozen_and_unknown_fields_fail() -> None:
    value = valid_attestation()
    parsed = contract.RoutingAttestation.model_validate(value)
    with pytest.raises(ValidationError):
        parsed.pins.run_id = "replaced"
    with pytest.raises(ValidationError):
        parsed.decision.candidates[0].peer_id = "replaced"
    with pytest.raises(ValidationError):
        contract.RoutingAttestation.model_validate({**value, "reviewer_public_key": H})


def test_unavailable_capability_is_unsafe_even_when_every_digest_is_recomputed() -> None:
    value = valid_attestation()
    cap = value["records"][2]
    cap["status"] = "unavailable"
    cap_hash = digest(cap)
    value["decision"]["candidates"][1]["capability_sha256"] = cap_hash
    for peer in value["peer_readbacks"]:
        for stage in ("reopen", "after_rejoin"):
            peer[stage]["record_sha256_by_id"][cap["record_id"]] = cap_hash
    value["reducer_state_sha256"] = contract.replay_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H)
    value["accepted_record_set_sha256"] = contract.replay_record_set_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H)
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError, match="unsafe"):
        verify(value, key)


def test_unselected_wrong_policy_capability_is_not_an_eligible_route() -> None:
    value = valid_attestation()
    task_capability = value["records"][1]
    observation_capability = copy.deepcopy(task_capability)
    observation_capability["record_id"] = records.deterministic_record_id(
        "capability", "group-1", "session-1", "cap-observation:0"
    )
    observation_capability["capability_id"] = "cap-observation"
    value["records"].append(observation_capability)
    value["peer_readbacks"][0]["local_write_record_ids"].append(observation_capability["record_id"])
    task_capability["policy_version"] = "wrong-policy"
    value["decision"]["candidates"][0]["capability_sha256"] = digest(task_capability)
    for peer in value["peer_readbacks"]:
        for stage in ("reopen", "after_rejoin"):
            peer[stage]["record_sha256_by_id"][task_capability["record_id"]] = digest(task_capability)
            peer[stage]["record_sha256_by_id"][observation_capability["record_id"]] = digest(
                observation_capability
            )
    value["reducer_state_sha256"] = contract.replay_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H,
    )
    value["accepted_record_set_sha256"] = contract.replay_record_set_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H,
    )
    with pytest.raises(ValueError, match="eligible"):
        verify(value, Ed25519PrivateKey.generate())


def test_sdk_query_cannot_contain_a_record_created_after_the_query() -> None:
    value = valid_attestation()
    future_capability = copy.deepcopy(value["records"][1])
    future_capability["record_id"] = records.deterministic_record_id(
        "capability", "group-1", "session-1", "future-capability:0"
    )
    future_capability["capability_id"] = "future-capability"
    future_capability["created_at"] = "2026-09-30T12:11:00Z"
    value["records"].append(future_capability)
    for peer in value["peer_readbacks"]:
        for stage in ("reopen", "after_rejoin"):
            peer[stage]["record_sha256_by_id"][future_capability["record_id"]] = digest(
                future_capability
            )
    value["reducer_state_sha256"] = contract.replay_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H,
    )
    value["accepted_record_set_sha256"] = contract.replay_record_set_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H,
    )
    with pytest.raises(ValueError, match="predates a returned SDK record"):
        verify(value, Ed25519PrivateKey.generate())


def test_reducer_rejects_unavailable_task_capability_even_when_snapshot_omits_it() -> None:
    value = valid_attestation()
    cap = value["records"][1]
    cap["status"] = "unavailable"
    cap_hash = digest(cap)
    value["decision"]["candidates"][0]["capability_sha256"] = cap_hash
    value["decision"]["eligible_candidate_ids"] = ["peer-2"]
    value["peer_readbacks"][0]["decision_query"]["record_sha256_by_id"][cap["record_id"]] = cap_hash
    for peer in value["peer_readbacks"]:
        for stage in ("reopen", "after_rejoin"):
            peer[stage]["record_sha256_by_id"][cap["record_id"]] = cap_hash
    value["reducer_state_sha256"] = contract.replay_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H)
    value["accepted_record_set_sha256"] = contract.replay_record_set_digest(
        value["records"], group_id="group-1", session_id="session-1", as_of=T4,
        coordinator_id="peer-1", policy_version="policy-1", policy_sha256=H)
    # The snapshot is internally consistent, but the reducer still rejects the task.
    with pytest.raises(ValueError, match="reducer"):
        verify(value, Ed25519PrivateKey.generate())


def test_eligible_candidate_cannot_be_omitted_from_declared_set() -> None:
    value = valid_attestation()
    value["decision"]["eligible_candidate_ids"] = ["peer-2"]
    with pytest.raises(ValueError, match="eligible"):
        verify(value, Ed25519PrivateKey.generate())


def test_unexpected_candidate_tag_fails_even_if_selected_candidate_has_required_tag() -> None:
    value = valid_attestation()
    value["decision"]["candidates"][0]["required_tag"] = "unauthorized-skill"
    with pytest.raises(ValueError, match="tag"):
        verify(value, Ed25519PrivateKey.generate())


def test_single_selected_capability_cannot_claim_to_cover_two_different_task_tags() -> None:
    value = valid_attestation()
    value["decision"]["required_tags"] = ["inspect", "vision"]
    value["decision"]["candidates"][1]["required_tag"] = "vision"
    with pytest.raises(ValueError, match="tag"):
        verify(value, Ed25519PrivateKey.generate())


def test_reopen_query_cannot_predate_selected_peer_claim_and_result_writes() -> None:
    value = valid_attestation()
    value["peer_readbacks"][1]["reopen"]["queried_at"] = T2
    with pytest.raises(ValueError, match="reopen"):
        verify(value, Ed25519PrivateKey.generate())


def test_reopen_query_cannot_predate_coordinator_local_observation_and_task_writes() -> None:
    value = valid_attestation()
    value["peer_readbacks"][0]["reopen"]["queried_at"] = T0
    with pytest.raises(ValueError, match="reopen"):
        verify(value, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("record_index", [0, 3, 4])
def test_coordinator_must_locally_write_and_reopen_source_records(record_index: int) -> None:
    value = valid_attestation()
    record_id = value["records"][record_index]["record_id"]
    value["peer_readbacks"][0]["local_write_record_ids"].remove(record_id)
    with pytest.raises(ValueError, match="coordinator"):
        verify(value, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("record_index", [0, 3, 4])
def test_coordinator_source_record_must_survive_reopen_query(record_index: int) -> None:
    value = valid_attestation()
    record_id = value["records"][record_index]["record_id"]
    del value["peer_readbacks"][0]["reopen"]["record_sha256_by_id"][record_id]
    with pytest.raises(ValueError, match="reopen"):
        verify(value, Ed25519PrivateKey.generate())


def test_resigned_consistent_bogus_skill_tag_fails_external_capability_policy() -> None:
    value = valid_attestation()
    value["decision"]["required_tags"] = ["made-up-skill"]
    for candidate in value["decision"]["candidates"]:
        candidate["required_tag"] = "made-up-skill"
    with pytest.raises(ValueError, match="external capability"):
        verify(value, Ed25519PrivateKey.generate())


def test_external_capability_policy_must_match_all_task_capability_ids() -> None:
    value = valid_attestation()
    key = Ed25519PrivateKey.generate()
    for policy in ({"cap-peer-1": "inspect"},
                   {**EXPECTED_CAPABILITY_TAGS, "cap-other": "inspect"},
                   {"cap-peer-1": "inspect", "cap-peer-2": "vision"}):
        with pytest.raises(ValueError, match="external capability"):
            contract.verify_attestation(value, receipt(value, key), expected_pins=value["pins"],
                                        trusted_reviewer_keys=trusted_keys(key),
                                        expected_capability_tags=policy)


def test_caller_must_supply_external_capability_policy() -> None:
    value = valid_attestation()
    key = Ed25519PrivateKey.generate()
    with pytest.raises(TypeError, match="expected_capability_tags"):
        contract.verify_attestation(value, receipt(value, key), expected_pins=value["pins"],
                                    trusted_reviewer_keys=trusted_keys(key))


def test_unselected_capability_must_remain_valid_through_selection() -> None:
    value = valid_attestation()
    cap = value["records"][1]
    cap["expires_at"] = T3
    cap_hash = digest(cap)
    value["decision"]["candidates"][0]["capability_sha256"] = cap_hash
    for peer in value["peer_readbacks"]:
        for stage in ("reopen", "after_rejoin"):
            peer[stage]["record_sha256_by_id"][cap["record_id"]] = cap_hash
    with pytest.raises(ValueError, match="selection"):
        verify(value, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("changed_at", ["2026-09-30T12:01:30Z", "2026-09-30T12:02:30Z"])
def test_signed_cited_capability_revision_must_still_be_effective(changed_at: str) -> None:
    value = valid_attestation()
    stale = value["records"][1]
    unavailable = copy.deepcopy(stale)
    unavailable.update(
        record_id=records.deterministic_record_id(
            "capability", "group-1", "session-1", "cap-peer-1:1"
        ),
        revision=1,
        created_at=changed_at,
        status="unavailable",
    )
    add_signed_history_row(value, unavailable)
    # The selected peer-2 route still has an accepted reducer result. A signed
    # snapshot must not count peer-1's superseded available revision.
    assert value["selected"]["peer_id"] == "peer-2"
    with pytest.raises(ValueError, match="(eligible|effective|selection)"):
        verify(value, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("changed_at", ["2026-09-30T12:01:30Z", "2026-09-30T12:02:30Z"])
def test_signed_cited_session_epoch_cannot_hide_removed_peer(changed_at: str) -> None:
    value = valid_attestation()
    old_session = value["records"][0]
    new_session = copy.deepcopy(old_session)
    new_session.update(
        record_id=records.deterministic_record_id(
            "session", "group-1", "session-1", "session-1:1"
        ),
        membership_epoch=1,
        created_at=changed_at,
        authorized_device_ids=["peer-2"],
    )
    add_signed_history_row(value, new_session)
    assert value["selected"]["peer_id"] == "peer-2"
    with pytest.raises(ValueError, match="(eligible|effective|selection)"):
        verify(value, Ed25519PrivateKey.generate())


@pytest.mark.parametrize("peer_index,cap_index", [(0, 1), (1, 2)])
def test_each_advertised_capability_requires_owner_local_write(peer_index: int, cap_index: int) -> None:
    value = valid_attestation()
    cap_id = value["records"][cap_index]["record_id"]
    value["peer_readbacks"][peer_index]["local_write_record_ids"].remove(cap_id)
    with pytest.raises(ValueError, match="capability"):
        verify(value, Ed25519PrivateKey.generate())


def test_trusted_key_cannot_sign_an_arbitrary_reviewer_identity() -> None:
    value = valid_attestation()
    key = Ed25519PrivateKey.generate()
    forged_identity = receipt(value, key, reviewer_id="another-reviewer")
    with pytest.raises(ValueError, match="reviewer identity"):
        verify(value, key, forged_identity)


@given(st.sampled_from(["scenario_sha256", "image_sha256", "source_sha256", "source_event_sha256",
                        "model_sha256", "cohort_sha256",
                        "sdk_distribution_sha256", "policy_sha256", "records_module_sha256",
                        "reducer_module_sha256"]))
def test_each_pin_is_bound_to_external_expected_pin(name: str) -> None:
    attestation = valid_attestation()
    expected = dict(attestation["pins"])
    attestation["pins"][name] = J if expected[name] == H else H
    key = Ed25519PrivateKey.generate()
    with pytest.raises(ValueError):
        contract.verify_attestation(attestation, receipt(attestation, key),
                                    expected_pins=expected, trusted_reviewer_keys=trusted_keys(key),
                                    expected_capability_tags=EXPECTED_CAPABILITY_TAGS)
