"""Typed public contracts for dataset generation jobs and bundles."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator

from .base import (  # noqa: F401 — re-export for backward compat
    DatasetExecutionPolicy, DatasetFallbackRecord, DatasetInputRef,
    DatasetProvenanceRecord, DatasetQualityResults, DatasetSnapshotRef,
    DatasetToolSchemaSnapshotRef, _normalize_digest, _require_non_empty,
)
from .approval_models import DatasetApprovalBinding
from .scenario_models import ScenarioPackGenerationInput, ScenarioPackLineage
from .blueprint_models import DatasetBlueprintBinding, DatasetBlueprintLineage


class DatasetGenerationRequest(BaseModel):
    """A versioned declarative request for a dataset bundle."""
    recipe_uri: str
    recipe_digest: str
    input_artifacts: list[DatasetInputRef] = Field(default_factory=list)
    context_snapshot: DatasetSnapshotRef
    tool_schema_snapshot: DatasetToolSchemaSnapshotRef
    requested_views: list[str] = Field(default_factory=lambda: ["default"], min_length=1, max_length=10)
    execution_policy: DatasetExecutionPolicy = Field(default_factory=DatasetExecutionPolicy)
    scenario_generation: ScenarioPackGenerationInput | None = None
    blueprint_binding: DatasetBlueprintBinding | None = None
    approval_binding: DatasetApprovalBinding | None = None
    idempotency_key: str | None = None
    schema_version: str = "1.0"

    @field_validator("recipe_uri")
    @classmethod
    def _validate_recipe_uri(cls, value: str) -> str:
        return _require_non_empty(value, "Dataset recipe URI")

    @field_validator("recipe_digest")
    @classmethod
    def _validate_recipe_digest(cls, value: str) -> str:
        return _normalize_digest(value, "dataset recipe")

    @field_validator("requested_views")
    @classmethod
    def _validate_requested_views(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for view in value:
            name = view.strip()
            if not name:
                raise ValueError("Requested dataset view must be non-empty")
            if name in cleaned:
                raise ValueError("Requested dataset views must be unique")
            cleaned.append(name)
        return cleaned

    @computed_field(return_type=str)
    @property
    def context_snapshot_uri(self) -> str:
        return self.context_snapshot.uri

    @computed_field(return_type=str)
    @property
    def context_snapshot_digest(self) -> str:
        return self.context_snapshot.digest

    @computed_field(return_type=str)
    @property
    def tool_schema_snapshot_uri(self) -> str:
        return self.tool_schema_snapshot.uri

    @computed_field(return_type=str)
    @property
    def tool_schema_snapshot_digest(self) -> str:
        return self.tool_schema_snapshot.digest


class DatasetRecipeStage(BaseModel):
    name: str
    config: dict[str, Any] = Field(default_factory=dict)


class DatasetRecipe(BaseModel):
    version: str
    schema_version: str = "1.0"
    stages: list[DatasetRecipeStage] = Field(min_length=1)
    record_schema: Literal["conversation", "can_frame", "can_artifact", "generic"] = "conversation"


class DatasetJobReceipt(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"
    submitted_at: datetime


class DatasetArtifactRef(BaseModel):
    dataset_uri: str
    manifest_uri: str
    digest: str
    schema_version: str
    available_views: list[str] = Field(min_length=1, max_length=10)
    view_schema_versions: dict[str, str] = Field(default_factory=dict)
    training_uri: str | None = None


class DatasetJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    submitted_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    artifact: DatasetArtifactRef | None = None
    error: str | None = None
    cancelled_at: datetime | None = None
    request: DatasetGenerationRequest


class DatasetManifest(BaseModel):
    """Reproducibility metadata for one immutable dataset bundle."""
    schema_version: str
    dataset_uri: str | None = None
    manifest_uri: str | None = None
    training_uri: str | None = None
    dataset_digest: str
    recipe_uri: str
    recipe_digest: str
    input_artifacts: list[DatasetInputRef]
    context_snapshot: DatasetSnapshotRef
    tool_schema_snapshot: DatasetToolSchemaSnapshotRef
    execution_policy: DatasetExecutionPolicy
    training_views: list[str] = Field(min_length=1, max_length=10)
    view_schema_versions: dict[str, str] = Field(default_factory=dict)
    quality_results: DatasetQualityResults
    provenance: DatasetProvenanceRecord
    stage_adapter_versions: dict[str, str]
    stage_lineage: list["DatasetStageCheckpoint"] = Field(default_factory=list)
    blueprint_binding: DatasetBlueprintBinding | None = None
    approval_binding: DatasetApprovalBinding | None = None
    blueprint_lineage: DatasetBlueprintLineage | None = None
    scenario_lineage: ScenarioPackLineage | None = None
    fallback: DatasetFallbackRecord | None = None
    created_at: datetime

    @computed_field(return_type=str)
    @property
    def context_snapshot_uri(self) -> str:
        return self.context_snapshot.uri

    @computed_field(return_type=str)
    @property
    def context_snapshot_digest(self) -> str:
        return self.context_snapshot.digest

    @computed_field(return_type=str)
    @property
    def tool_schema_snapshot_uri(self) -> str:
        return self.tool_schema_snapshot.uri

    @computed_field(return_type=str)
    @property
    def tool_schema_snapshot_digest(self) -> str:
        return self.tool_schema_snapshot.digest


class DatasetStageCheckpoint(BaseModel):
    """Immutable output metadata for one completed recipe stage."""
    stage_name: str
    stage_index: int
    input_digest: str
    output_uri: str
    output_digest: str
    record_count: int
    schema_version: str
    adapter_version: str
    config_digest: str
    context_snapshot_digest: str
    tool_schema_snapshot_digest: str
    provenance: DatasetProvenanceRecord
    quality_results: DatasetQualityResults
    scenario_lineage: ScenarioPackLineage | None = None
    checkpoint_digest: str | None = None
    fallback: DatasetFallbackRecord | None = None
    created_at: datetime

    @field_validator("checkpoint_digest")
    @classmethod
    def _validate_checkpoint_digest(cls, value: str | None) -> str | None:
        return (
            _normalize_digest(value, "stage checkpoint")
            if value is not None else None
        )
