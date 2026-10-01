"""Synthetic fixtures exercise host verification; they are not native-run evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from projects.companion_x.experiments.edge_models.native_runner.contracts import (
    NativeRunResult, NativeScenario, NativeTarget, scenario_digest,
)
from projects.companion_x.experiments.edge_models.native_runner.verify import (
    NativeEvidenceFiles, publish_completed_result, verify_completed_result,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(
    tmp_path: Path, target: NativeTarget = NativeTarget.IOS_SIMULATOR,
) -> tuple[Path, Path, NativeEvidenceFiles, Path]:
    ios = target is NativeTarget.IOS_SIMULATOR
    scenario = NativeScenario(
        schema_version=1, scenario_id="native-ios-001" if ios else "native-android-001",
        run_id="run-ios-001" if ios else "run-android-001", target=target,
        device_name="iPhone 16" if ios else "Pixel 7",
        os_version="iOS 18.0" if ios else "Android 15",
        model_id="tiny-audio-v1", model_sha256="a" * 64,
        dataset_id="audio-eval-v1", dataset_sha256="b" * 64,
        runtime="coreml" if ios else "tflite", seed=7, parity_tolerance=1e-5,
    )
    paths = {name: tmp_path / name for name in NativeEvidenceFiles.__dataclass_fields__}
    for name in paths:
        if name not in {"event_trace", "observation", "persistence_readback", "peer_readback",
                        "native_predictions", "reference_predictions", "dataset"}:
            paths[name].write_bytes(f"synthetic {name} fixture".encode())
    paths["dataset"].write_text(json.dumps({
        "schema_version": 1, "dataset_id": scenario.dataset_id, "split": "test",
        "samples": [
            {"sample_id": "sample-1", "sha256": "1" * 64},
            {"sample_id": "sample-2", "sha256": "2" * 64},
        ],
    }), encoding="utf-8")
    # Frozen scenario digests are derived from the actual fixture files.
    scenario = scenario.model_copy(update={
        "model_sha256": _sha(paths["loaded_model"]),
        "dataset_sha256": _sha(paths["dataset"]),
    })
    observation = b'{"alert":true,"source":"writer"}\n'
    for name in ("observation", "persistence_readback", "peer_readback"):
        paths[name].write_bytes(observation)
    predictions = {"schema_version": 1, "predictions": [
        {"sample_id": "sample-1", "score": 0.25},
        {"sample_id": "sample-2", "score": 0.75},
    ]}
    for name in ("native_predictions", "reference_predictions"):
        paths[name].write_text(json.dumps(predictions), encoding="utf-8")
    digest = _sha(paths["observation"])
    run = scenario.run_id

    def event(kind: str, peer: str, session: str, **payload: object) -> dict[str, object]:
        return {"event": kind, "run_id": run, "peer_id": peer,
                "session_id": session, **payload}

    events = [
        event("ditto_started", "writer", "writer-0", sdk_version="4.12.0", cloud_disabled=True),
        event("ditto_started", "peer", "peer-0", sdk_version="4.12.0", cloud_disabled=True),
        event("model_loaded", "writer", "writer-0", model_id=scenario.model_id,
              model_sha256=scenario.model_sha256),
        event("inference", "writer", "writer-0", sample_id="sample-1"),
        event("inference", "writer", "writer-0", sample_id="sample-2"),
        event("observation_written", "writer", "writer-0", observation_sha256=digest),
        event("peer_observed", "peer", "peer-0", observation_sha256=digest),
        event("writer_reopened", "writer", "writer-1"),
        event("persistence_readback", "writer", "writer-1", observation_sha256=digest),
        event("peer_reopened", "peer", "peer-1"),
        event("peer_readback", "peer", "peer-1", observation_sha256=digest),
    ]
    paths["event_trace"].write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in events), encoding="utf-8"
    )
    files = NativeEvidenceFiles(**paths)
    result = NativeRunResult.model_validate({
        "schema_version": 2, "result_id": "result-ios-001" if ios else "result-android-001",
        "scenario_id": scenario.scenario_id, "scenario_sha256": scenario_digest(scenario),
        "target": scenario.target, "status": "completed",
        "model_sha256": scenario.model_sha256, "dataset_sha256": scenario.dataset_sha256,
        "runtime_version": "Core ML 8" if ios else "TFLite 2.17",
        "native_artifact_sha256": _sha(files.app_build),
        "parity": {"sample_count": 2, "max_absolute_error": 0.0},
        "execution": {
            "observed": {name: getattr(scenario, name) for name in
                         ("run_id", "device_name", "os_version", "runtime", "model_id", "dataset_id")},
            "app_build": {"app_id": "com.ditto.edge", "version": "1.0", "build_id": "1",
                          "artifact_sha256": _sha(files.app_build)},
            "ditto_sdk_version": "4.12.0",
            "ditto_sdk_package_sha256": _sha(files.ditto_sdk_package),
            "device_runtime": {"target": scenario.target,
                               "name": "iOS Simulator" if ios else "Android Emulator",
                               "runtime_id": "iOS-18-0" if ios else "android-35",
                               "device_name": scenario.device_name,
                               "os_version": scenario.os_version,
                               "manifest_sha256": _sha(files.device_runtime_manifest)},
            "loaded_model": {"model_id": scenario.model_id,
                             "sha256": scenario.model_sha256, "runtime": scenario.runtime},
            "inference_count": 2, "cloud_disabled": True,
            "writer": {"peer_id": "writer", "initial_session_id": "writer-0",
                       "reopen_session_id": "writer-1"},
            "peer": {"peer_id": "peer", "initial_session_id": "peer-0",
                     "reopen_session_id": "peer-1"},
            "observation_sha256": digest, "persistence_readback_sha256": digest,
            "peer_readback_sha256": digest, "event_trace_sha256": _sha(files.event_trace),
            "native_predictions_sha256": _sha(files.native_predictions),
            "reference_predictions_sha256": _sha(files.reference_predictions),
        },
    })
    scenario_path = tmp_path / "scenario.json"
    result_path = tmp_path / "result.json"
    scenario_path.write_text(scenario.model_dump_json(), encoding="utf-8")
    result_path.write_text(result.model_dump_json(), encoding="utf-8")
    return scenario_path, result_path, files, tmp_path / "published.json"


@pytest.mark.parametrize("target", [NativeTarget.IOS_SIMULATOR, NativeTarget.ANDROID_EMULATOR])
def test_coherent_host_evidence_is_integrity_checked_but_cannot_publish_native_completion(tmp_path, target):
    scenario, result, files, published = _evidence(tmp_path, target)
    verified = verify_completed_result(scenario, result, files)
    assert verified.status == "integrity_verified"
    assert verified.native_provenance == "unverified"
    assert verified.sample_count == 2
    with pytest.raises(RuntimeError, match="controlled native runner"):
        publish_completed_result(scenario, result, files, published)
    assert not published.exists()


def test_trace_samples_must_match_frozen_dataset_manifest(tmp_path):
    scenario, result, files, _ = _evidence(tmp_path)
    dataset = json.loads(files.dataset.read_text())
    dataset["samples"][1]["sample_id"] = "unrelated"
    files.dataset.write_text(json.dumps(dataset))
    claim = json.loads(result.read_text())
    frozen = json.loads(scenario.read_text())
    frozen["dataset_sha256"] = _sha(files.dataset)
    scenario.write_text(json.dumps(frozen))
    claim["dataset_sha256"] = frozen["dataset_sha256"]
    claim["scenario_sha256"] = scenario_digest(NativeScenario.model_validate_json(scenario.read_text()))
    result.write_text(json.dumps(claim))
    with pytest.raises(ValueError, match="frozen dataset manifest"):
        verify_completed_result(scenario, result, files)


def test_claimed_parity_requires_measured_native_and_reference_predictions(tmp_path):
    scenario, result, files, published = _evidence(tmp_path)
    native = json.loads(files.native_predictions.read_text())
    native["predictions"][0]["score"] = 0.26
    files.native_predictions.write_text(json.dumps(native))
    claim = json.loads(result.read_text())
    claim["execution"]["native_predictions_sha256"] = _sha(files.native_predictions)
    result.write_text(json.dumps(claim))
    with pytest.raises(ValueError, match="parity claim"):
        verify_completed_result(scenario, result, files)
    assert not published.exists()


def test_prediction_sample_ids_must_match_trace(tmp_path):
    scenario, result, files, _ = _evidence(tmp_path)
    native = json.loads(files.native_predictions.read_text())
    native["predictions"][1]["sample_id"] = "unexpected"
    files.native_predictions.write_text(json.dumps(native))
    claim = json.loads(result.read_text())
    claim["execution"]["native_predictions_sha256"] = _sha(files.native_predictions)
    result.write_text(json.dumps(claim))
    with pytest.raises(ValueError, match="sample IDs"):
        verify_completed_result(scenario, result, files)


def test_hardlinked_evidence_is_not_independent(tmp_path):
    scenario, result, files, _ = _evidence(tmp_path)
    files.peer_readback.unlink()
    files.peer_readback.hardlink_to(files.observation)
    with pytest.raises(ValueError, match="distinct"):
        verify_completed_result(scenario, result, files)


@pytest.mark.parametrize("name", list(NativeEvidenceFiles.__dataclass_fields__))
def test_missing_evidence_blocks_publication(tmp_path, name):
    scenario, result, files, published = _evidence(tmp_path)
    getattr(files, name).unlink()
    with pytest.raises(ValueError, match="missing"):
        publish_completed_result(scenario, result, files, published)
    assert not published.exists()


@pytest.mark.parametrize("name", list(NativeEvidenceFiles.__dataclass_fields__))
def test_tampered_evidence_blocks_publication(tmp_path, name):
    scenario, result, files, published = _evidence(tmp_path)
    with getattr(files, name).open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="hash does not match"):
        publish_completed_result(scenario, result, files, published)
    assert not published.exists()


def test_scenario_mismatch_blocks_publication(tmp_path):
    scenario, result, files, published = _evidence(tmp_path)
    data = json.loads(scenario.read_text())
    data["run_id"] = "other-run"
    scenario.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="scenario_sha256"):
        publish_completed_result(scenario, result, files, published)
    assert not published.exists()


@pytest.mark.parametrize("change", ["reorder", "wrong_session", "duplicate_sample", "wrong_cloud"])
def test_trace_claims_require_ordered_offline_session_and_inference_evidence(tmp_path, change):
    scenario, result, files, published = _evidence(tmp_path)
    events = [json.loads(line) for line in files.event_trace.read_text().splitlines()]
    if change == "reorder":
        events[5], events[6] = events[6], events[5]
    elif change == "wrong_session":
        events[8]["session_id"] = "writer-0"
    elif change == "duplicate_sample":
        events[4]["sample_id"] = events[3]["sample_id"]
    else:
        events[1]["cloud_disabled"] = False
    files.event_trace.write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in events), encoding="utf-8"
    )
    data = json.loads(result.read_text())
    data["execution"]["event_trace_sha256"] = _sha(files.event_trace)
    result.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        publish_completed_result(scenario, result, files, published)
    assert not published.exists()


def test_distinct_readback_files_are_required(tmp_path):
    scenario, result, files, published = _evidence(tmp_path)
    aliased = NativeEvidenceFiles(**{
        name: files.observation if name == "peer_readback" else getattr(files, name)
        for name in NativeEvidenceFiles.__dataclass_fields__
    })
    with pytest.raises(ValueError, match="distinct"):
        publish_completed_result(scenario, result, aliased, published)
    assert not published.exists()


def test_publication_cannot_overwrite_evidence(tmp_path):
    scenario, result, files, _ = _evidence(tmp_path)
    original = files.observation.read_bytes()
    with pytest.raises(ValueError, match="must differ"):
        publish_completed_result(scenario, result, files, files.observation)
    assert files.observation.read_bytes() == original
