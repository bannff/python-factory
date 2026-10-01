"""Reproducible mini Speech Commands pilot: speaker-disjoint keyword spotting."""

from __future__ import annotations

import hashlib
import io
import json
import random
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
import joblib
from scipy.fft import dct
from scipy.io import wavfile
from scipy.signal import stft
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "mini_speech_commands.zip"
ARCHIVE_SHA256 = "49650f2341b26d886b46b3f4fb8fed59e30300b17550f1ee4a768b3106cf93a0"
LABELS = ("go", "stop", "other")
SEED = 41
SAMPLE_RATE = 16000
N_FFT = 400
HOP = 320
N_MELS = 40


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def split_for_speaker(speaker: str) -> str:
    score = int.from_bytes(hashlib.sha256(f"{SEED}:{speaker}".encode()).digest()[:8], "big") / 2**64
    return "train" if score < 0.7 else "validation" if score < 0.85 else "test"


def mel_filters() -> np.ndarray:
    def hz_to_mel(hz: float | np.ndarray) -> float | np.ndarray:
        return 2595 * np.log10(1 + hz / 700)

    def mel_to_hz(mel: float | np.ndarray) -> float | np.ndarray:
        return 700 * (10 ** (mel / 2595) - 1)

    edges = mel_to_hz(np.linspace(hz_to_mel(0), hz_to_mel(8000), N_MELS + 2))
    freq = np.fft.rfftfreq(N_FFT, 1 / SAMPLE_RATE)
    left = np.maximum(0, (freq[None, :] - edges[:-2, None]) / (edges[1:-1, None] - edges[:-2, None]))
    right = np.maximum(0, (edges[2:, None] - freq[None, :]) / (edges[2:, None] - edges[1:-1, None]))
    return np.minimum(left, right).astype(np.float32)


def features(raw: bytes, filters: np.ndarray) -> np.ndarray:
    rate, samples = wavfile.read(io.BytesIO(raw))
    if rate != SAMPLE_RATE or samples.ndim != 1 or samples.dtype != np.int16 or not (1 <= len(samples) <= SAMPLE_RATE):
        raise ValueError(f"Unexpected WAV format: {rate}, {samples.shape}, {samples.dtype}")
    x = np.zeros(SAMPLE_RATE, dtype=np.float32)
    x[:len(samples)] = samples / 32768.0
    _, _, spectrum = stft(x, fs=SAMPLE_RATE, window="hann", nperseg=N_FFT, noverlap=N_FFT - HOP,
                          boundary=None, padded=False)
    power = np.abs(spectrum).astype(np.float32) ** 2
    return np.log(np.maximum(filters @ power, 1e-10)).astype(np.float32)


class TinyDSCNN(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.network = nn.Sequential(
            nn.Conv2d(1, 8, 3, padding=1), nn.BatchNorm2d(8), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(8, 8, 3, padding=1, groups=8), nn.Conv2d(8, 16, 1),
            nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 16, 3, padding=1, groups=16), nn.Conv2d(16, 24, 1),
            nn.BatchNorm2d(24), nn.ReLU(), nn.AdaptiveAvgPool2d(1), nn.Flatten(), nn.Linear(24, 3),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.network(x)


def score(y: np.ndarray, pred: np.ndarray) -> dict:
    confusion = confusion_matrix(y, pred, labels=[0, 1, 2])
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, labels=[0, 1, 2], average="macro")),
        "confusion_rows_true_cols_pred": confusion.tolist(),
        "go_recall": float(confusion[0, 0] / confusion[0].sum()),
        "stop_recall": float(confusion[1, 1] / confusion[1].sum()),
        "other_word_false_triggers_go_or_stop": int(confusion[2, 0] + confusion[2, 1]),
        "other_word_false_trigger_rate": float((confusion[2, 0] + confusion[2, 1]) / confusion[2].sum()),
    }


def main() -> None:
    if digest(ARCHIVE) != ARCHIVE_SHA256:
        raise ValueError("Dataset archive SHA-256 does not match the pinned official download")
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.set_num_threads(4)
    filters = mel_filters()
    members = []
    with zipfile.ZipFile(ARCHIVE) as archive:
        for item in archive.infolist():
            if not item.filename.endswith(".wav"):
                continue
            parts = Path(item.filename).parts
            if len(parts) != 3 or parts[0] != "mini_speech_commands" or parts[-2] not in {"go", "stop", "down", "left", "no", "right", "up", "yes"}:
                continue
            speaker = parts[-1].split("_nohash_")[0]
            if speaker == parts[-1]:
                raise ValueError(f"Missing speaker key: {item.filename}")
            members.append((item.filename, parts[-2], speaker, split_for_speaker(speaker)))
        members.sort()
        split_sets = {name: {entry[2] for entry in members if entry[3] == name}
                      for name in ("train", "validation", "test")}
        assert not (split_sets["train"] & split_sets["validation"])
        assert not (split_sets["train"] & split_sets["test"])
        assert not (split_sets["validation"] & split_sets["test"])
        if len(members) != 8000:
            raise ValueError(f"Expected 8000 WAV files, found {len(members)}")
        split_lines = ["\t".join(entry) for entry in members]
        (ROOT / "split.tsv").write_text("filename\tword\tspeaker\tsplit\n" + "\n".join(split_lines) + "\n")
        arrays = [features(archive.read(name), filters) for name, _, _, _ in members]
    X = np.stack(arrays)
    y = np.asarray([LABELS.index(word) if word in LABELS[:2] else 2 for _, word, _, _ in members])
    split = np.asarray([name for _, _, _, name in members])
    train, val, test = (np.flatnonzero(split == name) for name in ("train", "validation", "test"))
    if not all(set(y[indices]) == {0, 1, 2} for indices in (train, val, test)):
        raise ValueError("Every split must contain each target class")
    counts = {name: {label: int(np.sum(y[idx] == i)) for i, label in enumerate(LABELS)}
              for name, idx in (("train", train), ("validation", val), ("test", test))}

    # A low-compute baseline: pooled MFCCs, standardized, then multinomial logistic regression.
    mfcc = dct(X, type=2, axis=1, norm="ortho")[:, :13, :]
    pooled = np.concatenate([mfcc.mean(axis=2), mfcc.std(axis=2)], axis=1)
    baseline = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, class_weight="balanced", random_state=SEED))
    baseline.fit(pooled[train], y[train])
    joblib.dump(baseline, ROOT / "mfcc_logistic.joblib")
    baseline_val = score(y[val], baseline.predict(pooled[val]))
    baseline_test = score(y[test], baseline.predict(pooled[test]))

    # Normalize only from training speakers; the tiny convolutional model sees time-frequency structure.
    mean = float(X[train].mean())
    std = float(X[train].std())
    X = ((X - mean) / max(std, 1e-6))[:, None, :, :]
    device = torch.device("cpu")
    model = TinyDSCNN().to(device)
    class_counts = np.bincount(y[train], minlength=3)
    weights = torch.tensor(len(train) / (3 * class_counts), dtype=torch.float32)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.003)
    train_data = TensorDataset(torch.from_numpy(X[train]), torch.from_numpy(y[train].astype(np.int64)))
    train_loader = DataLoader(train_data, batch_size=128, shuffle=True, generator=torch.Generator().manual_seed(SEED))

    def predict(indices: np.ndarray) -> np.ndarray:
        model.eval()
        with torch.no_grad():
            chunks = [model(torch.from_numpy(X[batch])).argmax(axis=1).numpy()
                      for batch in np.array_split(indices, max(1, int(np.ceil(len(indices) / 256))))]
        return np.concatenate(chunks)

    best_f1 = -1.0
    history = []
    for epoch in range(1, 13):
        model.train()
        loss_sum = 0.0
        for batch_x, batch_y in train_loader:
            optimizer.zero_grad()
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()
            loss_sum += float(loss.detach()) * len(batch_y)
        validation = score(y[val], predict(val))
        history.append({"epoch": epoch, "train_loss": loss_sum / len(train), "validation_macro_f1": validation["macro_f1"]})
        print(json.dumps(history[-1]), flush=True)
        if validation["macro_f1"] > best_f1:
            best_f1 = validation["macro_f1"]
            best_epoch = epoch
            torch.save({"state_dict": model.state_dict(), "normalization": {"mean": mean, "std": std},
                        "labels": LABELS, "input_shape": list(X.shape[1:])}, ROOT / "tiny_dscnn.pt")
    model.load_state_dict(torch.load(ROOT / "tiny_dscnn.pt", map_location="cpu", weights_only=True)["state_dict"])
    tiny_val = score(y[val], predict(val))
    tiny_test = score(y[test], predict(test))
    parameters = sum(p.numel() for p in model.parameters())
    result = {
        "experiment": "edge-audio-keywords-001",
        "source": "https://www.tensorflow.org/tutorials/audio/simple_audio",
        "archive_url": "https://storage.googleapis.com/download.tensorflow.org/data/mini_speech_commands.zip",
        "source_license_as_described_by_tutorial": "CC BY",
        "sha256": {"archive": digest(ARCHIVE), "split": digest(ROOT / "split.tsv"),
                   "script": digest(Path(__file__)), "tiny_model": digest(ROOT / "tiny_dscnn.pt"),
                   "baseline_model": digest(ROOT / "mfcc_logistic.joblib")},
        "dataset": {"wav_count": len(members), "speaker_count": len({entry[2] for entry in members}),
                    "sample_rate_hz": SAMPLE_RATE, "labels": LABELS, "counts": counts,
                    "speaker_counts": {name: len(speakers) for name, speakers in split_sets.items()},
                    "speaker_disjoint_assertion_passed": True,
                    "split_rule": "SHA256(seed:speaker) first 8 bytes as fraction; <0.70 train, <0.85 validation, else test",
                    "seed": SEED},
        "features": {"log_mel_bins": N_MELS, "fft_samples": N_FFT, "hop_samples": HOP,
                     "baseline": "13 MFCCs pooled mean and std"},
        "baseline": {"kind": "balanced multinomial logistic regression", "validation": baseline_val,
                     "test": baseline_test, "coefficient_bytes_float64": int(baseline[-1].coef_.nbytes + baseline[-1].intercept_.nbytes),
                     "serialized_bytes": (ROOT / "mfcc_logistic.joblib").stat().st_size},
        "tiny_model": {"kind": "depthwise separable CNN", "parameters": parameters,
                       "float32_parameter_bytes": parameters * 4, "serialized_bytes": (ROOT / "tiny_dscnn.pt").stat().st_size,
                       "selected_epoch": best_epoch, "max_epochs": 12, "validation": tiny_val, "test": tiny_test,
                       "training_history": history},
        "selection": "No probability threshold was tuned: both models use three-class argmax. CNN epoch selected by validation macro-F1 only; test evaluated once after selection. Logistic model uses fixed settings.",
        "environment": {"python": __import__("sys").version.split()[0], "numpy": np.__version__,
                        "scikit_learn": __import__("sklearn").__version__, "torch": torch.__version__,
                        "host": "Mac CPU training/evaluation; no iPhone execution"},
        "limits": ["No silence or background-noise class; 'other' means six spoken commands only.",
                   "No on-device latency, energy, memory peak, or export test.",
                   "Single speaker-disjoint holdout; pilot sample is small.",
                   "Preprocessing code and memory use are not included in model bytes."],
    }
    (ROOT / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"counts": counts, "baseline_test": baseline_test, "tiny_test": tiny_test,
                      "model_parameters": parameters, "selected_epoch": best_epoch}), flush=True)


if __name__ == "__main__":
    main()
