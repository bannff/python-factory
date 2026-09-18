"""Artifact verification helpers for the local durable dataset store."""

from __future__ import annotations

import json
from pathlib import Path

from .adapters.scenario_store import LocalScenarioPackStore
from .atomic_io import read_bytes_no_follow
from .contracts import (
    DatasetArtifactRef,
    DatasetGenerationRequest,
    DatasetManifest,
)
from .helpers import _file_uri, _sha256
from .recipe import path_from_uri
from .scenario_generation import validate_scenario_lineage_against_pack


def verify_artifact(
    artifact: DatasetArtifactRef,
    manifests_dir: Path,
    artifacts_root: Path,
    request: DatasetGenerationRequest | None = None,
) -> None:
    """Verify a stored artifact reference before exposing it publicly."""
    dataset_path = path_from_uri(artifact.dataset_uri)
    reference_path = dataset_path.with_suffix(".ref.json")
    require_artifact_path(dataset_path, reference_path, artifacts_root)
    dataset_content = read_bytes_no_follow(dataset_path)
    if _sha256(dataset_content) != artifact.digest:
        raise ValueError("Dataset artifact digest does not match its reference")
    manifest_path = path_from_uri(artifact.manifest_uri)
    try:
        manifest_content = read_bytes_no_follow(manifest_path)
    except FileNotFoundError:
        raise ValueError("Dataset manifest is missing") from None
    verify_manifest_path(manifest_path, artifact.manifest_uri, manifests_dir)
    manifest = DatasetManifest.model_validate_json(manifest_content)
    _verify_non_empty_record_dataset(dataset_content, manifest)
    if manifest.scenario_lineage is not None:
        records = [
            json.loads(line) for line in read_bytes_no_follow(dataset_path).splitlines()
            if line.strip()
        ]
        pack = LocalScenarioPackStore(
            artifacts_root.parent, create=False,
        ).load(manifest.scenario_lineage.scenario_pack)
        validate_scenario_lineage_against_pack(
            records, manifest.scenario_lineage, pack,
        )
    if (
        manifest.dataset_uri != artifact.dataset_uri
        or manifest.dataset_digest != artifact.digest
        or manifest.training_uri != artifact.training_uri
        or manifest.schema_version != artifact.schema_version
        or manifest.training_views != artifact.available_views
        or manifest.view_schema_versions != artifact.view_schema_versions
    ):
        raise ValueError("Dataset manifest does not match its artifact reference")
    if not _blueprint_lineage_matches(manifest, artifacts_root.parent):
        raise ValueError("Dataset manifest blueprint lineage failed verification")
    if request is not None and (
        manifest.recipe_uri != request.recipe_uri
        or manifest.recipe_digest != request.recipe_digest
        or manifest.context_snapshot.uri != request.context_snapshot.uri
        or manifest.context_snapshot.digest != request.context_snapshot.digest
        or manifest.tool_schema_snapshot.uri != request.tool_schema_snapshot.uri
        or manifest.tool_schema_snapshot.digest != request.tool_schema_snapshot.digest
        or manifest.execution_policy != request.execution_policy
        or manifest.training_views != request.requested_views
        or manifest.blueprint_binding != request.blueprint_binding
        or manifest.approval_binding != request.approval_binding
        or not _scenario_request_matches(manifest, request)
    ):
        raise ValueError("Dataset manifest does not match the submitted request")
    if artifact.training_uri:
        training_path = path_from_uri(artifact.training_uri)
        if _sha256(read_bytes_no_follow(training_path)) != artifact.digest:
            raise ValueError("Training view does not match the dataset artifact")


def _verify_non_empty_record_dataset(
    dataset_content: bytes, manifest: DatasetManifest,
) -> None:
    """Reject record datasets whose bytes or signed manifest report no rows."""
    record_check = manifest.quality_results.checks.get("record_count", "")
    try:
        quality_count = int(record_check.removeprefix("passed:").strip())
    except ValueError:
        quality_count = 0
    lineage_count = (
        manifest.stage_lineage[-1].record_count if manifest.stage_lineage else quality_count
    )
    if (
        not dataset_content.strip()
        or not record_check.startswith("passed:")
        or quality_count <= 0
        or lineage_count <= 0
    ):
        raise ValueError("Dataset artifact contains no verified records")


def verify_manifest_path(manifest_path: Path, manifest_uri: str, manifests_dir: Path) -> None:
    expected_name = f"manifest-{_sha256(read_bytes_no_follow(manifest_path))}.json"
    if (
        manifest_path.parent != manifests_dir
        or manifest_path.name != expected_name
        or manifest_uri != _file_uri(manifest_path)
    ):
        raise ValueError("Dataset manifest path is not content addressed")


def require_artifact_path(dataset_path: Path, reference_path: Path, artifacts_root: Path) -> None:
    """Require dataset and sidecar paths to belong to this local store."""
    artifacts_root = artifacts_root.resolve()
    dataset_path = dataset_path.resolve()
    reference_path = reference_path.resolve()
    try:
        dataset_path.relative_to(artifacts_root)
        reference_path.relative_to(artifacts_root)
    except ValueError as error:
        raise ValueError("Dataset artifact is outside the configured store") from error
    if reference_path != dataset_path.with_suffix(".ref.json"):
        raise ValueError("Dataset artifact reference path is invalid")


def _blueprint_lineage_matches(manifest: DatasetManifest, storage_root: Path) -> bool:
    binding = manifest.blueprint_binding
    approval = manifest.approval_binding
    lineage = manifest.blueprint_lineage
    if binding is None:
        return approval is None and lineage is None
    if (
        approval is None
        or approval.blueprint_digest != binding.digest
        or approval.quality_policy != binding.quality_policy
        or lineage is None
        or lineage.binding != binding
    ):
        return False
    from .adapters.blueprint_store import LocalBlueprintStore
    from .blueprint_codec import blueprint_lineage
    blueprint = LocalBlueprintStore(storage_root).load(binding)
    return lineage == blueprint_lineage(blueprint, binding)


def _scenario_request_matches(
    manifest: DatasetManifest, request: DatasetGenerationRequest,
) -> bool:
    generation = request.scenario_generation
    lineage = manifest.scenario_lineage
    if generation is None:
        return lineage is None
    return bool(
        lineage is not None
        and lineage.scenario_pack == generation.scenario_pack
        and lineage.generator_adapter == generation.generator_adapter
        and lineage.generator_version == generation.generator_version
        and lineage.seed == generation.seed
    )
