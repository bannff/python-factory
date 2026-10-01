"""Train the held-out fold-0 grayscale model and export pure-Python JSON weights."""

from __future__ import annotations

import hashlib
import io
import json
import pickle
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from model import FEATURE_COUNT, FEATURE_KIND, MODEL_KIND, features_from_bytes

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[4].parent / "edge_vision" / "sources"
OUTPUT = ROOT / "model-fold0.json"
SEED = 41
PINNED = {
    "KolektorSDD.zip": "65dc621693418585de9c4467d1340ea7958a6181816f0dc2883a1e8b61f9d4dc",
    "KolektorSDD-training-splits.zip": "8ec637bf01be6d97254d9885abea9e5f32eda0387ebc356be24ab6bc0c3b0db2",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(unsigned: dict) -> bytes:
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def load_dataset() -> tuple[list[dict], list[str], list[str]]:
    source_bytes = {name: (SOURCE / name).read_bytes() for name in PINNED}
    for name, data in source_bytes.items():
        actual = _sha256(data)
        if actual != PINNED[name]:
            raise ValueError(f"source SHA-256 mismatch for {name}: {actual}")
    with zipfile.ZipFile(io.BytesIO(source_bytes["KolektorSDD.zip"])) as archive:
        members = sorted(name for name in archive.namelist() if name.endswith(".jpg"))
        rows = []
        for name in members:
            raw = archive.read(name)
            mask = np.asarray(Image.open(io.BytesIO(archive.read(name[:-4] + "_label.bmp"))).convert("L"))
            rows.append({
                "image_bytes": raw,
                "features": features_from_bytes(raw),
                "item": name.split("/")[0],
                "label": int(mask.max() > 0),
                "path": name,
                "image_sha256": _sha256(raw),
            })
    with zipfile.ZipFile(io.BytesIO(source_bytes["KolektorSDD-training-splits.zip"])) as archive:
        train_folds, test_folds, all_items = pickle.loads(archive.read("split.pyb"))
    if len(rows) != 399 or sum(row["label"] for row in rows) != 52:
        raise ValueError("source dataset row count or labels differ from the frozen pilot")
    dataset_items = {row["item"] for row in rows}
    if dataset_items != set(all_items) or set(train_folds[0]) != dataset_items - set(test_folds[0]):
        raise ValueError("official fold 0 does not match the expected group-disjoint split")
    if set(train_folds[0]) != set(test_folds[1]) | set(test_folds[2]):
        raise ValueError("fold-0 training cohort is not exactly official folds 1 and 2")
    return rows, train_folds[0], test_folds[0]


def run() -> dict:
    rows, train_items, held_out_items = load_dataset()
    training = [row for row in rows if row["item"] in set(train_items)]
    held_out = [row for row in rows if row["item"] in set(held_out_items)]
    x_train = np.asarray([row["features"] for row in training], dtype=np.float64)
    y_train = np.asarray([row["label"] for row in training], dtype=np.int64)
    x_test = np.asarray([row["features"] for row in held_out], dtype=np.float64)
    y_test = np.asarray([row["label"] for row in held_out], dtype=np.int64)
    head = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=0.1, class_weight="balanced", max_iter=2000, random_state=SEED),
    )
    head.fit(x_train, y_train)
    probabilities = head.predict_proba(x_test)[:, 1]
    tn, fp, fn, tp = confusion_matrix(y_test, probabilities >= 0.5, labels=[0, 1]).ravel()
    scaler = head.named_steps["standardscaler"]
    classifier = head.named_steps["logisticregression"]
    training_rows = sorted(
        ({"path": row["path"], "item": row["item"], "label": row["label"], "image_sha256": row["image_sha256"]}
         for row in training),
        key=lambda row: row["path"],
    )
    archive_sha = _sha256((SOURCE / "KolektorSDD.zip").read_bytes())
    split_sha = _sha256((SOURCE / "KolektorSDD-training-splits.zip").read_bytes())
    artifact = {
        "schema_version": 1,
        "kind": MODEL_KIND,
        "feature_kind": FEATURE_KIND,
        "feature_count": FEATURE_COUNT,
        "threshold": 0.5,
        "scaler_mean": scaler.mean_.astype(float).tolist(),
        "scaler_scale": scaler.scale_.astype(float).tolist(),
        "coefficients": classifier.coef_[0].astype(float).tolist(),
        "intercept": float(classifier.intercept_[0]),
        "training_folds": [1, 2],
        "training_rows": len(training),
        "training_items": len(train_items),
        "source_sha256": archive_sha,
        "split_sha256": split_sha,
        "training_data_sha256": _sha256(_canonical({"rows": training_rows})),
    }
    artifact["sha256"] = hashlib.sha256(_canonical(artifact)).hexdigest()
    OUTPUT.write_bytes(json.dumps(artifact, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n")
    metrics = {
        "held_out_fold": 0,
        "training_rows": len(training),
        "training_items": len(train_items),
        "held_out_rows": len(held_out),
        "held_out_items": len(held_out_items),
        "held_out_positives": int(y_test.sum()),
        "average_precision": float(average_precision_score(y_test, probabilities)),
        "auroc": float(roc_auc_score(y_test, probabilities)),
        "threshold_0_5": {"tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)},
        "artifact_bytes": OUTPUT.stat().st_size,
        "artifact_sha256": _sha256(OUTPUT.read_bytes()),
    }
    print(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
