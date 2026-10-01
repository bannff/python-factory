"""Strict, license-free evidence contract for a host-collected N=2 SDK route.

The signature proves a trusted reviewer's receipt over these bytes. Actual SDK
provenance still depends on the sealed collector and human review of its inputs.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MESH = Path(__file__).parents[1] / "edge-mesh-coordinator-001"
_RECORD_SPEC = importlib.util.spec_from_file_location("edge_mesh_records_for_routing_sdk", MESH / "records.py")
assert _RECORD_SPEC is not None and _RECORD_SPEC.loader is not None
_records = importlib.util.module_from_spec(_RECORD_SPEC)
sys.modules.setdefault(_RECORD_SPEC.name, _records)
_RECORD_SPEC.loader.exec_module(_records)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,95}$")


def canonical_bytes(value: Any) -> bytes:
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False,
                      ensure_ascii=False).encode("utf-8")


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_attestation_json_bytes(value: bytes) -> RoutingAttestation:
    """Reject duplicate JSON keys and nonfinite values before Pydantic validation."""
    if not isinstance(value, bytes) or len(value) > 1_048_576:
        raise ValueError("attestation JSON must be bytes of at most 1 MiB")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    data = json.loads(value.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)))
    return RoutingAttestation.model_validate(data)


def _digest(value: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError("digest must be lowercase SHA-256 hex")
    return value


def _id(value: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError("identity must be a bounded safe ID")
    return value


def _time(value: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("time must be RFC3339 UTC")
    _records.utc_datetime(value)
    return value


def _tuple(value: Any) -> Any:
    return tuple(value) if isinstance(value, list) else value


class FrozenValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RunPins(FrozenValue):
    run_id: str
    scenario_sha256: str
    image_sha256: str
    source_sha256: str
    source_event_sha256: str
    model_sha256: str
    cohort_sha256: str
    sdk_distribution_sha256: str
    policy_sha256: str
    records_module_sha256: str
    reducer_module_sha256: str

    @field_validator("run_id")
    @classmethod
    def _run(cls, value: str) -> str:
        return _id(value)

    @field_validator("scenario_sha256", "image_sha256", "source_sha256", "source_event_sha256",
                     "model_sha256", "cohort_sha256",
                     "sdk_distribution_sha256", "policy_sha256", "records_module_sha256",
                     "reducer_module_sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return _digest(value)


class Candidate(FrozenValue):
    candidate_id: str
    peer_id: str
    capability_record_id: str
    capability_sha256: str
    capability_id: str
    required_tag: str

    @field_validator("candidate_id", "peer_id", "capability_record_id", "capability_id", "required_tag")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _id(value)

    @field_validator("capability_sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return _digest(value)


class DecisionSnapshot(FrozenValue):
    decision_at: str
    task_record_id: str
    task_sha256: str
    observation_record_id: str
    observation_sha256: str
    session_record_id: str
    session_sha256: str
    required_tags: tuple[str, ...] = Field(min_length=1, max_length=16)
    candidates: tuple[Candidate, ...] = Field(min_length=2, max_length=2)
    eligible_candidate_ids: tuple[str, ...] = Field(min_length=1, max_length=2)

    @field_validator("required_tags", "candidates", "eligible_candidate_ids", mode="before")
    @classmethod
    def _arrays(cls, value: Any) -> Any:
        return _tuple(value)

    @field_validator("decision_at")
    @classmethod
    def _utc(cls, value: str) -> str:
        return _time(value)

    @field_validator("task_record_id", "observation_record_id", "session_record_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _id(value)

    @field_validator("required_tags", "eligible_candidate_ids")
    @classmethod
    def _distinct_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("snapshot IDs must be distinct")
        return tuple(_id(item) for item in value)

    @field_validator("task_sha256", "observation_sha256", "session_sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return _digest(value)

    @model_validator(mode="after")
    def _candidates(self) -> DecisionSnapshot:
        if len({c.candidate_id for c in self.candidates}) != 2 or len({c.peer_id for c in self.candidates}) != 2:
            raise ValueError("N=2 snapshot requires distinct candidates and peers")
        if not set(self.eligible_candidate_ids) <= {c.candidate_id for c in self.candidates}:
            raise ValueError("eligible candidate is absent")
        return self


class SelectedRoute(FrozenValue):
    candidate_id: str
    peer_id: str
    claim_record_id: str
    claim_sha256: str
    result_record_id: str
    result_sha256: str
    selected_at: str

    @field_validator("candidate_id", "peer_id", "claim_record_id", "result_record_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _id(value)

    @field_validator("claim_sha256", "result_sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return _digest(value)

    @field_validator("selected_at")
    @classmethod
    def _utc(cls, value: str) -> str:
        return _time(value)


class RecordHash(FrozenValue):
    record_id: str
    sha256: str

    @field_validator("record_id")
    @classmethod
    def _record(cls, value: str) -> str:
        return _id(value)

    @field_validator("sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return _digest(value)


class QueryEvidence(FrozenValue):
    queried_at: str
    record_sha256_by_id: tuple[RecordHash, ...] = Field(max_length=64)

    @field_validator("queried_at")
    @classmethod
    def _utc(cls, value: str) -> str:
        return _time(value)

    @field_validator("record_sha256_by_id", mode="before")
    @classmethod
    def _hashes(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return tuple({"record_id": key, "sha256": digest} for key, digest in sorted(value.items()))
        return _tuple(value)

    @model_validator(mode="after")
    def _distinct(self) -> QueryEvidence:
        ids = [item.record_id for item in self.record_sha256_by_id]
        if len(ids) != len(set(ids)):
            raise ValueError("query record IDs must be unique")
        return self

    def as_map(self) -> dict[str, str]:
        return {item.record_id: item.sha256 for item in self.record_sha256_by_id}


class PeerReadback(FrozenValue):
    peer_id: str
    sdk_distribution_sha256: str
    local_write_record_ids: tuple[str, ...] = Field(min_length=1, max_length=64)
    decision_query: QueryEvidence | None
    reopen: QueryEvidence
    after_rejoin: QueryEvidence
    disconnect_observed: Literal[True]
    rejoin_observed: Literal[True]

    @field_validator("peer_id")
    @classmethod
    def _peer(cls, value: str) -> str:
        return _id(value)

    @field_validator("sdk_distribution_sha256")
    @classmethod
    def _sdk(cls, value: str) -> str:
        return _digest(value)

    @field_validator("local_write_record_ids", mode="before")
    @classmethod
    def _array(cls, value: Any) -> Any:
        return _tuple(value)

    @field_validator("local_write_record_ids")
    @classmethod
    def _ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("local write IDs must be unique")
        return tuple(_id(item) for item in value)

    @model_validator(mode="after")
    def _ordered(self) -> PeerReadback:
        if _records.utc_datetime(self.reopen.queried_at) >= _records.utc_datetime(self.after_rejoin.queried_at):
            raise ValueError("SDK rejoin query must follow reopen query")
        return self


class RoutingAttestation(FrozenValue):
    schema_version: Literal[2]
    run_status: Literal["succeeded", "failed"]
    failure_reason: str | None
    pins: RunPins
    group_id: str
    session_id: str
    trusted_coordinator_device_id: str
    policy_version: str
    decision: DecisionSnapshot | None
    selected: SelectedRoute | None
    records: tuple[_records.Record, ...] = Field(max_length=64)
    peer_readbacks: tuple[PeerReadback, ...] = Field(max_length=2)
    reducer_as_of: str | None
    reducer_state_sha256: str | None
    accepted_record_set_sha256: str | None

    @field_validator("records", "peer_readbacks", mode="before")
    @classmethod
    def _arrays(cls, value: Any) -> Any:
        return _tuple(value)

    @field_validator("records", mode="before")
    @classmethod
    def _typed_records(cls, value: Any) -> Any:
        return tuple(_records.parse_record(item) for item in value)

    @field_validator("group_id", "session_id", "trusted_coordinator_device_id", "policy_version")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _id(value)

    @field_validator("reducer_as_of")
    @classmethod
    def _utc(cls, value: str | None) -> str | None:
        return _time(value) if value is not None else None

    @field_validator("reducer_state_sha256", "accepted_record_set_sha256")
    @classmethod
    def _hash(cls, value: str | None) -> str | None:
        return _digest(value) if value is not None else None

    @model_validator(mode="after")
    def _status(self) -> RoutingAttestation:
        if self.run_status == "succeeded" and (
            self.failure_reason is not None or self.decision is None or self.selected is None or
            not self.records or len(self.peer_readbacks) != 2 or self.reducer_as_of is None or
            self.reducer_state_sha256 is None or self.accepted_record_set_sha256 is None
        ):
            raise ValueError("successful run requires complete route evidence and no failure reason")
        if self.run_status == "succeeded" and any(
            (peer.decision_query is None) != (peer.peer_id != self.trusted_coordinator_device_id)
            for peer in self.peer_readbacks
        ):
            raise ValueError("decision query is required only on the coordinator peer")
        if self.run_status == "failed" and (not self.failure_reason or len(self.failure_reason) > 200):
            raise ValueError("failed run requires a bounded failure reason")
        return self


class ReviewerReceipt(FrozenValue):
    schema_version: Literal[2]
    attestation_sha256: str
    execution_sha256: str
    outcome_sha256: str
    reviewer_id: str
    key_id: str
    verdict: Literal["accepted", "rejected"]
    reviewed_at: str
    signature_base64: str

    @field_validator("attestation_sha256", "execution_sha256", "outcome_sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return _digest(value)

    @field_validator("reviewer_id", "key_id")
    @classmethod
    def _ids(cls, value: str) -> str:
        return _id(value)

    @field_validator("reviewed_at")
    @classmethod
    def _utc(cls, value: str) -> str:
        return _time(value)

    @field_validator("signature_base64")
    @classmethod
    def _signature(cls, value: str) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("signature must be canonical base64") from error
        if len(raw) != 64 or base64.b64encode(raw).decode("ascii") != value:
            raise ValueError("signature must be canonical Ed25519 bytes")
        return value


class VerifiedRoutingAttestation(FrozenValue):
    attestation_sha256: str
    selected_peer_id: str
    accepted_result_id: str
    reviewer_id: str
