"""Integrity checks for immutable stage checkpoint metadata and output paths."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from .contracts import DatasetProvenanceRecord, DatasetStageCheckpoint
from .quality import evaluate_quality
from .recipe import path_from_uri

RecordSchema = Literal["conversation", "can_frame", "can_artifact", "generic"]


def checkpoint_metadata_digest(checkpoint: DatasetStageCheckpoint) -> str:
    """Digest all semantic checkpoint metadata except the digest itself."""
    payload = checkpoint.model_dump(
        mode="json", exclude={"checkpoint_digest"}, exclude_none=True,
    )
    content = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode()
    return hashlib.sha256(content).hexdigest()


def checked_output_path(
    checkpoint: DatasetStageCheckpoint, root: Path, record_schema: RecordSchema,
) -> Path:
    """Constrain a resumed output to its exact content-addressed stage path."""
    suffix = ".json" if record_schema == "can_artifact" else ".jsonl"
    expected = (
        root / f"stage-{checkpoint.stage_index}-{checkpoint.output_digest}{suffix}"
    ).resolve()
    actual = path_from_uri(checkpoint.output_uri)
    if actual != expected:
        raise ValueError("Stage checkpoint output is outside its immutable store")
    return actual


def validate_checkpoint_metadata(
    checkpoint: DatasetStageCheckpoint,
    records: list[Any],
    *,
    job_id: str,
    require_digest: bool,
) -> None:
    """Recompute derived metadata and verify the checkpoint's self-digest."""
    if checkpoint.record_count != len(records):
        raise ValueError("Stage checkpoint record count does not match output")
    if checkpoint.quality_results != evaluate_quality(records):
        raise ValueError("Stage checkpoint quality results do not match output")
    expected_provenance = DatasetProvenanceRecord(
        materializer="local-recipe", job_id=job_id,
    )
    if checkpoint.provenance != expected_provenance:
        raise ValueError("Stage checkpoint provenance does not match current job")
    if checkpoint.checkpoint_digest is None:
        if require_digest:
            raise ValueError("Scenario stage checkpoint metadata digest is missing")
        return
    if checkpoint_metadata_digest(checkpoint) != checkpoint.checkpoint_digest:
        raise ValueError("Stage checkpoint metadata digest does not match")
