"""Strict ingress contracts for host-collected routing SDK documents."""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

_ATTESTATION_PATH = Path(__file__).with_name("attestation.py").resolve()
attestation = next((module for module in sys.modules.values()
                    if getattr(module, "__file__", None) is not None
                    and Path(module.__file__).resolve() == _ATTESTATION_PATH
                    and hasattr(module, "_schema")), None)
if attestation is None:
    _SPEC = importlib.util.spec_from_file_location("edge_routing_attestation_for_collection", _ATTESTATION_PATH)
    assert _SPEC is not None and _SPEC.loader is not None
    attestation = importlib.util.module_from_spec(_SPEC)
    sys.modules[_SPEC.name] = attestation
    _SPEC.loader.exec_module(attestation)
schema = attestation._schema
records = schema._records


class CollectionPolicy(schema.FrozenValue):
    """Host-owned expectations; never sourced from the run container."""

    pins: schema.RunPins
    peer_ids: tuple[str, str]
    network_id: str
    group_id: str
    session_id: str
    coordinator_id: str
    policy_version: str
    capability_tags: dict[str, str]
    expected_probability: float = Field(ge=0, le=1)
    expected_decision: Literal[0, 1]
    score_tolerance: float = Field(ge=0, le=0.001)
    resource_nano_cpus: int = Field(gt=0)
    resource_memory_bytes: int = Field(gt=0)

    @field_validator("expected_probability", "score_tolerance")
    @classmethod
    def _finite_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("reviewed score policy must be finite")
        return value

    @field_validator("peer_ids", mode="before")
    @classmethod
    def _array(cls, value: Any) -> Any:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("network_id")
    @classmethod
    def _network(cls, value: str) -> str:
        return schema._digest(value)

    @field_validator("group_id", "session_id", "coordinator_id", "policy_version")
    @classmethod
    def _id(cls, value: str) -> str:
        return schema._id(value)

    @model_validator(mode="after")
    def _members(self) -> CollectionPolicy:
        if len(set(self.peer_ids)) != 2 or self.coordinator_id not in self.peer_ids:
            raise ValueError("exactly two distinct peers including coordinator are required")
        for peer_id in self.peer_ids:
            schema._id(peer_id)
        if not self.capability_tags or len(self.capability_tags) > 16:
            raise ValueError("external capability tag policy is empty or oversized")
        for capability_id, tag in self.capability_tags.items():
            schema._id(capability_id)
            schema._id(tag)
        return self


class SDKQuery(schema.FrozenValue):
    queried_at: str
    documents: tuple[records.Record, ...] = Field(max_length=64)

    @field_validator("queried_at")
    @classmethod
    def _utc(cls, value: str) -> str:
        return schema._time(value)

    @field_validator("documents", mode="before")
    @classmethod
    def _parse(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise TypeError("SDK documents must be an array")
        return tuple(records.parse_record(item) for item in value)

    @model_validator(mode="after")
    def _unique(self) -> SDKQuery:
        ids = [item.record_id for item in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("SDK query contains duplicate record IDs")
        return self


class LocalInference(schema.FrozenValue):
    schema_version: Literal[1]
    source_event_sha256: str
    model_sha256: str
    probability: float = Field(ge=0, le=1)
    decision: Literal[0, 1]
    inference_ms: float = Field(ge=0)

    @field_validator("source_event_sha256", "model_sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return schema._digest(value)

    @field_validator("probability", "inference_ms")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("local inference measurement must be finite")
        return value


class Measurement(schema.FrozenValue):
    """A measured scalar, or an explicit reason that the boundary cannot expose it."""

    value: int | float | None
    unit: Literal["bytes", "microseconds", "milliseconds"]
    unavailable_reason: Literal[
        "api_unavailable", "read_failed", "counter_reset", "unsupported_cgroup_v2",
        "not_exposed_by_public_sdk",
    ] | None

    @field_validator("value")
    @classmethod
    def _finite_nonnegative(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("measurement must be finite and nonnegative")
        return value

    @model_validator(mode="after")
    def _available_or_reason(self) -> Measurement:
        if (self.value is None) == (self.unavailable_reason is None):
            raise ValueError("measurement needs exactly one value or unavailable reason")
        if self.unit in ("bytes", "microseconds") and self.value is not None and type(self.value) is not int:
            raise ValueError("byte and microsecond measurements must be integers")
        return self


class PeerMeasurements(schema.FrozenValue):
    disk_usage_before: Measurement
    disk_usage_after: Measurement
    disk_usage_growth: Measurement
    write_total: Measurement
    query_total: Measurement

    @model_validator(mode="after")
    def _disk_growth(self) -> PeerMeasurements:
        if (self.disk_usage_before.unit != "bytes" or self.disk_usage_after.unit != "bytes"
                or self.disk_usage_growth.unit != "bytes"
                or self.write_total.unit != "microseconds" or self.query_total.unit != "microseconds"):
            raise ValueError("peer measurement units differ from their fields")
        values = (self.disk_usage_before.value, self.disk_usage_after.value,
                  self.disk_usage_growth.value)
        if values[0] is not None and values[1] is not None:
            if values[2] != values[1] - values[0]:
                raise ValueError("database disk growth must equal after minus before")
        elif self.disk_usage_growth.value is not None:
            raise ValueError("database disk growth cannot be inferred from missing readings")
        return self


class RunMeasurements(schema.FrozenValue):
    cgroup_cpu_usage: Measurement
    cgroup_memory_peak: Measurement
    task_delivery: Measurement
    rejoin_delivery: Measurement
    end_to_end: Measurement
    raw_mesh_bytes: Measurement

    @model_validator(mode="after")
    def _mesh_unavailable(self) -> RunMeasurements:
        if (self.cgroup_cpu_usage.unit != "microseconds"
                or self.cgroup_memory_peak.unit != "bytes"
                or any(item.unit != "milliseconds" for item in
                       (self.task_delivery, self.rejoin_delivery, self.end_to_end))
                or self.raw_mesh_bytes.unit != "bytes"):
            raise ValueError("run measurement units differ from their fields")
        if (self.raw_mesh_bytes.value is not None
                or self.raw_mesh_bytes.unavailable_reason != "not_exposed_by_public_sdk"):
            raise ValueError("public SDK does not expose raw mesh byte counters")
        return self


class PeerSDKFile(schema.FrozenValue):
    schema_version: Literal[2]
    peer_id: str
    sdk_distribution_sha256: str
    local_write_documents: tuple[records.Record, ...] = Field(max_length=64)
    decision_query: SDKQuery | None = None
    reopen: SDKQuery
    after_rejoin: SDKQuery
    local_inference: LocalInference | None
    measurements: PeerMeasurements
    disconnect_observed: bool
    rejoin_observed: bool

    @field_validator("peer_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return schema._id(value)

    @field_validator("sdk_distribution_sha256")
    @classmethod
    def _hash(cls, value: str) -> str:
        return schema._digest(value)

    @field_validator("local_write_documents", mode="before")
    @classmethod
    def _parse(cls, value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            raise TypeError("local SDK writes must be an array")
        return tuple(records.parse_record(item) for item in value)

    @model_validator(mode="after")
    def _ordered(self) -> PeerSDKFile:
        ids = [item.record_id for item in self.local_write_documents]
        if len(ids) != len(set(ids)):
            raise ValueError("local SDK writes contain duplicate record IDs")
        if records.utc_datetime(self.reopen.queried_at) >= records.utc_datetime(self.after_rejoin.queried_at):
            raise ValueError("rejoin query must follow reopen")
        return self


class RunIndex(schema.FrozenValue):
    schema_version: Literal[2]
    run_status: Literal["succeeded", "failed"]
    failure_reason: Literal[
        "sdk_start_failed", "sdk_write_failed", "sdk_query_failed",
        "sdk_reopen_failed", "sdk_rejoin_failed", "routing_failed", "timed_out",
    ] | None
    pins: schema.RunPins
    group_id: str
    session_id: str
    coordinator_id: str
    policy_version: str
    decision: schema.DecisionSnapshot | None
    selected: schema.SelectedRoute | None
    reducer_as_of: str | None
    files_sha256: dict[str, str]
    measurements: RunMeasurements | None

    @field_validator("group_id", "session_id", "coordinator_id", "policy_version")
    @classmethod
    def _id(cls, value: str) -> str:
        return schema._id(value)

    @field_validator("reducer_as_of")
    @classmethod
    def _utc(cls, value: str | None) -> str | None:
        return schema._time(value) if value is not None else None

    @model_validator(mode="after")
    def _status(self) -> RunIndex:
        if self.run_status == "succeeded" and (
            self.failure_reason is not None or self.decision is None or
            self.selected is None or self.reducer_as_of is None or self.measurements is None
        ):
            raise ValueError("successful run index lacks a complete route")
        if self.run_status == "failed" and (
            self.failure_reason is None or
            self.decision is not None or self.selected is not None or self.reducer_as_of is not None
            or self.measurements is not None
        ):
            raise ValueError("failed run index contains a success route or invalid failure reason")
        if (self.run_status == "succeeded" and len(self.files_sha256) != 2
                or self.run_status == "failed" and len(self.files_sha256) not in (0, 2)):
            raise ValueError("run index requires zero or exactly two peer evidence digests")
        for digest in self.files_sha256.values():
            schema._digest(digest)
        return self
