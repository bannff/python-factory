"""Independent replay and trusted reviewer verification of an N=2 route."""

from __future__ import annotations

import base64
import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_SPEC = importlib.util.spec_from_file_location(
    "edge_routing_attestation_schema", Path(__file__).with_name("attestation_schema.py")
)
assert _SPEC is not None and _SPEC.loader is not None
_schema = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault(_SPEC.name, _schema)
_SPEC.loader.exec_module(_schema)
_records = _schema._records
_REDUCER_SPEC = importlib.util.spec_from_file_location(
    "edge_mesh_reducer_for_routing_sdk", _schema.MESH / "reducer.py"
)
assert _REDUCER_SPEC is not None and _REDUCER_SPEC.loader is not None
_reducer = importlib.util.module_from_spec(_REDUCER_SPEC)
sys.modules.setdefault(_REDUCER_SPEC.name, _reducer)
_REDUCER_SPEC.loader.exec_module(_reducer)
RunPins = _schema.RunPins
RoutingAttestation = _schema.RoutingAttestation
ReviewerReceipt = _schema.ReviewerReceipt
VerifiedRoutingAttestation = _schema.VerifiedRoutingAttestation
canonical_bytes = _schema.canonical_bytes
sha256 = _schema.sha256
parse_attestation_json_bytes = _schema.parse_attestation_json_bytes


def replay_digest(rows: list[dict] | tuple[Any, ...], *, group_id: str, session_id: str,
                  as_of: str, coordinator_id: str, policy_version: str, policy_sha256: str) -> str:
    return _reducer.reduce_records(rows, group_id=group_id, session_id=session_id, as_of=as_of,
                                   trusted_coordinator_device_id=coordinator_id,
                                   expected_policy_version=policy_version,
                                   expected_policy_sha256=policy_sha256).state_digest


def replay_record_set_digest(rows: list[dict] | tuple[Any, ...], *, group_id: str,
                             session_id: str, as_of: str, coordinator_id: str,
                             policy_version: str, policy_sha256: str) -> str:
    return _reducer.reduce_records(rows, group_id=group_id, session_id=session_id, as_of=as_of,
                                   trusted_coordinator_device_id=coordinator_id,
                                   expected_policy_version=policy_version,
                                   expected_policy_sha256=policy_sha256).accepted_record_set_digest


def attestation_digest(value: RoutingAttestation | dict[str, Any]) -> str:
    item = RoutingAttestation.model_validate(value)
    return sha256(canonical_bytes(item))


def execution_digest(value: RoutingAttestation | dict[str, Any]) -> str:
    item = RoutingAttestation.model_validate(value)
    return sha256(canonical_bytes({"pins": item.pins.model_dump(mode="json"),
                                   "decision": item.decision.model_dump(mode="json") if item.decision else None,
                                   "selected": item.selected.model_dump(mode="json") if item.selected else None}))


def outcome_digest(value: RoutingAttestation | dict[str, Any]) -> str:
    item = RoutingAttestation.model_validate(value)
    return sha256(canonical_bytes({"run_status": item.run_status,
                                   "selected": item.selected.model_dump(mode="json") if item.selected else None,
                                   "peer_readbacks": [p.model_dump(mode="json") for p in item.peer_readbacks],
                                   "reducer_state_sha256": item.reducer_state_sha256}))


def receipt_signing_bytes(value: ReviewerReceipt | dict[str, Any]) -> bytes:
    data = value.model_dump(mode="json") if isinstance(value, ReviewerReceipt) else value
    receipt = ReviewerReceipt.model_validate({**data, "signature_base64": base64.b64encode(bytes(64)).decode("ascii")})
    payload = receipt.model_dump(mode="json", exclude={"signature_base64"})
    return b"edge-routing-review-receipt-v2\x00" + canonical_bytes(payload)


def _record_map(item: RoutingAttestation) -> tuple[dict[str, Any], dict[str, str]]:
    rows = {r.record_id: r for r in item.records}
    if len(rows) != len(item.records):
        raise ValueError("attestation has duplicate record IDs")
    hashes = {record_id: sha256(canonical_bytes(row)) for record_id, row in rows.items()}
    return rows, hashes


def _expect_row(rows: dict[str, Any], hashes: dict[str, str], record_id: str,
                expected_hash: str, kind: str) -> Any:
    row = rows.get(record_id)
    if row is None or row.record_type != kind or hashes[record_id] != expected_hash:
        raise ValueError(f"{kind} record reference or digest mismatch")
    return row


def _verify_route(item: RoutingAttestation, rows: dict[str, Any], hashes: dict[str, str],
                  expected_capability_tags: Mapping[str, str]) -> tuple[Any, Any]:
    decision, selected = item.decision, item.selected
    assert selected is not None and decision is not None
    instant = _records.utc_datetime(decision.decision_at)
    chosen_at = _records.utc_datetime(selected.selected_at)
    if chosen_at < instant:
        raise ValueError("selection preceded decision snapshot")
    session = _expect_row(rows, hashes, decision.session_record_id, decision.session_sha256, "session")
    task = _expect_row(rows, hashes, decision.task_record_id, decision.task_sha256, "task")
    obs = _expect_row(rows, hashes, decision.observation_record_id, decision.observation_sha256, "observation")
    if (session.coordinator_device_id != item.trusted_coordinator_device_id or
            obs.observation_id not in task.observation_ids or
            task.policy_sha256 != item.pins.policy_sha256 or task.scenario_sha256 != item.pins.scenario_sha256 or
            obs.artifact_sha256 != item.pins.model_sha256 or
            obs.input_ref != f"sha256:{item.pins.source_event_sha256}" or
            _records.utc_datetime(task.created_at) > instant or
            _records.utc_datetime(obs.created_at) > instant or
            _records.utc_datetime(obs.source_time) > instant or
            chosen_at >= _records.utc_datetime(task.expires_at)):
        raise ValueError("predecision task, observation or policy is inconsistent")
    candidates = {c.candidate_id: c for c in decision.candidates}
    if selected.candidate_id not in decision.eligible_candidate_ids:
        raise ValueError("selected candidate is ineligible")
    candidate = candidates[selected.candidate_id]
    if candidate.peer_id != selected.peer_id or selected.peer_id not in task.authorized_device_ids or selected.peer_id not in session.authorized_device_ids:
        raise ValueError("selected peer is unauthorized or differs from candidate")
    if len(decision.required_tags) != 1 or any(
        entry.required_tag != decision.required_tags[0] for entry in decision.candidates
    ):
        raise ValueError("single selected capability cannot cover inconsistent or multiple task tags")
    if {entry.capability_id for entry in decision.candidates} != set(task.required_capabilities):
        raise ValueError("candidate capability IDs differ from concrete task requirements")
    if (set(expected_capability_tags) != set(task.required_capabilities) or
            any(expected_capability_tags[entry.capability_id] != entry.required_tag
                for entry in decision.candidates)):
        raise ValueError("external capability tag policy differs from Task or candidate snapshot")
    capability_history = _reducer._status_history(
        (row for row in rows.values() if row.record_type == "capability"),
        identity="capability_id", revision="revision", status="status",
        transition=("available", "unavailable"),
    )
    effective_at_decision = _reducer._effective_versions(capability_history, instant)
    effective_at_selection = _reducer._effective_versions(capability_history, chosen_at)
    session_history = _reducer._session_history(
        [row for row in rows.values() if row.record_type == "session"]
    )
    session_at_decision = _reducer._effective_session(session_history, instant)
    session_at_selection = _reducer._effective_session(session_history, chosen_at)
    if session_at_decision.record_id != session.record_id:
        raise ValueError("cited session is not effective at decision snapshot")
    decision_session_open = (
        session_at_decision.status == "open"
        and session_at_decision.policy_version == item.policy_version
        and _records.utc_datetime(session_at_decision.opened_at) <= instant
        and (session_at_decision.closed_at is None or
             instant < _records.utc_datetime(session_at_decision.closed_at))
    )
    selection_session_open = (
        session_at_selection.status == "open"
        and session_at_selection.policy_version == item.policy_version
        and _records.utc_datetime(session_at_selection.opened_at) <= chosen_at
        and (session_at_selection.closed_at is None or
             chosen_at < _records.utc_datetime(session_at_selection.closed_at))
    )
    eligible_at_decision: set[str] = set()
    eligible_at_selection: set[str] = set()
    for entry in decision.candidates:
        cap = _expect_row(rows, hashes, entry.capability_record_id,
                          entry.capability_sha256, "capability")
        if (cap.capability_id != entry.capability_id or cap.producer_device_id != entry.peer_id or
                _records.utc_datetime(cap.created_at) > instant):
            raise ValueError("candidate capability provenance is inconsistent")
        if any(effective.get(entry.capability_id) is None or
               effective[entry.capability_id].record_id != cap.record_id
               for effective in (effective_at_decision, effective_at_selection)):
            raise ValueError("cited capability revision is not effective at decision and selection")
        available = (cap.status == "available" and
                     cap.capability_id in task.required_capabilities and
                     cap.policy_version == task.policy_version == item.policy_version)
        if (available and decision_session_open and
                entry.peer_id in task.authorized_device_ids and
                entry.peer_id in session_at_decision.authorized_device_ids and
                _records.utc_datetime(cap.valid_from) <= instant < _records.utc_datetime(cap.expires_at)):
            eligible_at_decision.add(entry.candidate_id)
        if (available and selection_session_open and
                entry.peer_id in task.authorized_device_ids and
                entry.peer_id in session_at_selection.authorized_device_ids and
                _records.utc_datetime(cap.valid_from) <= chosen_at < _records.utc_datetime(cap.expires_at)):
            eligible_at_selection.add(entry.candidate_id)
    declared = set(decision.eligible_candidate_ids)
    if declared != eligible_at_decision:
        raise ValueError("declared eligible candidates differ from decision snapshot; unsafe or omitted candidate")
    if declared != eligible_at_selection:
        raise ValueError("eligible candidates changed before selection")
    claim = _expect_row(rows, hashes, selected.claim_record_id, selected.claim_sha256, "claim")
    result = _expect_row(rows, hashes, selected.result_record_id, selected.result_sha256, "result")
    if (claim.claimant_device_id != selected.peer_id or claim.capability_id != candidate.capability_id or
            claim.task_id != task.task_id or claim.claim_status != "proposed" or
            _records.utc_datetime(claim.issued_at) < chosen_at or
            result.claim_id != claim.claim_id or result.task_id != task.task_id or
            result.worker_device_id != selected.peer_id or result.outcome != "completed" or
            result.artifact_sha256 != item.pins.model_sha256 or
            result.policy_sha256 != item.pins.policy_sha256 or
            result.scenario_sha256 != item.pins.scenario_sha256):
        raise ValueError("selected Claim or Result does not match eligible route")
    return claim, result


def _verify_readbacks(item: RoutingAttestation, rows: dict[str, Any], hashes: dict[str, str]) -> None:
    assert item.decision is not None and item.selected is not None and item.reducer_as_of is not None
    expected_peers = {candidate.peer_id for candidate in item.decision.candidates}
    if len(item.peer_readbacks) != 2 or {peer.peer_id for peer in item.peer_readbacks} != expected_peers:
        raise ValueError("both distinct candidate peers need SDK readback evidence")
    coordinator = next((peer for peer in item.peer_readbacks
                        if peer.peer_id == item.trusted_coordinator_device_id), None)
    if coordinator is None:
        raise ValueError("coordinator peer lacks SDK readback evidence")
    source_record_ids = {item.decision.session_record_id, item.decision.observation_record_id,
                         item.decision.task_record_id}
    if not source_record_ids <= set(coordinator.local_write_record_ids):
        raise ValueError("coordinator lacks local Session, Observation or Task SDK write evidence")
    query = coordinator.decision_query
    if query is None or _records.utc_datetime(query.queried_at) >= _records.utc_datetime(item.decision.decision_at):
        raise ValueError("coordinator decision query must precede route decision")
    required_query_hashes = {
        item.decision.session_record_id: item.decision.session_sha256,
        item.decision.observation_record_id: item.decision.observation_sha256,
        item.decision.task_record_id: item.decision.task_sha256,
        **{candidate.capability_record_id: candidate.capability_sha256
           for candidate in item.decision.candidates},
    }
    observed_query_hashes = query.as_map()
    if any(observed_query_hashes.get(record_id) != digest
           for record_id, digest in required_query_hashes.items()):
        raise ValueError("coordinator decision query lacks a cited Session, Observation, Task or Capability")
    _verify_query_rows("decision query", query, rows, hashes)
    for peer in item.peer_readbacks:
        if peer.peer_id != item.trusted_coordinator_device_id and peer.decision_query is not None:
            raise ValueError("decision query is only permitted on the coordinator peer")
        if peer.sdk_distribution_sha256 != item.pins.sdk_distribution_sha256:
            raise ValueError("peer SDK digest differs from pin")
        local = set(peer.local_write_record_ids)
        if any(record_id not in rows or rows[record_id].producer_device_id != peer.peer_id for record_id in local):
            raise ValueError("local SDK write references wrong peer or absent record")
        capabilities = {candidate.capability_record_id for candidate in item.decision.candidates
                        if candidate.peer_id == peer.peer_id}
        if not capabilities <= local:
            raise ValueError("advertised capability lacks owning peer local SDK write evidence")
        reopened = peer.reopen.as_map()
        if any(reopened.get(record_id) != hashes[record_id] for record_id in local):
            raise ValueError("local records did not survive reopen query")
        for stage, query in (("reopen", peer.reopen), ("rejoin", peer.after_rejoin)):
            _verify_query_rows(stage, query, rows, hashes)
        if peer.peer_id == item.selected.peer_id and not {
            item.selected.claim_record_id, item.selected.result_record_id
        } <= local:
            raise ValueError("selected peer lacks local Claim and Result SDK write evidence")
        if peer.after_rejoin.as_map() != hashes:
            raise ValueError("peer did not query the converged complete record set")
        if _records.utc_datetime(peer.after_rejoin.queried_at) <= _records.utc_datetime(item.reducer_as_of):
            raise ValueError("rejoin readback must follow reducer decision")


def _verify_query_rows(stage: str, query: Any, rows: dict[str, Any], hashes: dict[str, str]) -> None:
    queried_at = _records.utc_datetime(query.queried_at)
    for record_id, observed_hash in query.as_map().items():
        row = rows.get(record_id)
        if row is None or observed_hash != hashes[record_id]:
            raise ValueError(f"{stage} contains an absent or changed final record")
        write_times = [row.created_at]
        if row.record_type == "claim":
            write_times.append(row.issued_at)
        elif row.record_type == "result":
            write_times.append(row.completed_at)
        if queried_at < max(_records.utc_datetime(value) for value in write_times):
            raise ValueError(f"{stage} predates a returned SDK record")


def verify_attestation(value: RoutingAttestation | dict[str, Any],
                       receipt_value: ReviewerReceipt | dict[str, Any], *,
                       expected_pins: RunPins | dict[str, Any],
                       trusted_reviewer_keys: Mapping[str, tuple[str, bytes]],
                       expected_capability_tags: Mapping[str, str]) -> VerifiedRoutingAttestation:
    """Accept replayed evidence under external reviewer and capability tag policies."""
    item = RoutingAttestation.model_validate(value)
    expected = RunPins.model_validate(expected_pins)
    receipt = ReviewerReceipt.model_validate(receipt_value)
    if item.run_status != "succeeded" or item.selected is None:
        raise ValueError("failed runs cannot be accepted as routing outcomes")
    assert item.decision is not None and item.reducer_as_of is not None
    if item.pins != expected:
        raise ValueError("attestation differs from externally expected pins")
    if not isinstance(expected_capability_tags, Mapping):
        raise TypeError("external capability tag policy must be a mapping")
    capability_tags = dict(expected_capability_tags)
    for capability_id, required_tag in capability_tags.items():
        _schema._id(capability_id)
        _schema._id(required_tag)
    if (sha256((_schema.MESH / "records.py").read_bytes()) != item.pins.records_module_sha256 or
            sha256((_schema.MESH / "reducer.py").read_bytes()) != item.pins.reducer_module_sha256):
        raise ValueError("executed records or reducer module differs from pinned bytes")
    rows, hashes = _record_map(item)
    claim, result = _verify_route(item, rows, hashes, capability_tags)
    _verify_readbacks(item, rows, hashes)
    state = _reducer.reduce_records(item.records, group_id=item.group_id,
                                    session_id=item.session_id, as_of=item.reducer_as_of,
                                    trusted_coordinator_device_id=item.trusted_coordinator_device_id,
                                    expected_policy_version=item.policy_version,
                                    expected_policy_sha256=item.pins.policy_sha256)
    task_state = next((t for t in state.tasks if t.task_id == claim.task_id), None)
    if (state.state_digest != item.reducer_state_sha256 or
            state.accepted_record_set_digest != item.accepted_record_set_sha256 or
            task_state is None or task_state.winner_claim_id != claim.claim_id or
            task_state.accepted_result_id != result.result_id or task_state.state != "completed" or
            not any(c.claim_id == claim.claim_id and c.reason == "winner" for c in state.claim_decisions) or
            not any(r.result_id == result.result_id and r.reason == "accepted" for r in state.result_decisions)):
        raise ValueError("reducer did not accept the selected Claim and Result")
    if (receipt.verdict != "accepted" or receipt.attestation_sha256 != attestation_digest(item) or
            receipt.execution_sha256 != execution_digest(item) or
            receipt.outcome_sha256 != outcome_digest(item)):
        raise ValueError("reviewer receipt does not accept these exact evidence digests")
    if _records.utc_datetime(receipt.reviewed_at) < max(
        _records.utc_datetime(peer.after_rejoin.queried_at) for peer in item.peer_readbacks
    ):
        raise ValueError("review preceded final SDK readback")
    trusted = trusted_reviewer_keys.get(receipt.key_id)
    if not isinstance(trusted, tuple) or len(trusted) != 2:
        raise ValueError("reviewer key is absent from caller trust policy")
    reviewer_id, key = trusted
    if reviewer_id != receipt.reviewer_id:
        raise ValueError("reviewer identity differs from caller trust policy")
    if not isinstance(key, bytes) or len(key) != 32:
        raise ValueError("reviewer key is absent from caller trust policy")
    try:
        Ed25519PublicKey.from_public_bytes(key).verify(
            base64.b64decode(receipt.signature_base64, validate=True),
            receipt_signing_bytes(receipt),
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("reviewer signature is invalid") from error
    return VerifiedRoutingAttestation(attestation_sha256=receipt.attestation_sha256,
                                      selected_peer_id=item.selected.peer_id,
                                      accepted_result_id=result.result_id,
                                      reviewer_id=receipt.reviewer_id)
