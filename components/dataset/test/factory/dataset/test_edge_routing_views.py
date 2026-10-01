"""Routing split mechanics and fail-closed publication boundaries."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from factory.dataset.runtime.artifact_utils import _verify_routing_views, verify_artifact
from factory.dataset.runtime.bundle_writer import (
    _routing_view_contents, _training_view_name, write_bundle,
)
from factory.dataset.runtime.contracts import (
    DatasetArtifactRef, DatasetGenerationRequest, DatasetManifest,
    DatasetProvenanceRecord, DatasetQualityResults, DatasetRecipe,
    DatasetSnapshotRef, DatasetToolSchemaSnapshotRef,
)
from factory.dataset.runtime.edge_routing_contracts import EdgeRoutingExample
from factory.dataset.runtime.local import LocalDatasetStore
from factory.dataset.runtime.quality import evaluate_quality
from factory.dataset.runtime.recipe import records_content

from .test_edge_routing_contracts import _example


def _records() -> list[EdgeRoutingExample]:
    return [
        EdgeRoutingExample.model_validate(_example(split=split))
        for split in ("train", "validation", "test")
    ]


def _request(views: list[str]) -> DatasetGenerationRequest:
    return DatasetGenerationRequest(
        recipe_uri="file:///fixtures/routing-recipe.json", recipe_digest="a" * 64,
        context_snapshot=DatasetSnapshotRef(uri="file:///fixtures/context", digest="a" * 64),
        tool_schema_snapshot=DatasetToolSchemaSnapshotRef(
            uri="file:///fixtures/tools", digest="a" * 64,
        ),
        requested_views=views,
    )


def _recipe() -> DatasetRecipe:
    return DatasetRecipe.model_validate({
        "version": "routing-test-v1", "stages": [{"name": "local-validate"}],
        "record_schema": "edge_routing_example",
    })


def _synthetic_forgery(tmp_path: Path) -> tuple[LocalDatasetStore, DatasetArtifactRef, Path]:
    """Hand-build a structural fixture; production writer must reject these rows."""
    records = _records()
    store = LocalDatasetStore(tmp_path / "store")
    bundle_dir = store.artifacts_dir / "routing-views"
    bundle_dir.mkdir()
    content = records_content(records, record_schema="edge_routing_example")
    digest = hashlib.sha256(content).hexdigest()
    dataset_path = bundle_dir / f"dataset-{digest}.jsonl"
    dataset_path.write_bytes(content)
    views = ["test", "validation", "train"]
    paths: dict[str, Path] = {}
    for split, payload in _routing_view_contents(records, views).items():
        path = bundle_dir / f"view-{split}-{hashlib.sha256(payload).hexdigest()}.jsonl"
        path.write_bytes(payload)
        paths[split] = path
    train_uri = paths["train"].resolve().as_uri()
    request = _request(views)
    forged_quality = DatasetQualityResults(checks={
        "record_count": "passed: 3", "trusted_run_provenance": "passed",
    })
    manifest = DatasetManifest(
        schema_version="1.0", record_schema="edge_routing_example",
        dataset_uri=dataset_path.resolve().as_uri(), dataset_digest=digest,
        recipe_uri=request.recipe_uri, recipe_digest=request.recipe_digest,
        input_artifacts=[], context_snapshot=request.context_snapshot,
        tool_schema_snapshot=request.tool_schema_snapshot,
        execution_policy=request.execution_policy,
        training_views=views, view_schema_versions={split: "1.0" for split in views},
        training_uri=train_uri, quality_results=forged_quality,
        provenance=DatasetProvenanceRecord(materializer="test", job_id="routing-views"),
        stage_adapter_versions={"test": "1"}, created_at=datetime.now(UTC),
    )
    manifest_content = manifest.model_dump_json(exclude_none=True).encode()
    manifest_path = store.manifests_dir / (
        f"manifest-{hashlib.sha256(manifest_content).hexdigest()}.json"
    )
    manifest_path.write_bytes(manifest_content)
    artifact = DatasetArtifactRef(
        dataset_uri=dataset_path.resolve().as_uri(),
        manifest_uri=manifest_path.resolve().as_uri(), digest=digest,
        schema_version="1.0", record_schema="edge_routing_example", available_views=views,
        view_schema_versions={split: "1.0" for split in views},
        training_uri=train_uri,
    )
    return store, artifact, dataset_path


def test_routing_view_content_is_disjoint_and_train_selected_when_last() -> None:
    views = _routing_view_contents(_records(), ["test", "validation", "train"])
    assert set(views) == {"train", "validation", "test"}
    assert len(set(views.values())) == 3
    for split, payload in views.items():
        (row,) = [json.loads(line) for line in payload.splitlines()]
        assert row["split"] == split
        assert row["record_id"] == f"routing-{split}-1"
    assert _training_view_name("edge_routing_example", list(views)) == "train"
    assert _training_view_name("generic", ["sft", "dpo"]) == "sft"


@pytest.mark.parametrize("views", [["train", "holdout"], ["test", "validation"]])
def test_unknown_or_missing_train_routing_view_fails(views: list[str]) -> None:
    with pytest.raises(ValueError, match="Routing views"):
        _routing_view_contents(_records(), views)


def test_direct_writer_rejects_untrusted_routing_before_artifacts(tmp_path: Path) -> None:
    store = LocalDatasetStore(tmp_path / "store")
    records = _records()
    actual_quality = evaluate_quality(records, record_schema="edge_routing_example")
    assert not actual_quality.passed
    for quality in (
        actual_quality,
        DatasetQualityResults(checks={"record_count": "passed: 3"}),
    ):
        with pytest.raises(ValueError, match="trusted provenance"):
            write_bundle(
                store, records, _request(["train", "validation", "test"]),
                _recipe(), "routing-views", {}, [], quality,
                DatasetProvenanceRecord(materializer="test", job_id="routing-views"), None,
            )
    assert not list(store.artifacts_dir.iterdir())
    assert not list(store.manifests_dir.iterdir())


def test_structural_verifier_detects_holdout_bytes_in_train_view(tmp_path: Path) -> None:
    store, artifact, dataset_path = _synthetic_forgery(tmp_path)
    source = dataset_path.read_bytes()
    _verify_routing_views(source, dataset_path, artifact)
    bundle_dir = store.artifacts_dir / "routing-views"
    (train_path,) = bundle_dir.glob("view-train-*.jsonl")
    (test_path,) = bundle_dir.glob("view-test-*.jsonl")
    train_path.write_bytes(test_path.read_bytes())
    with pytest.raises(ValueError, match="Routing view train"):
        _verify_routing_views(source, dataset_path, artifact)


@pytest.mark.parametrize("target", ["test", None])
def test_structural_verifier_rejects_swapped_or_missing_training_uri(
    tmp_path: Path, target: str | None,
) -> None:
    store, artifact, dataset_path = _synthetic_forgery(tmp_path)
    if target:
        (view_path,) = (store.artifacts_dir / "routing-views").glob(f"view-{target}-*.jsonl")
        alternate = view_path.resolve().as_uri()
    else:
        alternate = None
    forged = artifact.model_copy(update={"training_uri": alternate})
    with pytest.raises(ValueError, match="Training view must point"):
        _verify_routing_views(dataset_path.read_bytes(), dataset_path, forged)


def test_public_verifier_rejects_forged_quality_despite_valid_split_views(
    tmp_path: Path,
) -> None:
    store, artifact, _ = _synthetic_forgery(tmp_path)
    with pytest.raises(ValueError, match="trusted provenance"):
        verify_artifact(artifact, store.manifests_dir, store.artifacts_dir)


@pytest.mark.parametrize("downgraded_schema", ["conversation", "generic"])
def test_public_verifier_rejects_routing_schema_downgrade(
    tmp_path: Path, downgraded_schema: str,
) -> None:
    store, artifact, dataset_path = _synthetic_forgery(tmp_path)
    full_view = dataset_path.parent / f"view-train-{artifact.digest}.jsonl"
    full_view.write_bytes(dataset_path.read_bytes())
    original_manifest = DatasetManifest.model_validate_json(
        Path(artifact.manifest_uri.removeprefix("file://")).read_bytes(),
    )
    forged_manifest = original_manifest.model_copy(update={
        "record_schema": downgraded_schema,
        "training_uri": full_view.resolve().as_uri(),
        "training_views": ["train"],
        "view_schema_versions": {"train": "1.0"},
    })
    content = forged_manifest.model_dump_json(exclude_none=True).encode()
    manifest_path = store.manifests_dir / f"manifest-{hashlib.sha256(content).hexdigest()}.json"
    manifest_path.write_bytes(content)
    forged = artifact.model_copy(update={
        "manifest_uri": manifest_path.resolve().as_uri(),
        "record_schema": downgraded_schema,
        "training_uri": full_view.resolve().as_uri(),
        "available_views": ["train"],
        "view_schema_versions": {"train": "1.0"},
    })
    with pytest.raises(ValueError, match="record schema|routing-shaped"):
        verify_artifact(forged, store.manifests_dir, store.artifacts_dir)


def test_public_verifier_binds_artifact_and_manifest_schema(tmp_path: Path) -> None:
    store, artifact, _ = _synthetic_forgery(tmp_path)
    manifest = DatasetManifest.model_validate_json(
        Path(artifact.manifest_uri.removeprefix("file://")).read_bytes(),
    )
    downgraded = manifest.model_copy(update={"record_schema": "generic"})
    content = downgraded.model_dump_json(exclude_none=True).encode()
    path = store.manifests_dir / f"manifest-{hashlib.sha256(content).hexdigest()}.json"
    path.write_bytes(content)
    forged = artifact.model_copy(update={"manifest_uri": path.resolve().as_uri()})
    with pytest.raises(ValueError, match="record schema|manifest"):
        verify_artifact(forged, store.manifests_dir, store.artifacts_dir)


def test_public_verifier_binds_record_schema_to_verified_recipe(tmp_path: Path) -> None:
    recipe_path = tmp_path / "routing-recipe.json"
    recipe_content = json.dumps({
        "version": "routing-v1", "stages": [{"name": "local-validate"}],
        "record_schema": "edge_routing_example",
    }).encode()
    recipe_path.write_bytes(recipe_content)
    request = _request(["default"]).model_copy(update={
        "recipe_uri": recipe_path.resolve().as_uri(),
        "recipe_digest": hashlib.sha256(recipe_content).hexdigest(),
    })
    store = LocalDatasetStore(tmp_path / "store")
    records = [{"messages": [
        {"role": "user", "content": "request"},
        {"role": "assistant", "content": "response"},
    ]}]
    artifact = write_bundle(
        store, records, request,
        DatasetRecipe(version="generic-v1", stages=[{"name": "local-validate"}],
                      record_schema="generic"),
        "schema-forgery", {}, [], evaluate_quality(records),
        DatasetProvenanceRecord(materializer="test", job_id="schema-forgery"), None,
    )
    with pytest.raises(ValueError, match="record schema does not match verified recipe"):
        verify_artifact(artifact, store.manifests_dir, store.artifacts_dir, request=request)


def test_generic_labeled_outcome_row_is_not_mistaken_for_routing(tmp_path: Path) -> None:
    store = LocalDatasetStore(tmp_path / "store")
    records = [{
        "record_id": "item-1", "split": "train", "outcome": "resolved",
        "messages": [
            {"role": "user", "content": "status"},
            {"role": "assistant", "content": "resolved"},
        ],
    }]
    artifact = write_bundle(
        store, records, _request(["default"]),
        DatasetRecipe(version="generic-v1", stages=[{"name": "local-validate"}],
                      record_schema="generic"),
        "generic-outcome", {}, [], evaluate_quality(records),
        DatasetProvenanceRecord(materializer="test", job_id="generic-outcome"), None,
    )
    verify_artifact(artifact, store.manifests_dir, store.artifacts_dir)


def test_verifier_rejects_rows_inconsistent_with_declared_schema(tmp_path: Path) -> None:
    store = LocalDatasetStore(tmp_path / "store")
    records = [{"value": 1}]
    quality = DatasetQualityResults(checks={"record_count": "passed: 1"})
    artifact = write_bundle(
        store, records, _request(["default"]),
        DatasetRecipe(version="generic-v1", stages=[{"name": "local-validate"}],
                      record_schema="generic"),
        "forged-conversation", {}, [], quality,
        DatasetProvenanceRecord(materializer="test", job_id="forged-conversation"), None,
    )
    manifest = DatasetManifest.model_validate_json(
        Path(artifact.manifest_uri.removeprefix("file://")).read_bytes(),
    ).model_copy(update={"record_schema": "conversation"})
    content = manifest.model_dump_json(exclude_none=True).encode()
    path = store.manifests_dir / f"manifest-{hashlib.sha256(content).hexdigest()}.json"
    path.write_bytes(content)
    forged = artifact.model_copy(update={
        "record_schema": "conversation", "manifest_uri": path.resolve().as_uri(),
    })
    with pytest.raises(ValueError, match="declared record schema"):
        verify_artifact(forged, store.manifests_dir, store.artifacts_dir)


@pytest.mark.parametrize("schema", ["generic", "can_frame", "can_artifact"])
def test_legacy_bundle_without_schema_field_remains_readable(
    tmp_path: Path, schema: str,
) -> None:
    store = LocalDatasetStore(tmp_path / "store")
    records = [{"signal": "example"}]
    artifact = write_bundle(
        store, records, _request(["default"]),
        DatasetRecipe(version="legacy-v1", stages=[{"name": "local-validate"}],
                      record_schema=schema),
        "legacy", {}, [], DatasetQualityResults(checks={"record_count": "passed: 1"}),
        DatasetProvenanceRecord(materializer="test", job_id="legacy"), None,
    )
    manifest_data = json.loads(Path(artifact.manifest_uri.removeprefix("file://")).read_bytes())
    manifest_data.pop("record_schema")
    manifest_content = json.dumps(manifest_data, separators=(",", ":")).encode()
    manifest_path = store.manifests_dir / (
        f"manifest-{hashlib.sha256(manifest_content).hexdigest()}.json"
    )
    manifest_path.write_bytes(manifest_content)
    artifact_data = artifact.model_dump(mode="json", exclude={"record_schema"})
    artifact_data["manifest_uri"] = manifest_path.resolve().as_uri()
    legacy = DatasetArtifactRef.model_validate(artifact_data)
    assert "record_schema" not in legacy.model_fields_set
    verify_artifact(legacy, store.manifests_dir, store.artifacts_dir)


def test_schema_omission_cannot_hide_routing_rows(tmp_path: Path) -> None:
    store, artifact, dataset_path = _synthetic_forgery(tmp_path)
    full_view = dataset_path.parent / f"view-train-{artifact.digest}.jsonl"
    full_view.write_bytes(dataset_path.read_bytes())
    manifest_data = json.loads(Path(artifact.manifest_uri.removeprefix("file://")).read_bytes())
    manifest_data.pop("record_schema")
    manifest_data["training_uri"] = full_view.resolve().as_uri()
    manifest_data["training_views"] = ["train"]
    manifest_data["view_schema_versions"] = {"train": "1.0"}
    content = json.dumps(manifest_data, separators=(",", ":")).encode()
    path = store.manifests_dir / f"manifest-{hashlib.sha256(content).hexdigest()}.json"
    path.write_bytes(content)
    artifact_data = artifact.model_dump(mode="json", exclude={"record_schema"})
    artifact_data.update({
        "manifest_uri": path.resolve().as_uri(),
        "training_uri": full_view.resolve().as_uri(),
        "available_views": ["train"],
        "view_schema_versions": {"train": "1.0"},
    })
    hidden = DatasetArtifactRef.model_validate(artifact_data)
    with pytest.raises(ValueError, match="Routing-shaped"):
        verify_artifact(hidden, store.manifests_dir, store.artifacts_dir)
