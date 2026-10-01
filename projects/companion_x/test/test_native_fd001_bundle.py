"""Portable fixtures for the native FD001 staging contract, not device evidence."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from projects.companion_x.experiments.edge_models.native_runner.contracts import (
    NativeScenario,
    NativeTarget,
)
from projects.companion_x.experiments.edge_models.native_runner.fd001_bundle import (
    BundleSourcePins,
    NativeBundleManifest,
    NativeBundleSamples,
    stage_frozen_fd001_bundle,
    stage_native_bundle,
    verify_native_bundle,
)
from projects.companion_x.experiments.edge_models.native_runner.prediction_evidence import (
    dataset_sample_ids,
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _source(tmp_path: Path, *, two_classes: bool = False) -> tuple[Path, Path, BundleSourcePins]:
    count = 480
    model = {
        "schema_version": 2, "kind": "fd001_scaled_logistic",
        "window_cycles": 20, "channels_per_cycle": 24, "feature_count": count,
        "scaler_mean": [0.0] * count, "scaler_scale": [1.0] * count,
        "coefficients": [1.0] + [0.0] * (count - 1) if two_classes else [0.0] * count,
        "intercept": -10.0 if two_classes else 0.0, "threshold": 0.5,
    }
    model["sha256"] = _sha(_canonical(model))
    cohort = {
        "schema_version": 2, "kind": "fd001_official_test_endpoints",
        "model_sha256": model["sha256"],
        "rows": [
            {"engine_id": engine_id, "features": [float(engine_id)] * count,
             "expected_probability": 1 / (1 + math.exp(10 - engine_id)) if two_classes else 0.5,
             "expected_decision": int(engine_id >= 10) if two_classes else 1,
             "rul_label": int(engine_id >= 10) if two_classes else 1}
            for engine_id in range(1, 101)
        ],
    }
    cohort["sha256"] = _sha(_canonical(cohort))
    model_path, cohort_path = tmp_path / "model.json", tmp_path / "cohort.json"
    model_path.write_bytes(_canonical(model))
    cohort_path.write_bytes(_canonical(cohort))
    pins = BundleSourcePins(
        scenario_sha256="a" * 64,
        model_file_sha256=_sha(model_path.read_bytes()),
        model_payload_sha256=model["sha256"],
        cohort_file_sha256=_sha(cohort_path.read_bytes()),
        cohort_payload_sha256=cohort["sha256"],
    )
    return model_path, cohort_path, pins


def test_fd001_runtime_is_explicitly_available_to_both_native_targets():
    for target in NativeTarget:
        scenario = NativeScenario(
            schema_version=1, scenario_id="fd001-native-001", run_id="run-001",
            target=target, device_name="fixture", os_version="fixture",
            model_id="fd001", model_sha256="a" * 64,
            dataset_id="fd001-selected", dataset_sha256="b" * 64,
            runtime="fd001-native-linear", seed=1, parity_tolerance=1e-6,
        )
        assert scenario.runtime == "fd001-native-linear"


def test_stages_content_addressed_bundle_with_selected_rows_and_host_scores(tmp_path):
    model, cohort, pins = _source(tmp_path)
    bundle = stage_native_bundle(model, cohort, tmp_path / "bundles", pins, (1, 2))
    manifest = verify_native_bundle(bundle)
    samples = NativeBundleSamples.model_validate_json((bundle / "samples.json").read_bytes())
    assert bundle.name == _sha((bundle / "manifest.json").read_bytes())
    assert manifest.runtime == "fd001-native-linear"
    assert manifest.source == pins
    assert manifest.peer_engine_ids == (1, 2)
    assert manifest.parity_sample_engine_ids == (1, 2)
    assert manifest.dataset_id == "fd001-native-selected-001"
    assert manifest.dataset_file_sha256 == _sha((bundle / "dataset.json").read_bytes())
    assert dataset_sample_ids((bundle / "dataset.json").read_bytes(), manifest.dataset_id) == [
        "engine-001", "engine-002",
    ]
    assert [sample.sample_id for sample in samples.rows] == ["engine-001", "engine-002"]
    assert all(len(sample.features) == 480 for sample in samples.rows)
    assert [(sample.reference_probability, sample.reference_decision)
            for sample in samples.rows] == [(0.5, 1), (0.5, 1)]
    assert (bundle / "model.json").read_bytes() == model.read_bytes()
    assert stage_native_bundle(model, cohort, tmp_path / "bundles", pins, (1, 2)) == bundle


def test_stages_negative_peer_rows_and_supplemental_positive_parity_row(tmp_path):
    model, cohort, pins = _source(tmp_path, two_classes=True)
    bundle = stage_native_bundle(model, cohort, tmp_path / "bundles", pins,
                                 (1, 2), parity_sample_engine_ids=(1, 2, 20))
    manifest = verify_native_bundle(bundle)
    samples = NativeBundleSamples.model_validate_json((bundle / "samples.json").read_bytes())
    assert manifest.peer_engine_ids == (1, 2)
    assert manifest.parity_sample_engine_ids == (1, 2, 20)
    assert [(row.engine_id, row.reference_decision) for row in samples.rows] == [
        (1, 0), (2, 0), (20, 1),
    ]
    assert dataset_sample_ids((bundle / "dataset.json").read_bytes(), manifest.dataset_id) == [
        "engine-001", "engine-002", "engine-020",
    ]
    assert samples.rows[-1].reference_probability > 0.99


def test_manifest_rejects_relabeling_frozen_peer_or_parity_ids(tmp_path):
    model, cohort, pins = _source(tmp_path, two_classes=True)
    bundle = stage_native_bundle(model, cohort, tmp_path / "bundles", pins,
                                 (1, 2), parity_sample_engine_ids=(1, 2, 20))
    value = json.loads((bundle / "manifest.json").read_text())
    value["source"]["scenario_sha256"] = "5e7dc164c1f4625b27b75ef32a42fe34187f30a18134926f21ee37ea4d95bbd3"
    assert NativeBundleManifest.model_validate_json(_canonical(value)).peer_engine_ids == (1, 2)
    for field, ids in (("peer_engine_ids", [1, 20]),
                       ("parity_sample_engine_ids", [1, 2])):
        changed = json.loads(json.dumps(value))
        changed[field] = ids
        with pytest.raises(ValidationError, match="frozen N=2 scenario"):
            NativeBundleManifest.model_validate_json(_canonical(changed))
    changed = json.loads(json.dumps(value))
    changed["selected_engine_ids"] = changed.pop("peer_engine_ids")
    with pytest.raises(ValidationError):
        NativeBundleManifest.model_validate_json(_canonical(changed))


@pytest.mark.parametrize("peer_ids, sample_ids", [
    ((1, 2), (1, 20)),
    ((1, 2), (1, 2, 2, 20)),
    ((1, 2), (1, 2, 101)),
    ((1, 2), (1, 2, 0)),
    ((1, 2), (20, 2, 1)),
    ((1, 1), (1, 20)),
    ((0, 2), (0, 2, 20)),
])
def test_rejects_invalid_peer_or_parity_sample_boundaries(tmp_path, peer_ids, sample_ids):
    model, cohort, pins = _source(tmp_path)
    with pytest.raises(ValueError, match="peer|parity"):
        stage_native_bundle(model, cohort, tmp_path / "bundles", pins,
                            peer_ids, parity_sample_engine_ids=sample_ids)
    assert not (tmp_path / "bundles").exists()


@pytest.mark.parametrize("change, message", [
    ("model_file", "model file digest"),
    ("cohort_file", "cohort file digest"),
    ("model_schema", "model schema"),
    ("bad_feature", "cohort features"),
    ("bad_probability", "prediction parity"),
])
def test_rejects_mismatched_or_invalid_sources(tmp_path, change, message):
    model, cohort, pins = _source(tmp_path)
    if change in {"model_file", "cohort_file"}:
        (model if change == "model_file" else cohort).write_bytes(b"{}")
    elif change == "model_schema":
        value = json.loads(model.read_text())
        value["feature_count"] = 479
        model.write_bytes(_canonical(value))
        pins = pins.model_copy(update={"model_file_sha256": _sha(model.read_bytes())})
    else:
        value = json.loads(cohort.read_text())
        value["rows"][0]["features"] = [0.0] * (479 if change == "bad_feature" else 480)
        if change == "bad_probability":
            value["rows"][0]["expected_probability"] = 0.6
        value["sha256"] = _sha(_canonical({key: item for key, item in value.items() if key != "sha256"}))
        cohort.write_bytes(_canonical(value))
        pins = pins.model_copy(update={
            "cohort_file_sha256": _sha(cohort.read_bytes()),
            "cohort_payload_sha256": value["sha256"],
        })
    with pytest.raises(ValueError, match=message):
        stage_native_bundle(model, cohort, tmp_path / "bundles", pins, (1, 2))
    assert not (tmp_path / "bundles").exists()


def test_verify_rejects_tampered_bundle_file(tmp_path):
    model, cohort, pins = _source(tmp_path)
    bundle = stage_native_bundle(model, cohort, tmp_path / "bundles", pins, (1, 2))
    with (bundle / "samples.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="samples file digest"):
        verify_native_bundle(bundle)
    with pytest.raises(ValueError, match="samples file digest"):
        stage_native_bundle(model, cohort, tmp_path / "bundles", pins, (1, 2))


def test_verify_rejects_tampered_dataset_manifest(tmp_path):
    model, cohort, pins = _source(tmp_path)
    bundle = stage_native_bundle(model, cohort, tmp_path / "bundles", pins, (1, 2))
    with (bundle / "dataset.json").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError, match="dataset file digest"):
        verify_native_bundle(bundle)


def test_frozen_staging_rejects_unreviewed_model_and_cohort(tmp_path):
    model, cohort, _ = _source(tmp_path)
    with pytest.raises(ValueError, match="model file digest"):
        stage_frozen_fd001_bundle(model, cohort, tmp_path / "bundles")
    assert not (tmp_path / "bundles").exists()


@pytest.mark.parametrize("field", ["model_payload_sha256", "cohort_payload_sha256"])
def test_payload_pin_must_match_canonical_source(tmp_path, field):
    model, cohort, pins = _source(tmp_path)
    pins = pins.model_copy(update={field: "f" * 64})
    with pytest.raises(ValueError, match="payload digest"):
        stage_native_bundle(model, cohort, tmp_path / "bundles", pins, (1, 2))
    assert not (tmp_path / "bundles").exists()


@given(st.one_of(st.just(float("nan")), st.just(float("inf")), st.just(float("-inf"))))
def test_sample_contract_rejects_nonfinite_feature(value):
    with pytest.raises(ValidationError, match="finite number"):
        NativeBundleSamples.model_validate({
            "schema_version": 1, "kind": "fd001-native-samples", "feature_count": 480,
            "rows": ({"sample_id": "engine-001", "engine_id": 1,
                      "features": (0.0,) * 479 + (value,),
                      "reference_probability": 0.5, "reference_decision": 1},),
        })


def test_manifest_requires_digest_and_explicit_runtime():
    with pytest.raises(ValidationError):
        NativeBundleManifest.model_validate({"schema_version": 1, "runtime": "tflite"})
