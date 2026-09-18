"""Stage execution loop for recipe materialization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    DatasetFallbackRecord, DatasetGenerationRequest, DatasetProvenanceRecord,
    DatasetQualityResults, DatasetStageCheckpoint,
)
from .helpers import _config_digest, _sha256
from .ports import DatasetStagePort
from .quality import evaluate_quality
from .recipe import records_content
from .scenario_errors import ScenarioGenerationError
from .scenario_models import (
    ScenarioPackGenerationInput, ScenarioPackLineage,
)
from .validation import dispatch_validator


def run_stage_loop(
    recipe, request: DatasetGenerationRequest, records: list,
    stages: dict[str, DatasetStagePort], checkpoints,
    existing_checkpoints: dict[int, DatasetStageCheckpoint], job_id: str,
    check_running=None,
) -> tuple[list, dict[str, str], DatasetProvenanceRecord, DatasetQualityResults,
           DatasetFallbackRecord | None, list[DatasetStageCheckpoint]]:
    """Execute recipe stages, resuming from checkpoints where possible."""
    record_schema = getattr(recipe, "record_schema", "conversation")
    stage_versions: dict[str, str] = {}
    stage_lineage: list[DatasetStageCheckpoint] = []
    final_quality = evaluate_quality(records)
    final_provenance = DatasetProvenanceRecord(materializer="local-recipe", job_id=job_id)
    final_fallback: DatasetFallbackRecord | None = None
    current_content = (
        b"" if record_schema == "can_artifact" and not records
        else records_content(records, record_schema=record_schema)
    )
    current_digest = _sha256(current_content)

    for index, recipe_stage in enumerate(recipe.stages):
        checkpoint = existing_checkpoints.get(index)
        config_digest = _config_digest(recipe_stage.config)
        context_digest = request.context_snapshot.digest
        tool_digest = request.tool_schema_snapshot.digest
        stage_config = dict(recipe_stage.config)
        if recipe_stage.name == "apigenmt":
            stage_config["tool_schema_snapshot"] = request.tool_schema_snapshot
        stage = stages.get(recipe_stage.name)
        if stage is None:
            raise ValueError(f"Unsupported dataset recipe stage: {recipe_stage.name}")

        if checkpoint is not None:
            if (
                checkpoint.stage_name != recipe_stage.name
                or checkpoint.stage_index != index
                or checkpoint.schema_version != recipe.schema_version
                or (
                    request.scenario_generation is not None
                    and checkpoint.adapter_version != stage.stage_version
                )
                or checkpoint.input_digest != current_digest
                or checkpoint.config_digest != config_digest
                or checkpoint.context_snapshot_digest != context_digest
                or checkpoint.tool_schema_snapshot_digest != tool_digest
            ):
                raise ValueError("Stage checkpoint does not match the current job state")
            if checkpoint.fallback is not None:
                require_authorized_fallback(request, checkpoint.fallback)
            records = _load_checkpoint_records(
                checkpoint, record_schema, checkpoints.root, job_id,
                require_digest=request.scenario_generation is not None,
            )
            if request.scenario_generation is not None:
                _validate_scenario_stage(
                    stage, records, checkpoint.scenario_lineage,
                    request.scenario_generation,
                )
            stage_versions[recipe_stage.name] = checkpoint.adapter_version
            final_quality = checkpoint.quality_results
            final_provenance = checkpoint.provenance
            final_fallback = checkpoint.fallback or final_fallback
            stage_lineage.append(checkpoint)
            current_digest = checkpoint.output_digest
            continue

        if check_running is not None:
            check_running()
        input_digest = current_digest
        records = list(stage.execute(records, stage_config))
        scenario_lineage = _extract_scenario_lineage(stage)
        if request.scenario_generation is not None:
            _validate_scenario_stage(
                stage, records, scenario_lineage, request.scenario_generation,
            )
        fallback = _extract_fallback(stage, request)
        final_fallback = fallback or final_fallback
        provenance = DatasetProvenanceRecord(materializer="local-recipe", job_id=job_id)
        quality = evaluate_quality(records)
        checkpoint = checkpoints.save(
            stage_name=recipe_stage.name, stage_index=index, input_digest=input_digest,
            records=records, schema_version=recipe.schema_version,
            adapter_version=stage.stage_version, config=recipe_stage.config,
            context_snapshot_digest=context_digest,
            tool_schema_snapshot_digest=tool_digest, provenance=provenance,
            quality_results=quality, fallback=fallback, record_schema=record_schema,
            scenario_lineage=scenario_lineage,
        )
        final_quality, final_provenance = quality, provenance
        stage_versions[recipe_stage.name] = checkpoint.adapter_version
        stage_lineage.append(checkpoint)
        current_digest = checkpoint.output_digest

    if check_running is not None:
        check_running()
    return (
        records, stage_versions, final_provenance, final_quality,
        final_fallback, stage_lineage,
    )


def _validate_scenario_stage(
    stage,
    records: list[Any],
    lineage: ScenarioPackLineage | None,
    expected: ScenarioPackGenerationInput,
) -> None:
    if lineage is None or (
        lineage.scenario_pack != expected.scenario_pack
        or lineage.generator_adapter != expected.generator_adapter
        or lineage.generator_version != expected.generator_version
        or lineage.seed != expected.seed
    ):
        raise ScenarioGenerationError(
            "Scenario stage lineage does not match the submitted request"
        )
    validator = getattr(stage, "validate_lineage", None)
    if not callable(validator):
        raise ScenarioGenerationError(
            "scenario_generate stage must validate canonical lineage"
        )
    validator(records, lineage)


def _extract_scenario_lineage(stage) -> ScenarioPackLineage | None:
    value = getattr(stage, "scenario_lineage", None)
    if value is None or isinstance(value, ScenarioPackLineage):
        return value
    return ScenarioPackLineage.model_validate(value)


def _extract_fallback(stage, request: DatasetGenerationRequest) -> DatasetFallbackRecord | None:
    fallback = getattr(stage, "fallback_record", None)
    if fallback is None:
        return None
    if not isinstance(fallback, DatasetFallbackRecord):
        fallback = DatasetFallbackRecord.model_validate(fallback)
    require_authorized_fallback(request, fallback)
    return fallback


def require_authorized_fallback(
    request: DatasetGenerationRequest, fallback: DatasetFallbackRecord,
) -> None:
    if not fallback.authorized:
        raise ValueError("Stage fallback must be explicitly authorized")
    if fallback.actual_backend not in request.execution_policy.allowed_fallbacks:
        raise ValueError("Stage fallback backend is not allowed by policy")


def _load_checkpoint_records(
    checkpoint: DatasetStageCheckpoint,
    record_schema: str,
    checkpoint_root: Path,
    job_id: str,
    *,
    require_digest: bool,
) -> list[Any]:
    from .checkpoint_integrity import (
        checked_output_path, validate_checkpoint_metadata,
    )
    output_path = checked_output_path(checkpoint, checkpoint_root, record_schema)
    from .atomic_io import read_bytes_no_follow
    try:
        content = read_bytes_no_follow(output_path)
    except OSError:
        raise ValueError("Stage checkpoint output is missing") from None
    if _sha256(content) != checkpoint.output_digest:
        raise ValueError("Stage checkpoint output digest does not match")
    records = [json.loads(content)] if record_schema == "can_artifact" else [
        json.loads(line) for line in content.decode().splitlines() if line.strip()
    ]
    validated = list(dispatch_validator(records, record_schema=record_schema))
    validate_checkpoint_metadata(
        checkpoint, validated, job_id=job_id, require_digest=require_digest,
    )
    return validated
