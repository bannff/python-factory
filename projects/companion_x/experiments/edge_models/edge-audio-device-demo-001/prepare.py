"""Host-only export and anonymous held-out cohort preparation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import numpy as np
import torch


ARCHIVE_SHA256 = "49650f2341b26d886b46b3f4fb8fed59e30300b17550f1ee4a768b3106cf93a0"
SPLIT_SHA256 = "58454c7f670d12fbdb8669e54bc90f02f6d78b16fd4d1be1b5f23678f0c899c2"
CHECKPOINT_SHA256 = "40aa7c5d8502e9390ed5c62493c7bb43ae8f62b1e3d48214dff82e5b8d938ec5"
SOURCE_SHA256 = "23fd28ecb9c867045146e5ff39e3e7c7ed6e0780f933a1a1b3cec94acc29b5fe"
LABELS = ("go", "stop", "other")
DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "edge-audio-command-001" / "run.py"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def class_for_word(word: str) -> str:
    if word not in {"go", "stop", "down", "left", "no", "right", "up", "yes"}:
        raise ValueError(f"Unexpected source word: {word}")
    return word if word in {"go", "stop"} else "other"


def select_cohort(rows: list[dict], per_class: int = 4) -> list[dict]:
    if per_class < 1:
        raise ValueError("per_class must be positive")
    selected: list[dict] = []
    used_speakers: set[str] = set()
    for label in LABELS:
        eligible = (row for row in rows if row["split"] == "test" and class_for_word(row["word"]) == label)
        ranked = sorted(eligible, key=lambda row: hashlib.sha256(("device-demo-001:" + row["filename"]).encode()).hexdigest())
        for row in ranked:
            if row["speaker"] not in used_speakers:
                selected.append(row)
                used_speakers.add(row["speaker"])
            if len([item for item in selected if class_for_word(item["word"]) == label]) == per_class:
                break
        if len([item for item in selected if class_for_word(item["word"]) == label]) != per_class:
            raise ValueError(f"Insufficient speaker-distinct {label} test clips")
    return sorted(selected, key=lambda row: hashlib.sha256(("shuffle:" + row["filename"]).encode()).hexdigest())


def write_numpy_model(state_dict: dict, mean: float, std: float, output: Path) -> None:
    if not np.isfinite([mean, std]).all() or std <= 0:
        raise ValueError("Invalid model normalization")
    arrays = {key: tensor.detach().cpu().numpy() for key, tensor in state_dict.items()}
    arrays.update(mean=np.asarray(mean, dtype=np.float32), std=np.asarray(std, dtype=np.float32),
                  labels=np.asarray(LABELS))
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **arrays)


def load_source(path: Path):
    if sha256(path) != SOURCE_SHA256:
        raise ValueError("Training runner differs from the frozen pilot")
    spec = importlib.util.spec_from_file_location("edge_audio_training_source", path)
    assert spec is not None and spec.loader is not None
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)
    return source


def prepare(archive_path: Path, split_path: Path, checkpoint_path: Path, output: Path,
            source_path: Path = DEFAULT_SOURCE, per_class: int = 4) -> None:
    if output.exists():
        raise ValueError("prepare output must be a new directory")
    for path, pinned in ((archive_path, ARCHIVE_SHA256), (split_path, SPLIT_SHA256),
                         (checkpoint_path, CHECKPOINT_SHA256)):
        if sha256(path) != pinned:
            raise ValueError(f"Frozen input hash mismatch: {path.name}")
    source = load_source(source_path)
    with split_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 8000:
        raise ValueError("Frozen split must contain 8,000 clips")
    selected = select_cohort(rows, per_class)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model = source.TinyDSCNN().eval()
    model.load_state_dict(checkpoint["state_dict"])
    mean, std = checkpoint["normalization"]["mean"], checkpoint["normalization"]["std"]
    payload = output / "payload"
    clips = payload / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    model_path = payload / "model.npz"
    write_numpy_model(model.state_dict(), mean, std, model_path)
    public, private, reference = [], [], []
    with zipfile.ZipFile(archive_path) as archive:
        for index, row in enumerate(selected, 1):
            clip_id = f"clip-{index:03d}"
            filename = clip_id + ".wav"
            raw = archive.read(row["filename"])
            (clips / filename).write_bytes(raw)
            public.append({"clip_id": clip_id, "filename": filename,
                           "sha256": hashlib.sha256(raw).hexdigest()})
            private.append({"clip_id": clip_id, "word": row["word"], "label": class_for_word(row["word"]),
                            "speaker": row["speaker"], "source_filename": row["filename"]})
            features = source.features(raw, source.mel_filters())
            with torch.no_grad():
                vector = torch.from_numpy(((features - mean) / std)[None, None])
                probabilities = torch.softmax(model(vector), dim=1)[0].numpy()
            reference.append({"clip_id": clip_id, "prediction": LABELS[int(probabilities.argmax())],
                              "probabilities": [float(value) for value in probabilities]})
    (payload / "cohort.json").write_text(json.dumps({"schema_version": 1, "clips": public}, indent=2) + "\n")
    (output / "truth.json").write_text(json.dumps({"schema_version": 1, "clips": private}, indent=2) + "\n")
    (output / "reference.json").write_text(json.dumps({"schema_version": 1, "predictions": reference}, indent=2) + "\n")
    manifest = {"experiment": "edge-audio-device-demo-001", "source_experiment": "edge-audio-command-001",
                "source_hashes": {"archive": ARCHIVE_SHA256, "split": SPLIT_SHA256,
                                  "checkpoint": CHECKPOINT_SHA256, "runner": SOURCE_SHA256},
                "cohort_policy": f"{per_class} clips/class from held-out test speakers; distinct speakers; SHA-256 ranked",
                "payload_has_labels": False,
                "files": {name: {"sha256": sha256(output / name), "bytes": (output / name).stat().st_size}
                          for name in ("payload/model.npz", "payload/cohort.json", "truth.json", "reference.json")}}
    (output / "prepare-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-runner", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--per-class", type=int, default=4)
    args = parser.parse_args()
    prepare(args.archive, args.split, args.checkpoint, args.output, args.source_runner, args.per_class)
