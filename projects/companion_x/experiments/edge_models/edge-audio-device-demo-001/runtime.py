"""NumPy-only inference for the frozen 1,043-parameter keyword model."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import re
import resource
import time
import wave
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


SAMPLE_RATE = 16000
FFT_SAMPLES = 400
HOP_SAMPLES = 320
MEL_BINS = 40
LABELS = ("go", "stop", "other")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mel_filters() -> np.ndarray:
    def hz_to_mel(hz):
        return 2595 * np.log10(1 + hz / 700)

    def mel_to_hz(mel):
        return 700 * (10 ** (mel / 2595) - 1)

    edges = mel_to_hz(np.linspace(hz_to_mel(0), hz_to_mel(8000), MEL_BINS + 2))
    freq = np.fft.rfftfreq(FFT_SAMPLES, 1 / SAMPLE_RATE)
    left = np.maximum(0, (freq[None, :] - edges[:-2, None]) / (edges[1:-1, None] - edges[:-2, None]))
    right = np.maximum(0, (edges[2:, None] - freq[None, :]) / (edges[2:, None] - edges[1:-1, None]))
    return np.minimum(left, right).astype(np.float32)


def log_mel(raw: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(raw), "rb") as stream:
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate(), stream.getcomptype()) != (1, 2, SAMPLE_RATE, "NONE"):
            raise ValueError("WAV must be mono 16-bit PCM at 16 kHz")
        count = stream.getnframes()
        if not 1 <= count <= SAMPLE_RATE:
            raise ValueError("WAV must have 1..16000 frames")
        samples = np.frombuffer(stream.readframes(count), dtype="<i2")
        if len(samples) != count:
            raise ValueError("WAV payload is shorter than declared")
    x = np.zeros(SAMPLE_RATE, dtype=np.float32)
    x[:count] = samples / 32768.0
    window = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(FFT_SAMPLES) / FFT_SAMPLES)).astype(np.float32)
    frames = sliding_window_view(x, FFT_SAMPLES)[::HOP_SAMPLES]
    spectrum = (np.fft.rfft(frames * window, axis=-1) / window.sum()).astype(np.complex64).T
    power = np.abs(spectrum).astype(np.float32) ** 2
    return np.log(np.maximum(mel_filters() @ power, 1e-10)).astype(np.float32)


def load_model(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        model = {name: archive[name].copy() for name in archive.files}
    expected = {f"network.{layer}.{name}" for layer, names in {
        0: ("weight", "bias"), 1: ("weight", "bias", "running_mean", "running_var", "num_batches_tracked"),
        4: ("weight", "bias"), 5: ("weight", "bias"),
        6: ("weight", "bias", "running_mean", "running_var", "num_batches_tracked"),
        9: ("weight", "bias"), 10: ("weight", "bias"),
        11: ("weight", "bias", "running_mean", "running_var", "num_batches_tracked"),
        15: ("weight", "bias"),
    }.items() for name in names}
    if set(model) != expected | {"mean", "std", "labels"}:
        raise ValueError("Model artifact keys do not match the frozen CNN")
    if tuple(model["labels"].tolist()) != LABELS or not np.isfinite(model["std"]).all() or float(model["std"]) <= 0:
        raise ValueError("Model normalization or labels are invalid")
    if not all(np.isfinite(value).all() for name, value in model.items() if name != "labels"):
        raise ValueError("Model contains non-finite values")
    return model


def conv(x: np.ndarray, weight: np.ndarray, bias: np.ndarray, groups: int = 1, padding: int = 0) -> np.ndarray:
    out_channels, group_channels, height, width = weight.shape
    if x.shape[0] != group_channels * groups or out_channels % groups:
        raise ValueError("Invalid convolution dimensions")
    padded = np.pad(x, ((0, 0), (padding, padding), (padding, padding)))
    windows = sliding_window_view(padded, (height, width), axis=(1, 2))
    group_output = out_channels // groups
    outputs = [np.einsum("chwkl,ckl->hw", windows[group * group_channels:(group + 1) * group_channels],
                         weight[channel], optimize=True) + bias[channel]
               for channel in range(out_channels)
               for group in (channel // group_output,)]
    return np.stack(outputs).astype(np.float32)


def batch_norm(x: np.ndarray, model: dict[str, np.ndarray], layer: int) -> np.ndarray:
    key = f"network.{layer}."
    scale = model[key + "weight"] / np.sqrt(model[key + "running_var"] + 1e-5)
    offset = model[key + "bias"] - model[key + "running_mean"] * scale
    return (x * scale[:, None, None] + offset[:, None, None]).astype(np.float32)


def max_pool(x: np.ndarray) -> np.ndarray:
    channels, height, width = x.shape
    return x[:, :height // 2 * 2, :width // 2 * 2].reshape(channels, height // 2, 2, width // 2, 2).max(axis=(2, 4))


def logits(model: dict[str, np.ndarray], features: np.ndarray) -> np.ndarray:
    x = ((features - float(model["mean"])) / float(model["std"]))[None]
    for conv_layer, norm_layer, groups in ((0, 1, 1), (4, 6, 8), (9, 11, 16)):
        key = f"network.{conv_layer}."
        x = conv(x, model[key + "weight"], model[key + "bias"], groups=groups, padding=1)
        if conv_layer != 0:
            point = f"network.{conv_layer + 1}."
            x = conv(x, model[point + "weight"], model[point + "bias"])
        x = np.maximum(batch_norm(x, model, norm_layer), 0)
        if conv_layer != 9:
            x = max_pool(x)
    flat = x.mean(axis=(1, 2))
    return (model["network.15.weight"] @ flat + model["network.15.bias"]).astype(np.float32)


def predict(model: dict[str, np.ndarray], raw: bytes) -> dict:
    score = logits(model, log_mel(raw))
    probabilities = np.exp(score - score.max())
    probabilities /= probabilities.sum()
    return {"prediction": LABELS[int(probabilities.argmax())],
            "probabilities": [float(value) for value in probabilities]}


def run(model_path: Path, cohort_path: Path, output: Path, repeats: int) -> None:
    if not 1 <= repeats <= 100:
        raise ValueError("repeats must be 1..100")
    model = load_model(model_path)
    cohort = json.loads(cohort_path.read_text())
    if not isinstance(cohort.get("clips"), list) or not cohort["clips"]:
        raise ValueError("Cohort requires nonempty clips")
    predictions = []
    seen_ids = set()
    for clip in cohort["clips"]:
        clip_id, filename = clip["clip_id"], clip["filename"]
        if (not isinstance(clip_id, str) or re.fullmatch(r"clip-[0-9]{3,}", clip_id) is None
                or filename != clip_id + ".wav" or clip_id in seen_ids):
            raise ValueError("Invalid clip identity or path")
        seen_ids.add(clip_id)
        path = cohort_path.parent / "clips" / filename
        if sha256(path) != clip["sha256"]:
            raise ValueError(f"Audio digest mismatch for {clip_id}")
        elapsed = []
        for _ in range(repeats):
            start = time.perf_counter_ns()
            raw = path.read_bytes()
            result = predict(model, raw)
            elapsed.append((time.perf_counter_ns() - start) / 1e6)
        predictions.append({"clip_id": clip_id, **result, "latency_ms": float(np.median(elapsed)),
                            "latency_samples_ms": elapsed})
    report = {"schema_version": 1, "model_sha256": sha256(model_path), "cohort_sha256": sha256(cohort_path),
              "runtime_sha256": sha256(Path(__file__)), "environment": {
                  "platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
                  "numpy": np.__version__, "ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  "ru_maxrss_unit": "KiB on Linux; bytes on macOS"},
              "repeats": repeats, "timing_scope": "staged WAV file read, log-mel preprocessing, and model inference; excludes model load",
              "predictions": predictions}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    run(args.model, args.cohort, args.output, args.repeats)
