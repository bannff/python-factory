"""Host integrity checks for supplied native compatibility claims.

Passing these checks proves supplied files are internally consistent. A separate
controlled simulator/emulator runner must establish native provenance before
any result can be published as a completed compatibility run.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator

from .contracts import NativeRunResult, NativeScenario, StrictContract, validate_result_for_scenario
from .prediction_evidence import dataset_sample_ids, measured_max_error

_MAX_TRACE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class NativeEvidenceFiles:
    app_build: Path
    ditto_sdk_package: Path
    device_runtime_manifest: Path
    loaded_model: Path
    dataset: Path
    event_trace: Path
    observation: Path
    persistence_readback: Path
    peer_readback: Path
    native_predictions: Path
    reference_predictions: Path


@dataclass(frozen=True)
class NativeIntegrityReport:
    status: Literal["integrity_verified"]
    native_provenance: Literal["unverified"]
    scenario_sha256: str
    result_sha256: str
    sample_count: int
    measured_max_absolute_error: float


class NativeTraceEvent(StrictContract):
    event: Literal[
        "ditto_started", "model_loaded", "inference", "observation_written",
        "peer_observed", "writer_reopened", "persistence_readback",
        "peer_reopened", "peer_readback",
    ]
    run_id: str = Field(min_length=1)
    peer_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    sdk_version: str | None = None
    cloud_disabled: Literal[True] | None = None
    model_id: str | None = None
    model_sha256: str | None = None
    sample_id: str | None = None
    observation_sha256: str | None = None

    @field_validator("model_sha256", "observation_sha256")
    @classmethod
    def digest_or_none(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 64 or any(c not in "0123456789abcdef" for c in value)):
            raise ValueError("expected lowercase SHA-256 digest")
        return value


def _hash_file(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"required evidence file is missing: {path}")
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
    except OSError as exc:
        raise ValueError(f"cannot read evidence file: {path}") from exc
    if not size:
        raise ValueError(f"required evidence file is empty: {path}")
    return digest.hexdigest()


def _read_hashed_bytes(path: Path, expected_digest: str) -> bytes:
    content = path.read_bytes()
    if not content or hashlib.sha256(content).hexdigest() != expected_digest:
        raise ValueError(f"{path.name} evidence hash does not match completed result")
    return content


def _trace_events(path: Path, expected_digest: str) -> list[NativeTraceEvent]:
    if not path.is_file():
        raise ValueError(f"required evidence file is missing: {path}")
    if path.stat().st_size > _MAX_TRACE_BYTES:
        raise ValueError("event trace exceeds 16 MiB")
    try:
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_digest:
            raise ValueError("event_trace evidence hash does not match completed result")
        lines = content.decode("utf-8").splitlines()
        if not lines or any(not line.strip() for line in lines):
            raise ValueError("event trace must contain nonblank JSONL events")
        return [NativeTraceEvent.model_validate_json(line) for line in lines]
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read event trace: {path}") from exc


def _expected_base(event: str, run_id: str, peer_id: str, session_id: str, **data: Any) -> dict[str, Any]:
    return {"event": event, "run_id": run_id, "peer_id": peer_id, "session_id": session_id, **data}


def _verify_trace(result: NativeRunResult, trace: list[NativeTraceEvent]) -> list[str]:
    assert result.execution is not None
    execution = result.execution
    run_id = execution.observed.run_id
    writer, peer = execution.writer, execution.peer
    w0, w1 = writer.initial_session_id, writer.reopen_session_id
    p0, p1 = peer.initial_session_id, peer.reopen_session_id
    expected = [
        _expected_base("ditto_started", run_id, writer.peer_id, w0,
                       sdk_version=execution.ditto_sdk_version, cloud_disabled=True),
        _expected_base("ditto_started", run_id, peer.peer_id, p0,
                       sdk_version=execution.ditto_sdk_version, cloud_disabled=True),
        _expected_base("model_loaded", run_id, writer.peer_id, w0,
                       model_id=execution.loaded_model.model_id,
                       model_sha256=execution.loaded_model.sha256),
    ]
    if len(trace) != len(expected) + execution.inference_count + 6:
        raise ValueError("event trace has wrong event count")
    sample_ids: set[str] = set()
    ordered_sample_ids: list[str] = []
    for event in trace[3:3 + execution.inference_count]:
        if event.sample_id is None or not event.sample_id.strip() or event.sample_id in sample_ids:
            raise ValueError("inference sample IDs must be present and unique")
        sample_ids.add(event.sample_id)
        ordered_sample_ids.append(event.sample_id)
        expected.append(_expected_base("inference", run_id, writer.peer_id, w0,
                                       sample_id=event.sample_id))
    digest = execution.observation_sha256
    expected.extend((
        _expected_base("observation_written", run_id, writer.peer_id, w0,
                       observation_sha256=digest),
        _expected_base("peer_observed", run_id, peer.peer_id, p0,
                       observation_sha256=digest),
        _expected_base("writer_reopened", run_id, writer.peer_id, w1),
        _expected_base("persistence_readback", run_id, writer.peer_id, w1,
                       observation_sha256=digest),
        _expected_base("peer_reopened", run_id, peer.peer_id, p1),
        _expected_base("peer_readback", run_id, peer.peer_id, p1,
                       observation_sha256=digest),
    ))
    for index, (event, required) in enumerate(zip(trace, expected, strict=True)):
        if event.model_dump(exclude_none=True) != required:
            raise ValueError(f"event trace mismatch at event {index}: {required['event']}")
    return ordered_sample_ids


def verify_completed_result(
    scenario_file: Path, result_file: Path, files: NativeEvidenceFiles,
) -> NativeIntegrityReport:
    """Check a supplied claim's files; this does not establish native provenance."""
    scenario_bytes = scenario_file.read_bytes()
    result_bytes = result_file.read_bytes()
    scenario = NativeScenario.model_validate_json(scenario_bytes)
    result = NativeRunResult.model_validate_json(result_bytes)
    if result.status != "completed":
        raise ValueError("integrity check requires a completed result claim")
    validate_result_for_scenario(result, scenario)
    assert result.execution is not None
    execution = result.execution
    paths = [getattr(files, field.name) for field in fields(NativeEvidenceFiles)]
    for path in paths:
        if not path.is_file():
            raise ValueError(f"required evidence file is missing: {path}")
    if len({(path.stat().st_dev, path.stat().st_ino) for path in paths}) != len(paths):
        raise ValueError("evidence files must be distinct")
    expected = {
        "app_build": execution.app_build.artifact_sha256,
        "ditto_sdk_package": execution.ditto_sdk_package_sha256,
        "device_runtime_manifest": execution.device_runtime.manifest_sha256,
        "loaded_model": scenario.model_sha256,
        "dataset": scenario.dataset_sha256,
        "event_trace": execution.event_trace_sha256,
        "observation": execution.observation_sha256,
        "persistence_readback": execution.persistence_readback_sha256,
        "peer_readback": execution.peer_readback_sha256,
        "native_predictions": execution.native_predictions_sha256,
        "reference_predictions": execution.reference_predictions_sha256,
    }
    for name, digest in expected.items():
        if name == "event_trace":
            continue
        if _hash_file(getattr(files, name)) != digest:
            raise ValueError(f"{name} evidence hash does not match completed result")
    sample_ids = _verify_trace(result, _trace_events(files.event_trace, expected["event_trace"]))
    dataset_bytes = _read_hashed_bytes(files.dataset, expected["dataset"])
    native_bytes = _read_hashed_bytes(files.native_predictions, expected["native_predictions"])
    reference_bytes = _read_hashed_bytes(files.reference_predictions, expected["reference_predictions"])
    if sample_ids != dataset_sample_ids(dataset_bytes, scenario.dataset_id):
        raise ValueError("inference sample IDs do not match frozen dataset manifest")
    measured = measured_max_error(native_bytes, reference_bytes, sample_ids)
    assert result.parity is not None and result.parity.max_absolute_error is not None
    if abs(measured - result.parity.max_absolute_error) > 1e-12:
        raise ValueError("parity claim does not match measured native/reference predictions")
    if measured > scenario.parity_tolerance:
        raise ValueError("measured parity exceeds scenario tolerance")
    if _hash_file(scenario_file) != hashlib.sha256(scenario_bytes).hexdigest():
        raise ValueError("scenario changed during integrity verification")
    if _hash_file(result_file) != hashlib.sha256(result_bytes).hexdigest():
        raise ValueError("result changed during integrity verification")
    if any(_hash_file(getattr(files, name)) != digest for name, digest in expected.items()):
        raise ValueError("evidence changed during integrity verification")
    return NativeIntegrityReport(
        status="integrity_verified", native_provenance="unverified",
        scenario_sha256=hashlib.sha256(scenario_bytes).hexdigest(),
        result_sha256=hashlib.sha256(result_bytes).hexdigest(),
        sample_count=len(sample_ids), measured_max_absolute_error=measured,
    )


def publish_completed_result(
    scenario_file: Path, result_file: Path, files: NativeEvidenceFiles, output_file: Path,
) -> Path:
    """Refuse publication until a controlled native runner provides provenance."""
    verify_completed_result(scenario_file, result_file, files)
    input_paths = {scenario_file.resolve(), result_file.resolve()}
    input_paths.update(getattr(files, field.name).resolve() for field in fields(NativeEvidenceFiles))
    if output_file.resolve() in input_paths:
        raise ValueError("publication output must differ from input and evidence files")
    raise RuntimeError("controlled native runner provenance is not yet implemented")
