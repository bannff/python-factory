"""Stage an integrity-checked FD001 fixture for native debug apps.

Staging proves source identity and host predictions. It does not run an app,
prove native parity, or exercise Ditto SDK synchronization.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import StrictContract
from .prediction_evidence import DatasetManifest, DatasetSample

_CONTRACTS = importlib.import_module(
    "projects.companion_x.experiments.edge_models.edge-ditto-device-flow-001.contracts"
)
_SCENARIO = Path(__file__).resolve().parents[1] / "edge-ditto-device-flow-001" / "scenario-n2.json"
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Finite = Annotated[float, Field(allow_inf_nan=False)]


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class BundleSourcePins(StrictContract):
    scenario_sha256: Digest
    model_file_sha256: Digest
    model_payload_sha256: Digest
    cohort_file_sha256: Digest
    cohort_payload_sha256: Digest


class NativeBundleSample(StrictContract):
    sample_id: str = Field(pattern=r"^engine-[0-9]{3}$")
    engine_id: int = Field(ge=1, le=100)
    features: tuple[Finite, ...] = Field(min_length=480, max_length=480)
    reference_probability: Finite = Field(ge=0, le=1)
    reference_decision: Literal[0, 1]

    @model_validator(mode="after")
    def sample_id_matches_engine(self) -> NativeBundleSample:
        if self.sample_id != f"engine-{self.engine_id:03d}":
            raise ValueError("sample ID must encode engine ID")
        return self


class NativeBundleSamples(StrictContract):
    schema_version: Literal[1] = 1
    kind: Literal["fd001-native-samples"] = "fd001-native-samples"
    feature_count: Literal[480] = 480
    rows: tuple[NativeBundleSample, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ordered_rows(self) -> NativeBundleSamples:
        ids = tuple(row.engine_id for row in self.rows)
        if ids != tuple(sorted(set(ids))):
            raise ValueError("sample engine IDs must be unique and sorted")
        return self


class NativeBundleManifest(StrictContract):
    schema_version: Literal[2] = 2
    kind: Literal["fd001-native-bundle"] = "fd001-native-bundle"
    runtime: Literal["fd001-native-linear"] = "fd001-native-linear"
    source: BundleSourcePins
    samples_file_sha256: Digest
    dataset_file_sha256: Digest
    dataset_id: Literal["fd001-native-selected-001"] = "fd001-native-selected-001"
    peer_engine_ids: tuple[int, ...] = Field(min_length=1)
    parity_sample_engine_ids: tuple[int, ...] = Field(min_length=1)
    feature_count: Literal[480] = 480

    @model_validator(mode="after")
    def unique_ordered_ids(self) -> NativeBundleManifest:
        _validate_engine_ids(self.peer_engine_ids, "peer")
        _validate_engine_ids(self.parity_sample_engine_ids, "parity sample")
        if not set(self.peer_engine_ids).issubset(self.parity_sample_engine_ids):
            raise ValueError("peer engine IDs must be included in parity samples")
        if self.source.scenario_sha256 == _CONTRACTS.FROZEN_N2_SCENARIO_SHA256 and (
            self.peer_engine_ids != (1, 2) or self.parity_sample_engine_ids != (1, 2, 20)
        ):
            raise ValueError("frozen N=2 scenario requires peers 1/2 and parity samples 1/2/20")
        return self


def _validate_engine_ids(ids: tuple[int, ...], purpose: str) -> None:
    if not ids or any(type(engine_id) is not int or not 1 <= engine_id <= 100 for engine_id in ids):
        raise ValueError(f"{purpose} engine IDs must be in the frozen cohort 1..100")
    if ids != tuple(sorted(set(ids))):
        raise ValueError(f"{purpose} engine IDs must be unique and sorted")


def _read_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected a regular artifact file: {path.name}")
    return path.read_bytes()


def _validate_model_for_scoring(model: dict) -> None:
    if (
        model.get("schema_version") != 2
        or model.get("kind") != _CONTRACTS.MODEL_KIND
        or model.get("window_cycles") != 20
        or model.get("channels_per_cycle") != 24
        or model.get("feature_count") != 480
    ):
        raise ValueError("model schema is unsupported")
    for key in ("scaler_mean", "scaler_scale", "coefficients"):
        values = model.get(key)
        if not isinstance(values, list) or len(values) != 480 or any(not _CONTRACTS.finite(item) for item in values):
            raise ValueError(f"model {key} is invalid")
    if any(item <= 0 for item in model["scaler_scale"]):
        raise ValueError("model scaler is invalid")
    if not _CONTRACTS.finite(model.get("intercept")):
        raise ValueError("model intercept is invalid")
    threshold = model.get("threshold")
    if not _CONTRACTS.finite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("model threshold is invalid")


def _validated_sources(
    model_path: Path, cohort_path: Path, pins: BundleSourcePins
) -> tuple[bytes, dict, dict, dict[int, float]]:
    model_bytes, cohort_bytes = _read_regular(model_path), _read_regular(cohort_path)
    if _sha(model_bytes) != pins.model_file_sha256:
        raise ValueError("model file digest differs from source pin")
    if _sha(cohort_bytes) != pins.cohort_file_sha256:
        raise ValueError("cohort file digest differs from source pin")
    model = _CONTRACTS.parse_json_bytes(model_bytes)
    cohort = _CONTRACTS.parse_json_bytes(cohort_bytes)
    _CONTRACTS.validate_artifacts(model, cohort)
    if model.get("sha256") != _CONTRACTS.payload_digest(model) or model["sha256"] != pins.model_payload_sha256:
        raise ValueError("model payload digest differs from source pin")
    if cohort.get("sha256") != _CONTRACTS.payload_digest(cohort) or cohort["sha256"] != pins.cohort_payload_sha256:
        raise ValueError("cohort payload digest differs from source pin")
    return model_bytes, model, cohort, _CONTRACTS.verify_parity(model, cohort)


def stage_native_bundle(
    model_path: Path, cohort_path: Path, output_dir: Path,
    pins: BundleSourcePins, peer_engine_ids: tuple[int, ...],
    *, parity_sample_engine_ids: tuple[int, ...] | None = None,
) -> Path:
    """Stage a pinned fixture; the caller supplies reviewed source pins."""
    model_bytes, model, cohort, scores = _validated_sources(model_path, cohort_path, pins)
    peer_ids = tuple(peer_engine_ids)
    parity_ids = tuple(parity_sample_engine_ids) if parity_sample_engine_ids is not None else peer_ids
    _validate_engine_ids(peer_ids, "peer")
    _validate_engine_ids(parity_ids, "parity sample")
    if not set(peer_ids).issubset(parity_ids):
        raise ValueError("peer engine IDs must be included in parity samples")
    samples = NativeBundleSamples(rows=tuple(
        NativeBundleSample(
            sample_id=f"engine-{engine_id:03d}", engine_id=engine_id,
            features=tuple(cohort["rows"][engine_id - 1]["features"]),
            reference_probability=scores[engine_id],
            reference_decision=int(scores[engine_id] >= model["threshold"]),
        ) for engine_id in parity_ids
    ))
    sample_bytes = _json_bytes(samples.model_dump(mode="json"))
    dataset = DatasetManifest(
        schema_version=1, dataset_id="fd001-native-selected-001", split="test",
        samples=tuple(
            DatasetSample(sample_id=sample.sample_id,
                          sha256=_sha(_json_bytes(sample.model_dump(mode="json"))))
            for sample in samples.rows
        ),
    )
    dataset_bytes = _json_bytes(dataset.model_dump(mode="json"))
    manifest = NativeBundleManifest(
        source=pins, samples_file_sha256=_sha(sample_bytes),
        dataset_file_sha256=_sha(dataset_bytes), peer_engine_ids=peer_ids,
        parity_sample_engine_ids=parity_ids,
    )
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    bundle = output_dir / _sha(manifest_bytes)
    if bundle.exists():
        verify_native_bundle(bundle)
        return bundle
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".fd001-stage-", dir=output_dir) as temporary:
        staged = Path(temporary) / "bundle"
        staged.mkdir()
        (staged / "model.json").write_bytes(model_bytes)
        (staged / "samples.json").write_bytes(sample_bytes)
        (staged / "dataset.json").write_bytes(dataset_bytes)
        (staged / "manifest.json").write_bytes(manifest_bytes)
        try:
            os.replace(staged, bundle)
        except OSError:
            if not bundle.exists():
                raise
            verify_native_bundle(bundle)
    return bundle


def verify_native_bundle(bundle: Path) -> NativeBundleManifest:
    """Check the portable fixture's bytes, schema, links, and host parity."""
    if bundle.is_symlink() or not bundle.is_dir():
        raise ValueError("bundle must be a regular directory")
    if {path.name for path in bundle.iterdir()} != {"manifest.json", "model.json", "samples.json", "dataset.json"}:
        raise ValueError("bundle file set differs from the contract")
    manifest_bytes = _read_regular(bundle / "manifest.json")
    if bundle.name != _sha(manifest_bytes):
        raise ValueError("bundle directory digest differs from manifest")
    manifest = NativeBundleManifest.model_validate_json(manifest_bytes)
    model_bytes = _read_regular(bundle / "model.json")
    sample_bytes = _read_regular(bundle / "samples.json")
    dataset_bytes = _read_regular(bundle / "dataset.json")
    if _sha(model_bytes) != manifest.source.model_file_sha256:
        raise ValueError("model file digest differs from manifest")
    if _sha(sample_bytes) != manifest.samples_file_sha256:
        raise ValueError("samples file digest differs from manifest")
    if _sha(dataset_bytes) != manifest.dataset_file_sha256:
        raise ValueError("dataset file digest differs from manifest")
    model = _CONTRACTS.parse_json_bytes(model_bytes)
    if model.get("sha256") != _CONTRACTS.payload_digest(model) or model["sha256"] != manifest.source.model_payload_sha256:
        raise ValueError("model payload digest differs from manifest")
    _validate_model_for_scoring(model)
    samples = NativeBundleSamples.model_validate_json(sample_bytes)
    dataset = DatasetManifest.model_validate_json(dataset_bytes)
    if dataset.dataset_id != manifest.dataset_id or dataset.split != "test":
        raise ValueError("dataset manifest identity differs from bundle")
    if tuple(row.engine_id for row in samples.rows) != manifest.parity_sample_engine_ids:
        raise ValueError("parity sample engine IDs differ from manifest")
    if tuple(item.sample_id for item in dataset.samples) != tuple(row.sample_id for row in samples.rows):
        raise ValueError("dataset sample IDs differ from selected rows")
    if any(item.sha256 != _sha(_json_bytes(row.model_dump(mode="json")))
           for item, row in zip(dataset.samples, samples.rows, strict=True)):
        raise ValueError("dataset sample hashes differ from selected rows")
    for sample in samples.rows:
        observed = _CONTRACTS.infer(model, {"features": sample.features})
        if observed != sample.reference_probability or int(observed >= model["threshold"]) != sample.reference_decision:
            raise ValueError("sample host prediction parity differs from model")
    if manifest.source.scenario_sha256 == _CONTRACTS.FROZEN_N2_SCENARIO_SHA256 and (
        tuple(row.reference_decision for row in samples.rows) != (0, 0, 1)
    ):
        raise ValueError("frozen parity samples do not cover pinned negative and positive decisions")
    return manifest


def stage_frozen_fd001_bundle(model_path: Path, cohort_path: Path, output_dir: Path) -> Path:
    """Use the reviewed ENG-184 N=2 scenario pins for native fixture staging."""
    scenario = _CONTRACTS.validate_scenario(_CONTRACTS.parse_json_bytes(_SCENARIO.read_bytes()))
    pins = BundleSourcePins(
        scenario_sha256=_CONTRACTS.FROZEN_N2_SCENARIO_SHA256,
        model_file_sha256=scenario["model"]["file_sha256"],
        model_payload_sha256=scenario["model"]["payload_sha256"],
        cohort_file_sha256=scenario["cohort"]["file_sha256"],
        cohort_payload_sha256=scenario["cohort"]["payload_sha256"],
    )
    bundle = stage_native_bundle(
        model_path, cohort_path, output_dir, pins, tuple(scenario["cohort"]["engine_ids"]),
        parity_sample_engine_ids=(*scenario["cohort"]["engine_ids"], 20),
    )
    manifest = verify_native_bundle(bundle)
    if manifest.source != pins or manifest.peer_engine_ids != tuple(scenario["cohort"]["engine_ids"]):
        raise ValueError("staged bundle differs from frozen scenario pins")
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    print(stage_frozen_fd001_bundle(args.model, args.cohort, args.output))


if __name__ == "__main__":
    main()
