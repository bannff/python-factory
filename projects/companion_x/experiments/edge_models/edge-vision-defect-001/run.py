"""KolektorSDD image-defect pilot using the authors' three item-disjoint folds."""

from __future__ import annotations

import hashlib
import io
import json
import pickle
import time
import zipfile
from pathlib import Path

import joblib
import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torchvision.models import mobilenet_v3_small

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sources"
SEED = 41
PINNED_SOURCE_SHA256 = {
    "KolektorSDD.zip": "65dc621693418585de9c4467d1340ea7958a6181816f0dc2883a1e8b61f9d4dc",
    "KolektorSDD-training-splits.zip": "8ec637bf01be6d97254d9885abea9e5f32eda0387ebc356be24ab6bc0c3b0db2",
    "mobilenet_v3_small-047dcff4.pth": "047dcff4addef86ea5bc2eff13c9614dc11f47ab1160d0a71a25e7db994f4e1f",
}
torch.manual_seed(SEED)
torch.set_num_threads(4)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sources() -> None:
    # In particular, never unpickle split.pyb until its containing archive is pinned.
    for filename, expected in PINNED_SOURCE_SHA256.items():
        actual = digest(SOURCE / filename)
        if actual != expected:
            raise ValueError(f"source SHA-256 mismatch for {filename}: {actual}")


def load_records():
    with zipfile.ZipFile(SOURCE / "KolektorSDD.zip") as archive:
        names = sorted(n for n in archive.namelist() if n.endswith(".jpg"))
        records = []
        raw = []
        for name in names:
            label_name = name[:-4] + "_label.bmp"
            image = np.asarray(Image.open(io.BytesIO(archive.read(name))).convert("L"))
            mask = np.asarray(Image.open(io.BytesIO(archive.read(label_name))).convert("L"))
            assert image.shape == mask.shape
            records.append({"path": name, "item": name.split("/")[0], "label": int(mask.max() > 0)})
            raw.append(image)
    assert len(records) == 399 and len({r["item"] for r in records}) == 50
    assert sum(r["label"] for r in records) == 52
    return records, raw


def three_crops(image: np.ndarray) -> np.ndarray:
    # Preserve the long surface while fitting three 224-pixel views to a small backbone.
    resized = Image.fromarray(image).resize((224, 560), Image.Resampling.BILINEAR)
    array = np.asarray(resized, dtype=np.float32) / 255.0
    crops = np.stack([array[y : y + 224] for y in (0, 168, 336)])
    rgb = np.repeat(crops[:, None, :, :], 3, axis=1)
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)[None, :, None, None]
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)[None, :, None, None]
    return (rgb - mean) / std


def handcrafted(image: np.ndarray) -> np.ndarray:
    # Fixed, cheap image statistics: grayscale distribution and vertical/horizontal change.
    array = np.asarray(Image.fromarray(image).resize((64, 160)), dtype=np.float32) / 255.0
    parts = []
    for crop in np.array_split(array, 3, axis=0):
        dx = np.abs(np.diff(crop, axis=1))
        dy = np.abs(np.diff(crop, axis=0))
        parts.extend(np.histogram(crop, bins=16, range=(0, 1), density=True)[0])
        parts.extend(np.quantile(crop, [0, .01, .1, .25, .5, .75, .9, .99, 1]))
        parts.extend(np.quantile(dx, [.5, .9, .99, 1]))
        parts.extend(np.quantile(dy, [.5, .9, .99, 1]))
    return np.asarray(parts, dtype=np.float32)


def backbone_features(images: list[np.ndarray]) -> tuple[np.ndarray, float]:
    # Recompute on each run so changed preprocessing or sources cannot reuse stale features.
    model = mobilenet_v3_small(weights=None)
    state = torch.load(SOURCE / "mobilenet_v3_small-047dcff4.pth", map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()
    rows = []
    start = time.perf_counter()
    with torch.inference_mode():
        for i, image in enumerate(images, 1):
            x = torch.from_numpy(three_crops(image))
            pooled = model.avgpool(model.features(x)).flatten(1).numpy()
            rows.append(np.concatenate((pooled.mean(axis=0), pooled.max(axis=0))))
            if i % 50 == 0:
                print(f"embedded {i}/{len(images)}", flush=True)
    elapsed = time.perf_counter() - start
    feats = np.asarray(rows, dtype=np.float32)
    np.save(ROOT / "mobilenet_features.npy", feats)
    return feats, elapsed


def measure(y: np.ndarray, s: np.ndarray) -> dict:
    tn, fp, fn, tp = confusion_matrix(y, s >= .5, labels=[0, 1]).ravel().tolist()
    return {
        "n": int(len(y)), "positives": int(y.sum()),
        "average_precision": float(average_precision_score(y, s)) if len(np.unique(y)) == 2 else None,
        "auroc": float(roc_auc_score(y, s)) if len(np.unique(y)) == 2 else None,
        "threshold_0_5": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def run():
    verify_sources()
    records, images = load_records()
    with zipfile.ZipFile(SOURCE / "KolektorSDD-training-splits.zip") as archive:
        train_folds, test_folds, all_items = pickle.loads(archive.read("split.pyb"))
    assert len(all_items) == 50
    assert set(all_items) == {r["item"] for r in records}
    assert len(set.union(*(set(x) for x in test_folds))) == 50
    assert all(not set(tr) & set(te) for tr, te in zip(train_folds, test_folds))
    with (ROOT / "dataset_records.jsonl").open("w") as stream:
        with zipfile.ZipFile(SOURCE / "KolektorSDD.zip") as archive:
            for record in records:
                member = record["path"]
                stream.write(json.dumps({
                    "archive_uri": str(SOURCE / "KolektorSDD.zip"),
                    "image_member": member,
                    "image_sha256": hashlib.sha256(archive.read(member)).hexdigest(),
                    "mask_member": member[:-4] + "_label.bmp",
                    "item_id": record["item"], "label": record["label"],
                    "fold_test": [i for i, test_items in enumerate(test_folds) if record["item"] in test_items][0],
                }, sort_keys=True) + "\n")
    mobile, embed_seconds = backbone_features(images)
    simple = np.stack([handcrafted(im) for im in images])
    y = np.array([r["label"] for r in records])
    items = np.array([r["item"] for r in records])
    result = {}
    score_rows = []
    final_head_artifacts = {}
    for name, x in (("grayscale_statistics", simple), ("mobilenet_v3_small", mobile)):
        out = np.full(len(y), np.nan)
        folds = []
        for fold, (train_items, test_items) in enumerate(zip(train_folds, test_folds)):
            train = np.isin(items, train_items)
            test = np.isin(items, test_items)
            assert train.sum() + test.sum() == len(y)
            head = make_pipeline(StandardScaler(), LogisticRegression(C=.1, class_weight="balanced", max_iter=2000, random_state=SEED))
            head.fit(x[train], y[train])
            scores = head.predict_proba(x[test])[:, 1]
            out[test] = scores
            folds.append({"fold": fold, "train_items": len(train_items), "test_items": len(test_items), "image": measure(y[test], scores)})
        assert np.isfinite(out).all()
        result[name] = {"folds": folds, "out_of_fold_image": measure(y, out)}
        score_rows.append(out)
        final_head = make_pipeline(StandardScaler(), LogisticRegression(C=.1, class_weight="balanced", max_iter=2000, random_state=SEED))
        final_head.fit(x, y)
        artifact = ROOT / f"{name}_final_head.joblib"
        joblib.dump(final_head, artifact)
        final_head_artifacts[name] = {"path": str(artifact), "sha256": digest(artifact), "evaluation_use": "none; fitted on all 399 images only after cross-validation"}
    rng = np.random.default_rng(SEED)
    differences = []
    for _ in range(5000):
        sampled_items = rng.choice(np.asarray(all_items), size=len(all_items), replace=True)
        indices = np.concatenate([np.flatnonzero(items == item) for item in sampled_items])
        if len(np.unique(y[indices])) == 2:
            differences.append(average_precision_score(y[indices], score_rows[1][indices]) - average_precision_score(y[indices], score_rows[0][indices]))
    diff_ci = np.quantile(differences, [.025, .5, .975]).tolist()
    np.savez_compressed(ROOT / "scores.npz", paths=np.array([r["path"] for r in records]), items=items, labels=y,
                        grayscale_statistics=score_rows[0], mobilenet_v3_small=score_rows[1])
    manifest = {
        "id": "edge-vision-kolektorsdd-001", "status": "research_pilot", "seed": SEED,
        "dataset": {"name": "KolektorSDD", "source": "https://www.vicos.si/resources/kolektorsdd/",
                    "archive_sha256": digest(SOURCE / "KolektorSDD.zip"),
                    "split_sha256": digest(SOURCE / "KolektorSDD-training-splits.zip"),
                    "license": "CC BY-NC-SA 4.0; research only; commercial use requires owner contact",
                    "images": len(records), "positive_images": int(y.sum()), "items": len(all_items),
                    "official_split_file": "split.pyb", "split_group": "production item (kosXX)",
                    "dataset_records_sha256": digest(ROOT / "dataset_records.jsonl")},
        "model": {"architecture": "torchvision MobileNetV3-Small 0.28.0, ImageNet1K V1 frozen features",
                  "weights_url": "https://download.pytorch.org/models/mobilenet_v3_small-047dcff4.pth",
                  "weights_sha256": digest(SOURCE / "mobilenet_v3_small-047dcff4.pth"),
                  "preprocessing": "grayscale repeated to RGB; resize 224x560; three 224x224 overlapping vertical crops; ImageNet normalization; mean+max pooled crop features",
                  "head": "StandardScaler + balanced logistic regression C=0.1"},
        "baseline": "64x160 grayscale histograms, quantiles, spatial difference quantiles; same head",
        "evaluation": "3 official item-disjoint folds; no threshold or hyperparameter tuning; out-of-fold image metrics. All 50 production items contain a defect, so item-level classification is undefined.",
        "feature_extraction_seconds_cpu": embed_seconds,
        "mobilenet_features_sha256": digest(ROOT / "mobilenet_features.npy"),
        "metrics": result, "paired_item_bootstrap_ap_difference_mobile_minus_baseline_95pct": diff_ci,
        "final_head_artifacts": final_head_artifacts,
        "scores_sha256": digest(ROOT / "scores.npz"),
        "script_sha256": digest(Path(__file__)),
        "limitations": ["All items have a defect somewhere; only image-level metrics are meaningful", "ImageNet backbone may underresolve small defects", "ImageNet weights may have separate commercial licensing considerations", "No iPhone latency, energy or memory measured", "Single dataset and model configuration; no field generalization claim"],
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"feature_extraction_seconds_cpu": embed_seconds, "metrics": result, "paired_bootstrap_ci": diff_ci}, indent=2))


if __name__ == "__main__":
    run()
