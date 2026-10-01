from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import struct
import sys
import unittest
import zlib
from pathlib import Path

import numpy as np
from PIL import Image

EXPERIMENT = Path(__file__).parents[1] / "experiments/edge_models/edge-visual-quality-mesh-001"
sys.path.insert(0, str(EXPERIMENT))
import model  # noqa: E402


def _reference_features(image_bytes: bytes) -> list[float]:
    """Independent NumPy transcription of the frozen feature contract."""
    with Image.open(io.BytesIO(image_bytes)) as image:
        pixels = np.asarray(image.convert("L").resize((64, 160)), dtype=np.float32) / 255.0
    parts = []
    for crop in np.array_split(pixels, 3, axis=0):
        dx = np.abs(np.diff(crop, axis=1))
        dy = np.abs(np.diff(crop, axis=0))
        parts.extend(np.histogram(crop, bins=16, range=(0, 1), density=True)[0])
        parts.extend(np.quantile(crop, [0, .01, .1, .25, .5, .75, .9, .99, 1]))
        parts.extend(np.quantile(dx, [.5, .9, .99, 1]))
        parts.extend(np.quantile(dy, [.5, .9, .99, 1]))
    # The deployed host reference explicitly casts its completed feature row to float32.
    return np.asarray(parts, dtype=np.float32).tolist()


def _valid_artifact() -> dict:
    artifact = {
        "schema_version": 1,
        "kind": model.MODEL_KIND,
        "feature_kind": model.FEATURE_KIND,
        "feature_count": model.FEATURE_COUNT,
        "threshold": 0.5,
        "scaler_mean": [0.1] * model.FEATURE_COUNT,
        "scaler_scale": [1.3] * model.FEATURE_COUNT,
        "coefficients": [((index % 7) - 3) / 25 for index in range(model.FEATURE_COUNT)],
        "intercept": -0.17,
        "training_folds": [1, 2],
        "training_rows": 264,
        "training_items": 33,
        "source_sha256": "a" * 64,
        "split_sha256": "b" * 64,
        "training_data_sha256": "c" * 64,
    }
    unsigned = json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    artifact["sha256"] = hashlib.sha256(unsigned).hexdigest()
    return artifact


class EdgeVisualQualityModelTests(unittest.TestCase):
    def test_original_image_bytes_features_and_probability_match_reference(self) -> None:
        y, x = np.indices((81, 147))
        source = ((x * 13 + y * 29 + ((x // 8 + y // 5) % 2) * 71) % 256).astype(np.uint8)
        stream = io.BytesIO()
        Image.fromarray(source, mode="L").save(stream, format="PNG")
        image_bytes = stream.getvalue()
        expected_features = _reference_features(image_bytes)

        actual_features = model.features_from_bytes(image_bytes)
        np.testing.assert_array_equal(np.asarray(actual_features, dtype=np.float32), expected_features)
        self.assertEqual(len(actual_features), model.FEATURE_COUNT)

        artifact = model.load_artifact(_valid_artifact())
        expected_logit = artifact["intercept"] + np.sum(
            np.asarray(artifact["coefficients"])
            * ((np.asarray(expected_features) - artifact["scaler_mean"]) / artifact["scaler_scale"])
        )
        expected_probability = 1 / (1 + np.exp(-expected_logit))
        prediction = model.predict_image(image_bytes, artifact)
        self.assertAlmostEqual(prediction["probability"], float(expected_probability), places=14)
        self.assertEqual(prediction["decision"], int(expected_probability >= artifact["threshold"]))

    def test_generated_fold0_artifact_loads_as_strict_versioned_weights(self) -> None:
        artifact_path = EXPERIMENT / "model-fold0.json"
        self.assertTrue(artifact_path.exists(), "run train.py before this test")
        artifact = model.load_artifact(artifact_path)
        self.assertEqual(artifact["training_folds"], [1, 2])
        self.assertEqual(artifact["feature_count"], 99)
        self.assertEqual(artifact["training_rows"], 264)
        self.assertNotIn("joblib", artifact)

    def test_artifact_schema_rejects_unknown_fields_wrong_fold_and_modified_digest(self) -> None:
        artifact = _valid_artifact()
        with self.assertRaisesRegex(ValueError, "strict schema"):
            model.load_artifact({**artifact, "unexpected": True})

        wrong_fold = copy.deepcopy(artifact)
        wrong_fold["training_folds"] = [0, 1, 2]
        unsigned = {key: value for key, value in wrong_fold.items() if key != "sha256"}
        wrong_fold["sha256"] = hashlib.sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "folds 1 and 2"):
            model.load_artifact(wrong_fold)

        modified = copy.deepcopy(artifact)
        modified["coefficients"][0] += 0.01
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            model.load_artifact(modified)

        duplicate = json.dumps(artifact, separators=(",", ":")).replace('"kind":', '"kind":"other","kind":', 1)
        with self.assertRaisesRegex(ValueError, "duplicate artifact key"):
            model.load_artifact(duplicate)

    def test_image_byte_and_dimension_budgets_reject_before_pixel_decode(self) -> None:
        with self.assertRaisesRegex(ValueError, "image bytes exceed"):
            model.features_from_bytes(b"x" * (model.MAX_IMAGE_BYTES + 1))

        def png_header(width: int, height: int) -> bytes:
            def chunk(kind: bytes, payload: bytes) -> bytes:
                body = kind + payload
                return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

            ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
            return (
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(b"\x00\x00"))
                + chunk(b"IEND", b"")
            )

        for width, height in (
            (model.MAX_IMAGE_DIMENSION + 1, 1),
            (4000, 4001),
        ):
            with self.subTest(width=width, height=height):
                with self.assertRaisesRegex(ValueError, "image dimensions exceed"):
                    model.features_from_bytes(png_header(width, height))

    def test_invalid_image_bytes_and_nonfinite_features_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "could not be decoded"):
            model.features_from_bytes(b"not an image")
        with self.assertRaisesRegex(ValueError, "99 finite values"):
            model.predict_features([float("nan")] * model.FEATURE_COUNT, _valid_artifact())


if __name__ == "__main__":
    unittest.main()
