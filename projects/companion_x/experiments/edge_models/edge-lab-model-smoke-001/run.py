"""Export the frozen FD001 logistic baseline and benchmark its stdlib inference.

The export command runs on the host with numpy, scikit-learn, and joblib.
The infer command needs only Python's standard library inside edge-lab.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import statistics
import struct
import sys
import time
from pathlib import Path

WINDOW = 20
CHANNELS = 24
FEATURES = WINDOW * CHANNELS
THRESHOLD = 0.7392553708788053
ARCHIVE_SHA256 = "74bef434a34db25c7bf72e668ea4cd52afe5f2cf8e44367c55a82bfd91a5a34f"
JOBLIB_SHA256 = "6dbb0b9b37e6640322048ecd965cfc72eda00e2564915e2a6f9b1125576a74e8"
DEFAULT_ARCHIVE = Path("/Users/danielrodrigo/Documents/Codex/2026-09-29/onbo/work/data/CMAPSSData.zip")
DEFAULT_JOBLIB = Path("/Users/danielrodrigo/Documents/Codex/2026-09-29/onbo/work/runs/edge-engine-failure-001/logistic/logistic_baseline.joblib")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def payload_sha256(payload: dict) -> str:
    content = {key: value for key, value in payload.items() if key != "sha256"}
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def export(archive_path: Path, joblib_path: Path, model_path: Path, cohort_path: Path) -> None:
    # joblib uses pickle: load only the exact frozen artifact trusted for this run.
    if file_sha256(joblib_path) != JOBLIB_SHA256:
        raise ValueError("frozen joblib SHA-256 mismatch")
    if file_sha256(archive_path) != ARCHIVE_SHA256:
        raise ValueError("FD001 archive SHA-256 mismatch")

    import io
    import zipfile

    import joblib
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    pipeline = joblib.load(joblib_path)
    if not isinstance(pipeline, Pipeline) or len(pipeline.steps) != 2:
        raise ValueError("expected a two-step sklearn Pipeline")
    scaler, classifier = (step for _, step in pipeline.steps)
    if not isinstance(scaler, StandardScaler) or not isinstance(classifier, LogisticRegression):
        raise ValueError("expected StandardScaler then LogisticRegression")
    if (not scaler.with_mean or not scaler.with_std or classifier.classes_.tolist() != [0, 1]
            or classifier.coef_.shape != (1, FEATURES) or classifier.intercept_.shape != (1,)
            or scaler.mean_.shape != (FEATURES,) or scaler.scale_.shape != (FEATURES,)):
        raise ValueError("unexpected fitted model shape or class order")
    if (not np.isfinite(scaler.mean_).all() or not np.isfinite(scaler.scale_).all()
            or (scaler.scale_ <= 0).any() or not np.isfinite(classifier.coef_).all()
            or not np.isfinite(classifier.intercept_).all()):
        raise ValueError("non-finite or invalid fitted model parameters")

    with zipfile.ZipFile(archive_path) as archive:
        rows = np.loadtxt(io.BytesIO(archive.read("test_FD001.txt")), dtype=np.float64)
        rul = np.loadtxt(io.BytesIO(archive.read("RUL_FD001.txt")), dtype=np.float64)
    if (rows.ndim != 2 or rows.shape[1] != CHANNELS + 2 or not np.isfinite(rows).all()
            or rul.shape != (100,) or not np.isfinite(rul).all()
            or not np.array_equal(rul, rul.astype(int)) or (rul < 0).any()):
        raise ValueError("invalid FD001 test table or RUL")
    ids, cycles = rows[:, 0], rows[:, 1]
    if not np.array_equal(ids, ids.astype(int)) or not np.array_equal(cycles, cycles.astype(int)):
        raise ValueError("engine IDs and cycles must be integers")
    if set(ids.astype(int)) != set(range(1, 101)):
        raise ValueError("expected official test engine IDs 1..100")
    vectors = []
    for engine_id in range(1, 101):
        own = rows[ids == engine_id]
        if len(own) < WINDOW or not np.array_equal(own[:, 1], np.arange(1, len(own) + 1)):
            raise ValueError(f"engine {engine_id} has too few or nonsequential cycles")
        vectors.append(own[-WINDOW:, 2:].astype(np.float32).reshape(FEATURES))
    features = np.stack(vectors)
    probabilities = pipeline.predict_proba(features)[:, 1]

    model = {
        "schema_version": 2, "kind": "fd001_scaled_logistic", "window_cycles": WINDOW,
        "channels_per_cycle": CHANNELS, "feature_count": FEATURES, "threshold": THRESHOLD,
        "scaler_mean": scaler.mean_.tolist(), "scaler_scale": scaler.scale_.tolist(),
        "coefficients": classifier.coef_[0].tolist(), "intercept": float(classifier.intercept_[0]),
        "source_archive_sha256": ARCHIVE_SHA256, "source_joblib_sha256": JOBLIB_SHA256,
    }
    model["sha256"] = payload_sha256(model)
    cohort = {
        "schema_version": 2, "kind": "fd001_official_test_endpoints",
        "model_sha256": model["sha256"], "source_archive_sha256": ARCHIVE_SHA256,
        "rows": [{"engine_id": engine_id, "features": vector.tolist(),
                  "expected_probability": float(probability),
                  "expected_decision": int(probability >= THRESHOLD),
                  "rul_label": int(rul[engine_id - 1] <= 30)}
                 for engine_id, (vector, probability) in enumerate(zip(features, probabilities, strict=True), 1)],
    }
    cohort["sha256"] = payload_sha256(cohort)
    write_json(model_path, model)
    write_json(cohort_path, cohort)
    print(json.dumps({"model_sha256": model["sha256"], "cohort_sha256": cohort["sha256"],
                      "engines": len(cohort["rows"])}))


def finite_number(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def read_payload(path: Path) -> dict:
    payload = json.loads(path.read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(payload, dict) or payload.get("sha256") != payload_sha256(payload):
        raise ValueError(f"invalid JSON payload hash: {path}")
    return payload


def validate(model: dict, cohort: dict) -> tuple[list[float], list[float], list[float], float, float, list[dict]]:
    if (model.get("schema_version") != 2 or model.get("kind") != "fd001_scaled_logistic"
            or model.get("window_cycles") != WINDOW or model.get("channels_per_cycle") != CHANNELS
            or model.get("feature_count") != FEATURES
            or model.get("source_archive_sha256") != ARCHIVE_SHA256
            or model.get("source_joblib_sha256") != JOBLIB_SHA256):
        raise ValueError("invalid model schema or frozen source hashes")
    means, scales = model.get("scaler_mean"), model.get("scaler_scale")
    weights, intercept, threshold = model.get("coefficients"), model.get("intercept"), model.get("threshold")
    if (not isinstance(weights, list) or len(weights) != FEATURES
            or not all(map(finite_number, weights)) or not finite_number(intercept)
            or not isinstance(means, list) or len(means) != FEATURES
            or not all(map(finite_number, means))
            or not isinstance(scales, list) or len(scales) != FEATURES
            or not all(finite_number(scale) and scale > 0 for scale in scales)
            or not finite_number(threshold) or threshold != THRESHOLD):
        raise ValueError("invalid logistic parameters")
    rows = cohort.get("rows")
    if (cohort.get("schema_version") != 2 or cohort.get("kind") != "fd001_official_test_endpoints"
            or cohort.get("model_sha256") != model["sha256"]
            or cohort.get("source_archive_sha256") != ARCHIVE_SHA256
            or not isinstance(rows, list) or len(rows) != 100):
        raise ValueError("invalid cohort schema or source linkage")
    for engine_id, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("engine_id") != engine_id:
            raise ValueError("invalid engine ID ordering")
        vector = row.get("features")
        probability = row.get("expected_probability")
        if (not isinstance(vector, list) or len(vector) != FEATURES
                or not all(map(finite_number, vector)) or not finite_number(probability)
                or not 0 <= probability <= 1
                or type(row.get("expected_decision")) is not int
                or row["expected_decision"] not in (0, 1)
                or row["expected_decision"] != int(probability >= threshold)
                or type(row.get("rul_label")) is not int or row["rul_label"] not in (0, 1)):
            raise ValueError(f"invalid cohort row {engine_id}")
    return [float32(value) for value in means], [float32(value) for value in scales], weights, intercept, threshold, rows


def float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def probability(vector: list[float], means: list[float], scales: list[float],
                weights: list[float], intercept: float) -> float:
    transformed = (float32(float32(value - mean) / scale)
                   for value, mean, scale in zip(vector, means, scales, strict=True))
    score = math.fsum((intercept, *(weight * value for weight, value in zip(weights, transformed, strict=True))))
    if score >= 0:
        return 1.0 / (1.0 + math.exp(-score))
    value = math.exp(score)
    return value / (1.0 + value)


def cgroup_peak_bytes() -> int | None:
    for path in (Path("/sys/fs/cgroup/memory.peak"), Path("/sys/fs/cgroup/memory/memory.max_usage_in_bytes")):
        try:
            return int(path.read_text().strip())
        except (OSError, ValueError):
            continue
    return None


def cgroup_current_bytes() -> int | None:
    try:
        return int(Path("/sys/fs/cgroup/memory.current").read_text().strip())
    except (OSError, ValueError):
        return None


def infer(model_path: Path, cohort_path: Path, output_path: Path, repeats: int) -> bool:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    model, cohort = read_payload(model_path), read_payload(cohort_path)
    means, scales, weights, intercept, threshold, rows = validate(model, cohort)
    memory_before = cgroup_current_bytes()
    scores = [probability(row["features"], means, scales, weights, intercept) for row in rows]
    error = max(abs(score - row["expected_probability"]) for score, row in zip(scores, rows, strict=True))
    decisions = sum(int(score >= threshold) == row["expected_decision"] for score, row in zip(scores, rows, strict=True))
    predictions = [
        {"engine_id": row["engine_id"], "observed_probability": score,
         "expected_probability": row["expected_probability"],
         "absolute_error": abs(score - row["expected_probability"]),
         "observed_decision": int(score >= threshold),
         "expected_decision": row["expected_decision"],
         "rul_label": row["rul_label"]}
        for score, row in zip(scores, rows, strict=True)
    ]
    latencies_ns = []
    for _ in range(repeats):
        for row in rows:
            start = time.perf_counter_ns()
            probability(row["features"], means, scales, weights, intercept)
            latencies_ns.append(time.perf_counter_ns() - start)
    ordered = sorted(latencies_ns)
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    memory_after = cgroup_current_bytes()
    result = {
        "schema_version": 2, "experiment_id": "edge-lab-model-smoke-001",
        "status": "passed" if error <= 1e-6 and decisions == 100 else "failed",
        "model_sha256": model["sha256"], "cohort_sha256": cohort["sha256"],
        "source_archive_sha256": ARCHIVE_SHA256, "source_joblib_sha256": JOBLIB_SHA256,
        "engines": len(rows), "max_abs_probability_error": error, "matching_decisions": decisions,
        "predictions": predictions,
        "probability_tolerance": 1e-6, "repeats": repeats, "inferences": len(ordered),
        "latency_us": {"p50": statistics.median(ordered) / 1000,
                       "p95": ordered[math.ceil(0.95 * len(ordered)) - 1] / 1000},
        "process_peak_rss_bytes": peak_rss * (1024 if sys.platform.startswith("linux") else 1),
        "cgroup_memory_before_bytes": memory_before,
        "cgroup_memory_after_bytes": memory_after,
        "cgroup_peak_bytes": cgroup_peak_bytes(),
    }
    write_json(output_path, result)
    print(json.dumps({key: value for key, value in result.items() if key != "predictions"}, sort_keys=True))
    return result["status"] == "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    host = commands.add_parser("export", help="convert the pinned sklearn model and official FD001 cohort")
    host.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    host.add_argument("--joblib", type=Path, default=DEFAULT_JOBLIB)
    host.add_argument("--model", type=Path, required=True)
    host.add_argument("--cohort", type=Path, required=True)
    edge = commands.add_parser("infer", help="check parity and benchmark inside edge-lab")
    edge.add_argument("--model", type=Path, required=True)
    edge.add_argument("--cohort", type=Path, required=True)
    edge.add_argument("--output", type=Path, required=True)
    edge.add_argument("--repeats", type=int, default=100)
    options = parser.parse_args()
    if options.command == "export":
        export(options.archive, options.joblib, options.model, options.cohort)
        return 0
    return 0 if infer(options.model, options.cohort, options.output, options.repeats) else 1


if __name__ == "__main__":
    raise SystemExit(main())
