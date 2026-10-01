from __future__ import annotations

import subprocess

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from projects.companion_x.experiments.edge_models.native_runner.contracts import (
    NativeRunResult,
    NativeScenario,
    NativeTarget,
    ParityEvidence,
    PreflightReport,
    ToolchainRequirement,
    build_preflight,
    scenario_digest,
    validate_result_for_scenario,
)
from projects.companion_x.experiments.edge_models.native_runner.probe import (
    ProbeDependencies,
    probe_host,
)

VALID_DIGEST = "a" * 64


def _scenario(**overrides: object) -> NativeScenario:
    values: dict[str, object] = {
        "schema_version": 1,
        "scenario_id": "edge-audio-ios-001",
        "run_id": "run-20260930-001",
        "target": NativeTarget.IOS_SIMULATOR,
        "device_name": "iPhone 16",
        "os_version": "iOS 18.0",
        "model_id": "tiny-audio-command-v1",
        "model_sha256": VALID_DIGEST,
        "dataset_id": "offline-command-eval-v1",
        "dataset_sha256": "b" * 64,
        "runtime": "coreml",
        "seed": 41,
        "parity_tolerance": 1e-5,
    }
    values.update(overrides)
    return NativeScenario.model_validate(values)


def _fake_run(stdout: str = "ok", stderr: str = ""):
    def run(argv, **_kwargs):
        command = tuple(argv)
        output = stdout
        if command == ("xcrun", "--find", "simctl"):
            output = "/Applications/Xcode.app/Contents/Developer/usr/bin/simctl"
        elif command == ("xcrun", "simctl", "list", "devices", "available"):
            output = "-- iOS 18.0 --\n    iPhone 16 (01234567-89AB-CDEF-0123-456789ABCDEF) (Shutdown)"
        elif command[0].endswith("/emulator/emulator") and command[1:] == ("-list-avds",):
            output = "Pixel_7_API_35"
        elif command[0].endswith("/platform-tools/adb") and command[1:] == ("version",):
            output = "Android Debug Bridge version 1.0.41"
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr=stderr)

    return run


def _add_avd_profile(home, *, avd_name: str, display_name: str, device_name: str, api: int):
    avd = home / f"{avd_name}.avd"
    avd.mkdir(parents=True)
    (avd / "config.ini").write_text(
        f"hw.device.name={device_name}\ntarget=android-{api}\n", encoding="utf-8"
    )
    (home / f"{avd_name}.ini").write_text(
        f"avd.ini.displayname={display_name}\n", encoding="utf-8"
    )


def _add_sdk_tools(sdk):
    for relative in ("platform-tools/adb", "emulator/emulator"):
        executable = sdk / relative
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)


def test_scenario_is_strict_versioned_and_normalizes_hashes():
    scenario = _scenario()
    assert scenario.schema_version == 1
    assert scenario.model_sha256 == VALID_DIGEST
    with pytest.raises(ValidationError):
        _scenario(schema_version=2)
    with pytest.raises(ValidationError):
        _scenario(unreviewed_field="not allowed")
    with pytest.raises(ValidationError):
        _scenario(dataset_sha256="not-a-hash")


def test_preflight_reports_toolchain_readiness_without_claiming_a_native_run():
    scenario = _scenario()
    report = build_preflight(
        scenario,
        host_platform="darwin",
        available_tools={"xcodebuild", "xcrun", "simctl"},
        simulator_available=True,
        android_sdk_configured=False,
    )
    assert report.status == "ready"
    assert report.scenario_id == scenario.scenario_id
    assert report.native_run_performed is False
    assert report.requirements
    assert all(req.available for req in report.requirements)


@pytest.mark.parametrize(
    ("status", "requirements"),
    [
        ("ready", (ToolchainRequirement(name="xcodebuild", available=False, detail="missing"),)),
        ("blocked", (ToolchainRequirement(name="xcodebuild", available=True, detail="present"),)),
    ],
)
def test_preflight_report_rejects_status_inconsistent_with_requirements(status, requirements):
    with pytest.raises(ValidationError, match="status must be"):
        PreflightReport(
            scenario_id="edge-audio-ios-001",
            target=NativeTarget.IOS_SIMULATOR,
            status=status,
            requirements=requirements,
            planned_commands=("xcodebuild -version",),
        )


def test_preflight_distinguishes_missing_toolchain_from_compatibility():
    scenario = _scenario(target=NativeTarget.ANDROID_EMULATOR, runtime="tflite")
    report = build_preflight(
        scenario,
        host_platform="darwin",
        available_tools={"adb"},
        simulator_available=None,
        android_sdk_configured=False,
    )
    assert report.status == "blocked"
    assert report.native_run_performed is False
    assert any(not req.available for req in report.requirements)
    assert "compatibility" in report.scope_note.lower()
    assert report.blocked_reasons


def test_ios_host_probe_reports_absent_tools_as_preflight_only():
    output = probe_host(
        _scenario(),
        deps=ProbeDependencies(which=lambda _name: None, run=_fake_run(), host_platform="darwin", environ={}),
    )
    assert output.preflight.status == "blocked"
    assert output.result.status == "preflight_only"
    assert output.result.native_artifact_sha256 is None
    assert {"xcodebuild", "xcrun", "simctl", "requested simulator device and OS"}.issubset(
        {reason.split(":", 1)[0] for reason in output.preflight.blocked_reasons}
    )


def test_ios_host_probe_reports_partial_xcode_install_without_simulator():
    paths = {"xcodebuild": "/fake/xcodebuild", "xcrun": "/fake/xcrun"}

    def run_without_simulator(argv, **_kwargs):
        result = _fake_run()(argv, **_kwargs)
        if tuple(argv) == ("xcrun", "simctl", "list", "devices", "available"):
            return subprocess.CompletedProcess(argv, 0, stdout="-- iOS 18.0 --\n", stderr="")
        return result

    output = probe_host(
        _scenario(),
        deps=ProbeDependencies(
            which=lambda name: paths.get(name),
            run=run_without_simulator,
            host_platform="darwin",
            environ={},
        ),
    )
    by_name = {item.name: item.available for item in output.preflight.requirements}
    assert by_name["xcodebuild"] and by_name["xcrun"] and by_name["simctl"]
    assert not by_name["requested simulator device and OS"]
    assert output.preflight.status == "blocked"
    assert len(output.preflight.blocked_reasons) == 1


def test_ios_host_probe_reports_available_toolchain_but_only_preflight_evidence():
    paths = {name: f"/fake/{name}" for name in ("xcodebuild", "xcrun")}
    output = probe_host(
        _scenario(),
        deps=ProbeDependencies(
            which=lambda name: paths.get(name),
            run=_fake_run(),
            host_platform="darwin",
            environ={},
        ),
    )
    assert output.preflight.status == "ready"
    assert output.preflight.blocked_reasons == ()
    assert output.result.status == "preflight_only"
    assert output.result.parity is None
    assert output.result.runtime_version is None
    assert output.result.native_artifact_sha256 is None


def test_ios_host_probe_rejects_a_different_requested_device_and_runtime():
    scenario = _scenario(device_name="iPhone 99", os_version="iOS 99.0")
    paths = {name: f"/fake/{name}" for name in ("xcodebuild", "xcrun")}
    output = probe_host(
        scenario,
        deps=ProbeDependencies(
            which=lambda name: paths.get(name),
            run=_fake_run(),
            host_platform="darwin",
            environ={},
        ),
    )
    failed = {item.name for item in output.preflight.requirements if not item.available}
    assert failed == {"requested simulator device and OS"}
    assert "iPhone 99" in output.preflight.blocked_reasons[0]
    assert "iOS 99.0" in output.preflight.blocked_reasons[0]
    assert output.preflight.status == "blocked"
    assert output.result.status == "preflight_only"


def test_android_host_probe_checks_java_sdk_adb_emulator_and_avd(tmp_path):
    scenario = _scenario(
        target=NativeTarget.ANDROID_EMULATOR,
        runtime="tflite",
        device_name="Pixel 7",
        os_version="Android 15",
    )
    sdk = tmp_path / "sdk"
    for relative in ("platform-tools", "emulator", "platforms/android-35"):
        (sdk / relative).mkdir(parents=True)
    _add_sdk_tools(sdk)
    avd_home = tmp_path / "avds"
    _add_avd_profile(
        avd_home,
        avd_name="Pixel_7_API_35",
        display_name="Pixel 7",
        device_name="pixel_7",
        api=35,
    )
    paths = {name: f"/fake/{name}" for name in ("java", "adb", "emulator")}
    deps = ProbeDependencies(
        which=lambda name: paths.get(name),
        run=_fake_run(stderr='openjdk version "21"'),
        host_platform="linux",
        environ={"ANDROID_SDK_ROOT": str(sdk)},
        avd_home=avd_home,
    )
    output = probe_host(scenario, deps=deps)
    assert output.preflight.status == "ready"
    assert all(item.available for item in output.preflight.requirements)
    assert output.result.status == "preflight_only"


def test_android_host_probe_reports_partial_toolchain_and_explicit_reasons(tmp_path):
    scenario = _scenario(
        target=NativeTarget.ANDROID_EMULATOR,
        runtime="tflite",
        device_name="Pixel 7",
        os_version="Android 15",
    )
    sdk = tmp_path / "missing-sdk"
    paths = {"adb": "/fake/adb"}
    output = probe_host(
        scenario,
        deps=ProbeDependencies(
            which=lambda name: paths.get(name),
            run=_fake_run(),
            host_platform="linux",
            environ={"ANDROID_SDK_ROOT": str(sdk)},
        ),
    )
    failed = {item.name for item in output.preflight.requirements if not item.available}
    assert {"Android SDK configuration", "java", "emulator", "requested Android device and OS"} <= failed
    assert output.preflight.status == "blocked"
    assert len(output.preflight.blocked_reasons) == len(failed)
    assert output.result.status == "preflight_only"


def test_android_host_probe_ignores_unrelated_path_tools_when_sdk_binaries_are_missing(tmp_path):
    scenario = _scenario(
        target=NativeTarget.ANDROID_EMULATOR,
        runtime="tflite",
        device_name="Pixel 7",
        os_version="Android 15",
    )
    sdk = tmp_path / "sdk"
    for relative in ("platform-tools", "emulator", "platforms/android-35"):
        (sdk / relative).mkdir(parents=True)
    avd_home = tmp_path / "avds"
    _add_avd_profile(
        avd_home,
        avd_name="Pixel_7_API_35",
        display_name="Pixel 7",
        device_name="pixel_7",
        api=35,
    )
    unrelated_path_tools = {name: f"/other/sdk/{name}" for name in ("adb", "emulator", "java")}
    output = probe_host(
        scenario,
        deps=ProbeDependencies(
            which=lambda name: unrelated_path_tools.get(name),
            run=_fake_run(stderr='openjdk version "21"'),
            host_platform="linux",
            environ={"ANDROID_SDK_ROOT": str(sdk)},
            avd_home=avd_home,
        ),
    )
    by_name = {item.name: item.available for item in output.preflight.requirements}
    assert by_name["Android SDK configuration"]
    assert by_name["java"]
    assert not by_name["adb"]
    assert not by_name["emulator"]
    assert not by_name["requested Android device and OS"]
    assert output.preflight.status == "blocked"
    assert output.result.status == "preflight_only"


def test_android_host_probe_rejects_avd_with_wrong_device_and_os(tmp_path):
    scenario = _scenario(
        target=NativeTarget.ANDROID_EMULATOR,
        runtime="tflite",
        device_name="Pixel 7",
        os_version="Android 15",
    )
    sdk = tmp_path / "sdk"
    for relative in ("platform-tools", "emulator", "platforms/android-35"):
        (sdk / relative).mkdir(parents=True)
    _add_sdk_tools(sdk)
    avd_home = tmp_path / "avds"
    _add_avd_profile(
        avd_home,
        avd_name="Pixel_6_API_34",
        display_name="Pixel 6",
        device_name="pixel_6",
        api=34,
    )
    paths = {name: f"/fake/{name}" for name in ("java", "adb", "emulator")}
    output = probe_host(
        scenario,
        deps=ProbeDependencies(
            which=lambda name: paths.get(name),
            run=_fake_run(stderr='openjdk version "21"'),
            host_platform="linux",
            environ={"ANDROID_SDK_ROOT": str(sdk)},
            avd_home=avd_home,
        ),
    )
    by_name = {item.name: item.available for item in output.preflight.requirements}
    assert by_name["emulator"]
    assert not by_name["requested Android device and OS"]
    assert output.preflight.status == "blocked"
    assert output.result.status == "preflight_only"


def test_android_host_probe_does_not_treat_avd_labels_as_hardware_identity(tmp_path):
    scenario = _scenario(
        target=NativeTarget.ANDROID_EMULATOR,
        runtime="tflite",
        device_name="Pixel 7",
        os_version="Android 15",
    )
    sdk = tmp_path / "sdk"
    for relative in ("platform-tools", "emulator", "platforms/android-35"):
        (sdk / relative).mkdir(parents=True)
    _add_sdk_tools(sdk)
    avd_home = tmp_path / "avds"
    _add_avd_profile(
        avd_home,
        avd_name="Pixel_7_API_35",
        display_name="Pixel 7",
        device_name="pixel_6",
        api=35,
    )
    paths = {name: f"/fake/{name}" for name in ("java", "adb", "emulator")}

    output = probe_host(
        scenario,
        deps=ProbeDependencies(
            which=lambda name: paths.get(name),
            run=_fake_run(stderr='openjdk version "21"'),
            host_platform="linux",
            environ={"ANDROID_SDK_ROOT": str(sdk)},
            avd_home=avd_home,
        ),
    )

    by_name = {item.name: item.available for item in output.preflight.requirements}
    assert by_name["emulator"]
    assert not by_name["requested Android device and OS"]
    assert output.preflight.status == "blocked"
    assert output.result.status == "preflight_only"


def test_android_host_probe_blocks_name_only_avd_profiles(tmp_path):
    scenario = _scenario(
        target=NativeTarget.ANDROID_EMULATOR,
        runtime="tflite",
        device_name="Pixel 7",
        os_version="Android 15",
    )
    sdk = tmp_path / "sdk"
    for relative in ("platform-tools", "emulator", "platforms/android-35"):
        (sdk / relative).mkdir(parents=True)
    _add_sdk_tools(sdk)
    avd_home = tmp_path / "avds"
    avd = avd_home / "Pixel_7_API_35.avd"
    avd.mkdir(parents=True)
    (avd / "config.ini").write_text("target=android-35\n", encoding="utf-8")
    (avd_home / "Pixel_7_API_35.ini").write_text(
        "avd.ini.displayname=Pixel 7\n", encoding="utf-8"
    )
    paths = {name: f"/fake/{name}" for name in ("java", "adb", "emulator")}

    output = probe_host(
        scenario,
        deps=ProbeDependencies(
            which=lambda name: paths.get(name),
            run=_fake_run(stderr='openjdk version "21"'),
            host_platform="linux",
            environ={"ANDROID_SDK_ROOT": str(sdk)},
            avd_home=avd_home,
        ),
    )

    by_name = {item.name: item.available for item in output.preflight.requirements}
    assert by_name["emulator"]
    assert not by_name["requested Android device and OS"]
    assert output.preflight.status == "blocked"
    assert output.result.status == "preflight_only"


def _completed_payload(scenario: NativeScenario | None = None) -> dict[str, object]:
    scenario = scenario or _scenario()
    return {
        "schema_version": 2,
        "result_id": "result-20260930-001",
        "scenario_id": scenario.scenario_id,
        "scenario_sha256": scenario_digest(scenario),
        "target": scenario.target,
        "status": "completed",
        "model_sha256": scenario.model_sha256,
        "dataset_sha256": scenario.dataset_sha256,
        "runtime_version": "Core ML 8",
        "native_artifact_sha256": "c" * 64,
        "parity": {"sample_count": 10, "max_absolute_error": 0.000001},
        "execution": {
            "observed": {
                "run_id": scenario.run_id,
                "device_name": scenario.device_name,
                "os_version": scenario.os_version,
                "runtime": scenario.runtime,
                "model_id": scenario.model_id,
                "dataset_id": scenario.dataset_id,
            },
            "app_build": {
                "app_id": "com.ditto.edge", "version": "1.0", "build_id": "100",
                "artifact_sha256": "c" * 64,
            },
            "ditto_sdk_version": "4.12.0",
            "ditto_sdk_package_sha256": "f" * 64,
            "device_runtime": {
                "target": scenario.target,
                "name": "iOS Simulator",
                "runtime_id": "com.apple.CoreSimulator.SimRuntime.iOS-18-0",
                "device_name": scenario.device_name,
                "os_version": scenario.os_version,
                "manifest_sha256": "9" * 64,
            },
            "loaded_model": {
                "model_id": scenario.model_id,
                "sha256": scenario.model_sha256,
                "runtime": scenario.runtime,
            },
            "inference_count": 10,
            "cloud_disabled": True,
            "writer": {
                "peer_id": "writer-1", "initial_session_id": "writer-session-1",
                "reopen_session_id": "writer-session-2",
            },
            "peer": {
                "peer_id": "peer-2", "initial_session_id": "peer-session-1",
                "reopen_session_id": "peer-session-2",
            },
            "observation_sha256": "d" * 64,
            "persistence_readback_sha256": "d" * 64,
            "peer_readback_sha256": "d" * 64,
            "event_trace_sha256": "e" * 64,
            "native_predictions_sha256": "1" * 64,
            "reference_predictions_sha256": "2" * 64,
        },
    }


def test_v1_completed_cannot_pass_as_native_evidence():
    payload = _completed_payload()
    payload["schema_version"] = 1
    with pytest.raises(ValidationError, match="schema version 2"):
        NativeRunResult.model_validate(payload)


def test_v2_completed_result_matches_frozen_scenario_and_round_trips():
    scenario = _scenario()
    result = NativeRunResult.model_validate(_completed_payload(scenario))
    validate_result_for_scenario(result, scenario)
    reparsed = NativeRunResult.model_validate_json(result.model_dump_json())
    assert reparsed == result


@pytest.mark.parametrize(
    "missing",
    [
        "observed", "app_build", "ditto_sdk_version", "ditto_sdk_package_sha256",
        "device_runtime",
        "loaded_model", "inference_count", "cloud_disabled", "writer", "peer",
        "observation_sha256", "persistence_readback_sha256", "peer_readback_sha256",
        "event_trace_sha256", "native_predictions_sha256",
        "reference_predictions_sha256",
    ],
)
def test_completed_result_requires_each_native_execution_boundary(missing):
    payload = _completed_payload()
    del payload["execution"][missing]
    with pytest.raises(ValidationError, match=missing):
        NativeRunResult.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("app_build", "build_id"), " "),
        (("app_build", "artifact_sha256"), "not-a-digest"),
        (("ditto_sdk_version",), " "),
        (("ditto_sdk_package_sha256",), "not-a-digest"),
        (("device_runtime", "name"), " "),
        (("device_runtime", "runtime_id"), " "),
        (("device_runtime", "manifest_sha256"), "not-a-digest"),
        (("loaded_model", "sha256"), "not-a-digest"),
        (("inference_count",), 0),
        (("cloud_disabled",), False),
        (("event_trace_sha256",), "not-a-digest"),
        (("native_predictions_sha256",), "not-a-digest"),
        (("reference_predictions_sha256",), "not-a-digest"),
    ],
)
def test_completed_result_rejects_invalid_native_evidence(path, value):
    payload = _completed_payload()
    field = payload["execution"]
    for part in path[:-1]:
        field = field[part]
    field[path[-1]] = value
    with pytest.raises(ValidationError):
        NativeRunResult.model_validate(payload)


@pytest.mark.parametrize(
    "path",
    [
        ("app_build", "artifact_sha256"),
        ("device_runtime", "manifest_sha256"),
        ("ditto_sdk_package_sha256",),
        ("native_predictions_sha256",),
        ("reference_predictions_sha256",),
    ],
)
def test_completed_result_requires_artifact_digests(path):
    payload = _completed_payload()
    field = payload["execution"]
    for part in path[:-1]:
        field = field[part]
    del field[path[-1]]
    with pytest.raises(ValidationError, match=path[-1]):
        NativeRunResult.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("app_build", "artifact_sha256"), "8" * 64, "app build artifact hash"),
        (("device_runtime", "target"), NativeTarget.ANDROID_EMULATOR, "runtime target"),
        (("loaded_model", "sha256"), "8" * 64, "loaded model hash"),
        (("loaded_model", "model_id"), "other-model", "loaded model ID"),
        (("loaded_model", "runtime"), "onnxruntime", "loaded model runtime"),
        (("device_runtime", "device_name"), "iPhone 15", "runtime device_name"),
        (("device_runtime", "os_version"), "iOS 17.0", "runtime os_version"),
    ],
)
def test_completed_result_rejects_internal_identity_conflicts(path, value, message):
    payload = _completed_payload()
    payload["execution"][path[0]][path[1]] = value
    with pytest.raises(ValidationError, match=message):
        NativeRunResult.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("peer", "peer_id"), "writer-1", "peer IDs"),
        (("writer", "reopen_session_id"), "writer-session-1", "session IDs"),
        (("peer", "initial_session_id"), "writer-session-1", "session IDs"),
        (("persistence_readback_sha256",), "f" * 64, "readback hashes"),
        (("peer_readback_sha256",), "f" * 64, "readback hashes"),
    ],
)
def test_completed_result_requires_distinct_sessions_and_matching_readbacks(path, value, message):
    payload = _completed_payload()
    field = payload["execution"]
    for part in path[:-1]:
        field = field[part]
    field[path[-1]] = value
    with pytest.raises(ValidationError, match=message):
        NativeRunResult.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", "other-run"), ("device_name", "iPhone 15"),
        ("os_version", "iOS 17.0"), ("runtime", "onnxruntime"),
        ("model_id", "other-model"), ("dataset_id", "other-dataset"),
    ],
)
def test_completed_observation_must_match_frozen_scenario(field, value):
    scenario = _scenario()
    payload = _completed_payload(scenario)
    payload["execution"]["observed"][field] = value
    if field in {"device_name", "os_version"}:
        payload["execution"]["device_runtime"][field] = value
    elif field in {"model_id", "runtime"}:
        payload["execution"]["loaded_model"][field] = value
    result = NativeRunResult.model_validate(payload)
    with pytest.raises(ValueError, match=f"observed {field}"):
        validate_result_for_scenario(result, scenario)


def test_result_must_match_scenario_identity_and_artifact_hashes():
    scenario = _scenario()
    result = NativeRunResult.model_validate(_completed_payload(scenario))
    for field, value in (("scenario_id", "other-id"), ("scenario_sha256", "f" * 64),
                         ("model_sha256", "f" * 64), ("dataset_sha256", "f" * 64)):
        with pytest.raises(ValueError, match=field):
            validate_result_for_scenario(result.model_copy(update={field: value}), scenario)


def test_completed_result_requires_measured_parity_and_inference_alignment():
    for parity in (None, {"sample_count": 0, "max_absolute_error": None},
                   {"sample_count": 9, "max_absolute_error": 0.0}):
        payload = _completed_payload()
        payload["parity"] = parity
        with pytest.raises(ValidationError, match="parity"):
            NativeRunResult.model_validate(payload)


def test_completed_result_must_meet_the_frozen_parity_tolerance():
    scenario = _scenario(parity_tolerance=1e-6)
    payload = _completed_payload(scenario)
    payload["parity"]["max_absolute_error"] = 2e-6
    with pytest.raises(ValueError, match="exceeds scenario tolerance"):
        validate_result_for_scenario(NativeRunResult.model_validate(payload), scenario)


def test_preflight_result_cannot_carry_native_run_evidence():
    with pytest.raises(ValidationError, match="cannot contain native-run evidence"):
        NativeRunResult(
            schema_version=1,
            result_id="result-20260930-001",
            scenario_id="edge-audio-ios-001",
            scenario_sha256=VALID_DIGEST,
            target=NativeTarget.IOS_SIMULATOR,
            status="preflight_only",
            model_sha256=VALID_DIGEST,
            dataset_sha256="b" * 64,
            runtime_version="Core ML 8",
            native_artifact_sha256="c" * 64,
            parity=ParityEvidence(sample_count=1, max_absolute_error=0.0),
        )


@given(st.sampled_from([" ", "\t", "\n", "  "]))
def test_blank_identifiers_are_rejected(identifier: str):
    with pytest.raises(ValidationError):
        _scenario(scenario_id=identifier)


@given(st.text(alphabet="0123456789abcdef", min_size=64, max_size=64))
def test_any_sha256_hex_digest_is_accepted(digest: str):
    assert _scenario(model_sha256=digest).model_sha256 == digest


def test_scenario_digest_is_canonical():
    first = _scenario()
    second = NativeScenario.model_validate(first.model_dump())
    assert scenario_digest(first) == scenario_digest(second)
