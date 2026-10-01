"""Compare supplied scores against trace IDs bound to a frozen dataset manifest."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .contracts import StrictContract


class Prediction(StrictContract):
    sample_id: str = Field(min_length=1, max_length=160)
    score: float = Field(allow_inf_nan=False)


class PredictionSet(StrictContract):
    schema_version: Literal[1]
    predictions: tuple[Prediction, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_samples(self) -> PredictionSet:
        ids = [item.sample_id for item in self.predictions]
        if len(ids) != len(set(ids)):
            raise ValueError("prediction sample IDs must be unique")
        return self


class DatasetSample(StrictContract):
    sample_id: str = Field(min_length=1, max_length=160)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class DatasetManifest(StrictContract):
    schema_version: Literal[1]
    dataset_id: str = Field(min_length=1)
    split: str = Field(min_length=1)
    samples: tuple[DatasetSample, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_samples(self) -> DatasetManifest:
        ids = [item.sample_id for item in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError("dataset sample IDs must be unique")
        return self


def dataset_sample_ids(content: bytes, dataset_id: str) -> list[str]:
    manifest = DatasetManifest.model_validate_json(content)
    if manifest.dataset_id != dataset_id:
        raise ValueError("dataset manifest ID differs from frozen scenario")
    return [item.sample_id for item in manifest.samples]


def measured_max_error(
    native_content: bytes, reference_content: bytes, trace_sample_ids: list[str]
) -> float:
    native = PredictionSet.model_validate_json(native_content)
    reference = PredictionSet.model_validate_json(reference_content)
    native_ids = [item.sample_id for item in native.predictions]
    reference_ids = [item.sample_id for item in reference.predictions]
    if native_ids != reference_ids or native_ids != trace_sample_ids:
        raise ValueError("prediction sample IDs do not match the inference trace")
    return max(
        abs(left.score - right.score)
        for left, right in zip(native.predictions, reference.predictions, strict=True)
    )
