"""Small, dependency-light image features and logistic inference for edge peers."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

SCHEMA_VERSION = 1
MODEL_KIND = "grayscale-statistics-logistic"
FEATURE_KIND = "grayscale-statistics-64x160-v1"
FEATURE_COUNT = 99
FEATURE_QUANTILES = (0, 0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.99, 1)
DELTA_QUANTILES = (0.5, 0.9, 0.99, 1)
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_DIMENSION = 8192
MAX_IMAGE_PIXELS = 16_000_000
_ARTIFACT_FIELDS = {
    "schema_version", "kind", "feature_kind", "feature_count", "threshold",
    "scaler_mean", "scaler_scale", "coefficients", "intercept",
    "training_folds", "training_rows", "training_items", "source_sha256",
    "split_sha256", "training_data_sha256", "sha256",
}


class _ImageDimensionsError(ValueError):
    """An image header exceeds the peer's decode budget."""


def _quantile(values: list[float], quantile: float) -> float:
    """Match NumPy's default linear quantile interpolation for finite values."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _histogram(values: list[float]) -> list[float]:
    counts = [0] * 16
    for value in values:
        # NumPy histogram uses a closed right edge for the final bin.
        index = min(15, int(value * 16))
        counts[index] += 1
    scale = 16.0 / len(values)
    return [count * scale for count in counts]


def features_from_bytes(image_bytes: bytes) -> list[float]:
    """Decode original image bytes and reproduce the pilot's 99 image features."""
    if not isinstance(image_bytes, bytes) or not image_bytes:
        raise ValueError("image must be non-empty bytes")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("image bytes exceed the configured limit")
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
            if (
                width <= 0
                or height <= 0
                or width > MAX_IMAGE_DIMENSION
                or height > MAX_IMAGE_DIMENSION
                or width * height > MAX_IMAGE_PIXELS
            ):
                raise _ImageDimensionsError("image dimensions exceed the configured limit")
            gray = image.convert("L").resize((64, 160))
            pixels = [struct.unpack("f", struct.pack("f", value / 255.0))[0] for value in gray.tobytes()]
    except _ImageDimensionsError:
        raise
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ValueError("image bytes could not be decoded") from exc

    rows = [pixels[offset : offset + 64] for offset in range(0, len(pixels), 64)]
    # np.array_split(..., 3, axis=0) assigns the remainder to the first chunk.
    chunks = [rows[:54], rows[54:107], rows[107:]]
    result: list[float] = []
    for chunk in chunks:
        gray_values = [pixel for row in chunk for pixel in row]
        dx = [
            struct.unpack("f", struct.pack("f", abs(right - left)))[0]
            for row in chunk
            for left, right in zip(row, row[1:])
        ]
        dy = [
            struct.unpack("f", struct.pack("f", abs(chunk[row + 1][column] - chunk[row][column])))[0]
            for row in range(len(chunk) - 1)
            for column in range(64)
        ]
        result.extend(_histogram(gray_values))
        result.extend(_quantile(gray_values, q) for q in FEATURE_QUANTILES)
        result.extend(_quantile(dx, q) for q in DELTA_QUANTILES)
        result.extend(_quantile(dy, q) for q in DELTA_QUANTILES)
    if len(result) != FEATURE_COUNT:
        raise AssertionError(f"unexpected feature count: {len(result)}")
    # The frozen host reference ends with np.asarray(features, dtype=np.float32).
    # Quantize every feature here so peer-side scoring receives identical values.
    return [struct.unpack("f", struct.pack("f", value))[0] for value in result]


def _canonical_payload(artifact: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in artifact.items() if key != "sha256"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate artifact key: {key}")
        result[key] = value
    return result


def load_artifact(source: bytes | str | Path | dict[str, Any]) -> dict[str, Any]:
    """Load and strictly validate the compact, versioned JSON model artifact."""
    if isinstance(source, Path):
        artifact = json.loads(source.read_text(), object_pairs_hook=_reject_duplicate_keys)
    elif isinstance(source, bytes):
        artifact = json.loads(source, object_pairs_hook=_reject_duplicate_keys)
    elif isinstance(source, str):
        artifact = json.loads(source, object_pairs_hook=_reject_duplicate_keys)
    elif isinstance(source, dict):
        artifact = source
    else:
        raise TypeError("artifact must be JSON bytes, text, a path, or a mapping")
    if type(artifact) is not dict or set(artifact) != _ARTIFACT_FIELDS:
        raise ValueError("artifact fields do not match the strict schema")
    if type(artifact["schema_version"]) is not int or artifact["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported artifact schema version")
    if artifact["kind"] != MODEL_KIND or artifact["feature_kind"] != FEATURE_KIND:
        raise ValueError("unsupported model or feature kind")
    if type(artifact["feature_count"]) is not int or artifact["feature_count"] != FEATURE_COUNT:
        raise ValueError("feature count does not match feature contract")
    for field in ("scaler_mean", "scaler_scale", "coefficients"):
        values = artifact[field]
        if type(values) is not list or len(values) != FEATURE_COUNT:
            raise ValueError(f"{field} must contain {FEATURE_COUNT} values")
        if any(type(value) not in (float, int) or not math.isfinite(value) for value in values):
            raise ValueError(f"{field} must contain finite numbers")
    if any(value <= 0 for value in artifact["scaler_scale"]):
        raise ValueError("scaler scales must be positive")
    if type(artifact["intercept"]) not in (int, float) or not math.isfinite(artifact["intercept"]):
        raise ValueError("intercept must be finite")
    if type(artifact["threshold"]) not in (int, float) or not 0 <= artifact["threshold"] <= 1:
        raise ValueError("threshold must be between zero and one")
    if (
        type(artifact["training_folds"]) is not list
        or any(type(fold) is not int for fold in artifact["training_folds"])
        or artifact["training_folds"] != [1, 2]
    ):
        raise ValueError("artifact must be trained on published folds 1 and 2 only")
    if type(artifact["training_rows"]) is not int or artifact["training_rows"] <= 0:
        raise ValueError("training_rows must be a positive integer")
    if type(artifact["training_items"]) is not int or artifact["training_items"] <= 0:
        raise ValueError("training_items must be a positive integer")
    for field in ("source_sha256", "split_sha256", "training_data_sha256", "sha256"):
        value = artifact[field]
        if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    expected = hashlib.sha256(_canonical_payload(artifact)).hexdigest()
    if artifact["sha256"] != expected:
        raise ValueError("artifact payload SHA-256 mismatch")
    return artifact


def predict_features(features: list[float], artifact: dict[str, Any]) -> float:
    """Return the positive-class probability using the serialized sklearn head."""
    if len(features) != FEATURE_COUNT or any(not math.isfinite(value) for value in features):
        raise ValueError("features must be 99 finite values")
    model = load_artifact(artifact)
    logit = model["intercept"] + sum(
        coefficient * ((value - mean) / scale)
        for value, mean, scale, coefficient in zip(
            features, model["scaler_mean"], model["scaler_scale"], model["coefficients"]
        )
    )
    if logit >= 0:
        return 1.0 / (1.0 + math.exp(-logit))
    exp_logit = math.exp(logit)
    return exp_logit / (1.0 + exp_logit)


def predict_image(image_bytes: bytes, artifact: dict[str, Any]) -> dict[str, float | int]:
    features = features_from_bytes(image_bytes)
    probability = predict_features(features, artifact)
    return {"probability": probability, "decision": int(probability >= artifact["threshold"])}
