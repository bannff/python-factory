"""Immutable, leakage-safe examples for observed edge mesh routing outcomes."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .base import _normalize_digest, _require_non_empty


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _stable_id(value: str) -> str:
    if not _ID_RE.fullmatch(value):
        raise ValueError("Routing IDs must be stable nonblank ASCII identifiers")
    return value


def _utc_time(value: datetime | str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Routing timestamps must be RFC 3339 UTC") from error
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Routing timestamps must be RFC 3339 UTC")
    offset = value.utcoffset()
    if offset is None or offset.total_seconds() != 0:
        raise ValueError("Routing timestamps must use UTC offset zero")
    return value.astimezone(UTC)


def _immutable_sequence(value: object) -> object:
    """Accept JSON arrays while storing validated sequences as immutable tuples."""
    return tuple(value) if isinstance(value, list) else value


class _RoutingValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class RoutingContentRef(_RoutingValue):
    """A separately verifiable immutable JSON evidence object."""

    uri: str
    sha256: str

    @field_validator("uri")
    @classmethod
    def _uri(cls, value: str) -> str:
        return _require_non_empty(value, "Routing evidence URI")

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        return _normalize_digest(value, "routing evidence")


class RoutingCandidateSnapshot(_RoutingValue):
    """Only values observed about a candidate before the route decision."""

    candidate_id: str
    capability_id: str
    capabilities: tuple[str, ...] = Field(min_length=1, max_length=16)
    role: str
    model_id: str
    model_artifact_sha256: str
    observed_at: datetime
    expires_at: datetime
    status: Literal["available", "unavailable"]
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    cpu_utilization_pct: int | None = Field(default=None, ge=0, le=100)
    memory_available_mib: int | None = Field(default=None, ge=0, le=1_048_576)
    estimated_link_latency_ms: int | None = Field(default=None, ge=0, le=600_000)

    @field_validator("candidate_id", "capability_id", "role", "model_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _stable_id(value)

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Candidate capabilities must be unique")
        return tuple(_stable_id(item) for item in value)

    @field_validator("capabilities", mode="before")
    @classmethod
    def _json_capabilities(cls, value: object) -> object:
        return _immutable_sequence(value)

    @field_validator("model_artifact_sha256")
    @classmethod
    def _model_digest(cls, value: str) -> str:
        return _normalize_digest(value, "routing model artifact")

    @field_validator("observed_at", "expires_at", mode="before")
    @classmethod
    def _time(cls, value: datetime | str) -> datetime:
        return _utc_time(value)

    @model_validator(mode="after")
    def _valid_window(self) -> RoutingCandidateSnapshot:
        if self.expires_at <= self.observed_at:
            raise ValueError("Candidate expiry must follow observation")
        return self


class RoutingDecisionFeatures(_RoutingValue):
    """Explicit feature allowlist frozen at decision time; no result fields."""

    group_id: str
    session_id: str
    task_id: str
    source_event_id: str
    source_event_ref: RoutingContentRef
    source_event_at: datetime
    decision_at: datetime
    task_kind: str
    policy_version: str
    policy_sha256: str
    reducer_sha256: str
    scenario_sha256: str
    required_capabilities: tuple[str, ...] = Field(min_length=1, max_length=16)
    candidate_snapshot_ref: RoutingContentRef
    candidates: tuple[RoutingCandidateSnapshot, ...] = Field(min_length=1, max_length=32)
    eligible_candidate_ids: tuple[str, ...] = Field(max_length=32)

    @field_validator(
        "required_capabilities", "candidates", "eligible_candidate_ids", mode="before",
    )
    @classmethod
    def _json_arrays(cls, value: object) -> object:
        return _immutable_sequence(value)

    @field_validator(
        "group_id", "session_id", "task_id", "source_event_id",
        "task_kind", "policy_version",
    )
    @classmethod
    def _id(cls, value: str) -> str:
        return _stable_id(value)

    @field_validator("required_capabilities", "eligible_candidate_ids")
    @classmethod
    def _ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Routing capability/candidate IDs must be unique")
        return tuple(_stable_id(item) for item in value)

    @field_validator("policy_sha256", "reducer_sha256", "scenario_sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        return _normalize_digest(value, "routing pin")

    @field_validator("source_event_at", "decision_at", mode="before")
    @classmethod
    def _time(cls, value: datetime | str) -> datetime:
        return _utc_time(value)

    @model_validator(mode="after")
    def _decision_snapshot(self) -> RoutingDecisionFeatures:
        if self.source_event_at > self.decision_at:
            raise ValueError("Source event cannot follow route decision")
        by_id = {candidate.candidate_id: candidate for candidate in self.candidates}
        if len(by_id) != len(self.candidates):
            raise ValueError("Candidate IDs must be unique")
        if len({candidate.capability_id for candidate in self.candidates}) != len(self.candidates):
            raise ValueError("Candidate capability IDs must be unique")
        required = set(self.required_capabilities)
        for candidate in self.candidates:
            if candidate.observed_at > self.decision_at:
                raise ValueError("Candidate snapshot cannot follow route decision")
        for candidate_id in self.eligible_candidate_ids:
            candidate = by_id.get(candidate_id)
            if candidate is None:
                raise ValueError("Eligible candidate is absent from snapshot")
            if candidate.status != "available" or candidate.expires_at <= self.decision_at:
                raise ValueError("Eligible candidate is unavailable or expired")
            if not required.issubset(candidate.capabilities):
                raise ValueError("Eligible candidate lacks required capability")
        return self


class ExecutedRoute(_RoutingValue):
    """The route actually attempted; other candidates have censored outcomes."""

    candidate_id: str
    selection_propensity: float = Field(gt=0, le=1, allow_inf_nan=False)
    selected_at: datetime
    execution_ref: RoutingContentRef

    @field_validator("candidate_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _stable_id(value)

    @field_validator("selected_at", mode="before")
    @classmethod
    def _time(cls, value: datetime | str) -> datetime:
        return _utc_time(value)


class RoutingReview(_RoutingValue):
    """Human or delegated adjudication of one observed executed outcome."""

    reviewer_ref: str
    adjudication_ref: RoutingContentRef
    reviewed_at: datetime
    verdict: Literal["accepted", "rejected"]

    @field_validator("reviewer_ref")
    @classmethod
    def _reviewer(cls, value: str) -> str:
        return _stable_id(value)

    @field_validator("reviewed_at", mode="before")
    @classmethod
    def _time(cls, value: datetime | str) -> datetime:
        return _utc_time(value)


class RoutingOutcomeEvidence(_RoutingValue):
    """Observed result for the executed route, with run and SDK provenance."""

    outcome_ref: RoutingContentRef
    run_id: str
    sdk_version: str
    provenance_kind: Literal["ditto_sdk_live", "simulated", "imported"]
    observed_at: datetime
    succeeded: bool
    review: RoutingReview | None = None

    @field_validator("run_id", "sdk_version")
    @classmethod
    def _id(cls, value: str) -> str:
        return _stable_id(value)

    @field_validator("observed_at", mode="before")
    @classmethod
    def _time(cls, value: datetime | str) -> datetime:
        return _utc_time(value)

    @model_validator(mode="after")
    def _review_time(self) -> RoutingOutcomeEvidence:
        if self.review is not None and self.review.reviewed_at < self.observed_at:
            raise ValueError("Review cannot precede observed outcome")
        return self


class EdgeRoutingExample(_RoutingValue):
    """One decision snapshot and at most one observed, reviewed route outcome."""

    schema_version: Literal["1.0"]
    record_id: str
    split: Literal["train", "validation", "test"]
    features: RoutingDecisionFeatures
    executed_route: ExecutedRoute | None = None
    outcome: RoutingOutcomeEvidence | None = None

    @field_validator("record_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _stable_id(value)

    @model_validator(mode="after")
    def _route_outcome_order(self) -> EdgeRoutingExample:
        route = self.executed_route
        if route is None:
            if self.outcome is not None:
                raise ValueError("Outcome requires an executed route")
            return self
        if route.candidate_id not in self.features.eligible_candidate_ids:
            raise ValueError("Executed route must select an eligible candidate")
        if route.selected_at < self.features.decision_at:
            raise ValueError("Route execution cannot precede decision")
        selected = next(
            candidate for candidate in self.features.candidates
            if candidate.candidate_id == route.candidate_id
        )
        if route.selected_at >= selected.expires_at:
            raise ValueError("Executed route cannot use an expired capability")
        if self.outcome is not None and self.outcome.observed_at < route.selected_at:
            raise ValueError("Outcome cannot precede route execution")
        return self


class RoutingDatasetReadiness(_RoutingValue):
    """A bounded training-readiness signal, before artifact integrity gates."""

    status: Literal["ready", "no_labels", "quality_blocked"]
    training_allowed: bool
    reason: str = Field(min_length=1, max_length=200)
    reviewed_label_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _coherent(self) -> RoutingDatasetReadiness:
        if self.training_allowed != (self.status == "ready"):
            raise ValueError("Readiness status and training_allowed disagree")
        return self


def is_reviewed_observed_outcome(record: EdgeRoutingExample) -> bool:
    """Only executed, accepted-review live SDK outcomes carry routing labels."""
    outcome = record.outcome
    return bool(
        record.executed_route is not None
        and outcome is not None
        and outcome.provenance_kind == "ditto_sdk_live"
        and outcome.review is not None
        and outcome.review.verdict == "accepted"
    )


def routing_dataset_readiness(
    records: Iterable[EdgeRoutingExample | dict],
) -> RoutingDatasetReadiness:
    """Require reviewed labels, full quality, and trusted run provenance."""
    from .validation import validate_edge_routing_records
    from .quality_edge_routing import evaluate_edge_routing_quality

    counts = {"train": 0, "validation": 0, "test": 0}
    counted_ids: set[str] = set()
    validated = list(validate_edge_routing_records(records))
    for record in validated:
        if record.record_id not in counted_ids and is_reviewed_observed_outcome(record):
            counts[record.split] += 1
            counted_ids.add(record.record_id)
    total = sum(counts.values())
    missing = [split for split, count in counts.items() if count == 0]
    if missing:
        return RoutingDatasetReadiness(
            status="no_labels", training_allowed=False,
            reason=f"No reviewed live SDK outcome labels in {', '.join(missing)} split(s)",
            reviewed_label_count=total,
        )
    quality = evaluate_edge_routing_quality(validated)
    trusted = quality.checks.get("trusted_run_provenance", "failed: not evaluated")
    if not quality.passed or not (trusted == "passed" or trusted.startswith("passed:")):
        failed = {
            name for name, result in quality.checks.items()
            if result.startswith("failed:")
        }
        if not trusted.startswith("passed"):
            failed.add("trusted_run_provenance")
        priority = (
            "trusted_run_provenance", "evidence_integrity", "session_split_isolation",
        )
        ordered = [name for name in priority if name in failed]
        ordered.extend(sorted(failed - set(ordered)))
        return RoutingDatasetReadiness(
            status="quality_blocked", training_allowed=False,
            reason=f"Quality gates failed: {', '.join(ordered[:3])} ({len(failed)} checks)",
            reviewed_label_count=total,
        )
    return RoutingDatasetReadiness(
        status="ready", training_allowed=True,
        reason="Reviewed live SDK labels and trusted evidence passed quality gates",
        reviewed_label_count=total,
    )
