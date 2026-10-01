"""Versioned contracts for native mobile experiment planning and evidence.

A successful preflight reports host/tool availability only. It is never evidence
that a packaged model ran or is compatible with an iOS/Android runtime.
"""
from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class NativeTarget(StrEnum):
    IOS_SIMULATOR = "ios_simulator"
    ANDROID_EMULATOR = "android_emulator"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class NativeScenario(StrictContract):
    """Immutable inputs and comparison policy for one native compatibility run."""

    schema_version: Literal[1]
    scenario_id: str
    run_id: str
    target: NativeTarget
    device_name: str = Field(min_length=1, max_length=120)
    os_version: str = Field(min_length=1, max_length=80)
    model_id: str
    model_sha256: str
    dataset_id: str
    dataset_sha256: str
    runtime: str
    seed: int = Field(ge=0)
    parity_tolerance: float = Field(ge=0, le=1)

    @field_validator("scenario_id", "run_id", "model_id", "dataset_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("must be a lowercase kebab-case identifier")
        return value

    @field_validator("model_sha256", "dataset_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return value

    @model_validator(mode="after")
    def runtime_matches_target(self) -> NativeScenario:
        allowed = {
            NativeTarget.IOS_SIMULATOR: {"coreml", "onnxruntime", "fd001-native-linear"},
            NativeTarget.ANDROID_EMULATOR: {"tflite", "onnxruntime", "fd001-native-linear"},
        }
        if self.runtime not in allowed[self.target]:
            raise ValueError(f"runtime {self.runtime!r} is not supported by {self.target.value}")
        return self


class ToolchainRequirement(StrictContract):
    name: str
    available: bool
    detail: str


class PreflightReport(StrictContract):
    schema_version: Literal[1] = 1
    scenario_id: str
    target: NativeTarget
    status: Literal["ready", "blocked"]
    native_run_performed: Literal[False] = False
    requirements: tuple[ToolchainRequirement, ...] = Field(min_length=1)
    blocked_reasons: tuple[str, ...] = ()
    planned_commands: tuple[str, ...]
    scope_note: str = (
        "Preflight checks toolchain availability only; it does not run a native "
        "app, validate prediction parity, or establish device compatibility."
    )

    @model_validator(mode="after")
    def status_matches_requirements(self) -> PreflightReport:
        expected = "ready" if all(item.available for item in self.requirements) else "blocked"
        if self.status != expected:
            raise ValueError(f"status must be {expected!r} for the reported requirements")
        expected_reasons = tuple(
            f"{item.name}: {item.detail}" for item in self.requirements if not item.available
        )
        if self.blocked_reasons != expected_reasons:
            raise ValueError("blocked_reasons must identify every unavailable requirement")
        return self


class ParityEvidence(StrictContract):
    sample_count: int = Field(ge=0)
    max_absolute_error: float | None = Field(default=None, ge=0)


class ObservedScenario(StrictContract):
    run_id: NonBlankText
    device_name: NonBlankText
    os_version: NonBlankText
    runtime: NonBlankText
    model_id: NonBlankText
    dataset_id: NonBlankText


class NativeAppBuild(StrictContract):
    app_id: NonBlankText
    version: NonBlankText
    build_id: NonBlankText
    artifact_sha256: str

    @field_validator("artifact_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return value


class NativeRuntimeIdentity(StrictContract):
    target: NativeTarget
    name: NonBlankText
    runtime_id: NonBlankText
    device_name: NonBlankText
    os_version: NonBlankText
    manifest_sha256: str

    @field_validator("manifest_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return value


class LoadedModel(StrictContract):
    model_id: NonBlankText
    sha256: str
    runtime: NonBlankText

    @field_validator("sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return value


class PeerSessions(StrictContract):
    peer_id: NonBlankText
    initial_session_id: NonBlankText
    reopen_session_id: NonBlankText

    @model_validator(mode="after")
    def distinct_sessions(self) -> PeerSessions:
        if self.initial_session_id == self.reopen_session_id:
            raise ValueError("initial and reopen session IDs must differ")
        return self


class NativeExecutionEvidence(StrictContract):
    """Claimed observations; a host verifier must corroborate traces and artifacts."""

    observed: ObservedScenario
    app_build: NativeAppBuild
    ditto_sdk_version: NonBlankText
    ditto_sdk_package_sha256: str
    device_runtime: NativeRuntimeIdentity
    loaded_model: LoadedModel
    inference_count: int = Field(ge=1)
    cloud_disabled: Literal[True]
    writer: PeerSessions
    peer: PeerSessions
    observation_sha256: str
    persistence_readback_sha256: str
    peer_readback_sha256: str
    event_trace_sha256: str
    native_predictions_sha256: str
    reference_predictions_sha256: str

    @field_validator(
        "observation_sha256", "persistence_readback_sha256",
        "peer_readback_sha256", "event_trace_sha256", "ditto_sdk_package_sha256",
        "native_predictions_sha256", "reference_predictions_sha256",
    )
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return value

    @model_validator(mode="after")
    def readbacks_match_observation(self) -> NativeExecutionEvidence:
        if len({self.writer.peer_id, self.peer.peer_id}) != 2:
            raise ValueError("writer and peer IDs must differ")
        sessions = (
            self.writer.initial_session_id, self.writer.reopen_session_id,
            self.peer.initial_session_id, self.peer.reopen_session_id,
        )
        if len(set(sessions)) != len(sessions):
            raise ValueError("writer and peer session IDs must all differ")
        if len({self.observation_sha256, self.persistence_readback_sha256,
                self.peer_readback_sha256}) != 1:
            raise ValueError("observation and persistence/peer readback hashes must match")
        return self


class NativeRunResult(StrictContract):
    """Typed run claim; completed is untrusted until controlled native execution."""

    schema_version: Literal[1, 2]
    result_id: str
    scenario_id: str
    scenario_sha256: str
    target: NativeTarget
    status: Literal["preflight_only", "completed", "failed"]
    model_sha256: str
    dataset_sha256: str
    runtime_version: NonBlankText | None
    native_artifact_sha256: str | None
    parity: ParityEvidence | None
    execution: NativeExecutionEvidence | None = None

    @field_validator("result_id", "scenario_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("must be a lowercase kebab-case identifier")
        return value

    @field_validator("scenario_sha256", "model_sha256", "dataset_sha256", "native_artifact_sha256")
    @classmethod
    def validate_optional_digest(cls, value: str | None) -> str | None:
        if value is not None and not _SHA256.fullmatch(value):
            raise ValueError("must be a lowercase SHA-256 hex digest")
        return value

    @model_validator(mode="after")
    def enforce_evidence_by_status(self) -> NativeRunResult:
        if self.status == "completed":
            if self.schema_version != 2:
                raise ValueError("completed status requires schema version 2")
            if not self.runtime_version or self.native_artifact_sha256 is None:
                raise ValueError("completed status requires runtime version and native artifact hash")
            if self.parity is None or self.parity.sample_count < 1 or self.parity.max_absolute_error is None:
                raise ValueError("completed status requires measured parity evidence")
            if self.execution is None:
                raise ValueError("completed status requires native execution evidence")
            if self.parity.sample_count != self.execution.inference_count:
                raise ValueError("parity sample count must match inference count")
            execution = self.execution
            if execution.app_build.artifact_sha256 != self.native_artifact_sha256:
                raise ValueError("app build artifact hash must match native artifact hash")
            if execution.device_runtime.target != self.target:
                raise ValueError("device runtime target must match result target")
            if execution.loaded_model.sha256 != self.model_sha256:
                raise ValueError("loaded model hash must match result model hash")
            if execution.loaded_model.model_id != execution.observed.model_id:
                raise ValueError("loaded model ID must match observed model ID")
            if execution.loaded_model.runtime != execution.observed.runtime:
                raise ValueError("loaded model runtime must match observed runtime")
            for field in ("device_name", "os_version"):
                if getattr(execution.device_runtime, field) != getattr(execution.observed, field):
                    raise ValueError(f"device runtime {field} must match observed {field}")
        elif self.status == "preflight_only":
            if any((self.runtime_version, self.native_artifact_sha256, self.parity, self.execution)):
                raise ValueError("preflight_only status cannot contain native-run evidence")
        elif self.execution is not None:
            raise ValueError("failed status cannot claim completed native execution evidence")
        return self


class NativePreflightOutput(StrictContract):
    """Strict CLI output joining toolchain checks to an explicitly non-run result."""

    preflight: PreflightReport
    result: NativeRunResult

    @model_validator(mode="after")
    def result_matches_preflight(self) -> NativePreflightOutput:
        if self.result.status != "preflight_only":
            raise ValueError("host probes may only emit preflight_only results")
        if self.result.native_artifact_sha256 is not None or self.result.parity is not None:
            raise ValueError("host probes cannot emit native execution evidence")
        if (
            self.result.scenario_id != self.preflight.scenario_id
            or self.result.target != self.preflight.target
        ):
            raise ValueError("preflight result must match its report")
        return self


def scenario_digest(scenario: NativeScenario) -> str:
    """Return SHA-256 over a canonical JSON representation of the scenario."""
    canonical = json.dumps(scenario.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_result_for_scenario(result: NativeRunResult, scenario: NativeScenario) -> None:
    """Reject result envelopes that are detached from their frozen scenario."""
    expected = {
        "scenario_id": scenario.scenario_id,
        "scenario_sha256": scenario_digest(scenario),
        "target": scenario.target,
        "model_sha256": scenario.model_sha256,
        "dataset_sha256": scenario.dataset_sha256,
    }
    for field, value in expected.items():
        if getattr(result, field) != value:
            raise ValueError(f"result {field} does not match the scenario")
    if result.status == "completed":
        assert result.parity is not None
        assert result.parity.max_absolute_error is not None
        assert result.execution is not None
        observed = result.execution.observed
        for field in ("run_id", "device_name", "os_version", "runtime", "model_id", "dataset_id"):
            if getattr(observed, field) != getattr(scenario, field):
                raise ValueError(f"observed {field} does not match the scenario")
        runtime = result.execution.device_runtime
        if runtime.target != scenario.target:
            raise ValueError("device runtime target does not match the scenario")
        for field in ("device_name", "os_version"):
            if getattr(runtime, field) != getattr(scenario, field):
                raise ValueError(f"device runtime {field} does not match the scenario")
        loaded = result.execution.loaded_model
        if loaded.model_id != scenario.model_id or loaded.sha256 != scenario.model_sha256:
            raise ValueError("loaded model does not match the scenario")
        if loaded.runtime != scenario.runtime:
            raise ValueError("loaded model runtime does not match the scenario")
        if result.parity.max_absolute_error > scenario.parity_tolerance:
            raise ValueError("result parity error exceeds scenario tolerance")


def build_preflight(
    scenario: NativeScenario,
    *,
    host_platform: str,
    available_tools: set[str],
    simulator_available: bool | None,
    android_sdk_configured: bool,
) -> PreflightReport:
    """Build a pure, repeatable toolchain preflight from an observed host snapshot."""
    if scenario.target is NativeTarget.IOS_SIMULATOR:
        checks = (
            ("macOS host", host_platform == "darwin", f"host platform: {host_platform}"),
            ("xcodebuild", "xcodebuild" in available_tools, "xcodebuild is missing or did not pass its version probe"),
            ("xcrun", "xcrun" in available_tools, "xcrun is missing or did not pass its simulator probe"),
            ("simctl", "simctl" in available_tools, "xcrun could not find or run simctl"),
            ("requested simulator device and OS", simulator_available is True, f"no available simulator matches {scenario.device_name!r} on {scenario.os_version!r}"),
        )
        commands = ("xcodebuild -version", "xcrun simctl list devices available")
    else:
        checks = (
            ("Android SDK configuration", android_sdk_configured, "ANDROID_SDK_ROOT/ANDROID_HOME is unset or does not name an SDK directory"),
            ("java", "java" in available_tools, "java is missing or did not pass its version probe"),
            ("adb", "adb" in available_tools, "adb is missing or did not pass its version probe"),
            ("emulator", "emulator" in available_tools, "emulator is missing or did not pass its AVD probe"),
            ("requested Android device and OS", simulator_available is True, f"no listed AVD matches {scenario.device_name!r} on {scenario.os_version!r}"),
        )
        commands = ("adb version", "emulator -list-avds")
    requirements = tuple(
        ToolchainRequirement(name=name, available=available, detail=detail)
        for name, available, detail in checks
    )
    blocked_reasons = tuple(
        f"{item.name}: {item.detail}" for item in requirements if not item.available
    )
    return PreflightReport(
        scenario_id=scenario.scenario_id,
        target=scenario.target,
        status="ready" if all(item.available for item in requirements) else "blocked",
        requirements=requirements,
        blocked_reasons=blocked_reasons,
        planned_commands=commands,
    )
