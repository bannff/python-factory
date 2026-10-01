"""Build a standalone, playable HTML report after local inference."""

from __future__ import annotations

import argparse
import base64
import html
import json
import statistics
from pathlib import Path


LABELS = ("go", "stop", "other")


def write_demo(predictions: dict, truth: dict, clips: Path, output: Path,
               reference: dict | None = None) -> dict:
    predicted = {item["clip_id"]: item for item in predictions["predictions"]}
    actual = {item["clip_id"]: item for item in truth["clips"]}
    if predicted.keys() != actual.keys() or not predicted:
        raise ValueError("Prediction and truth clip IDs must match")
    ref = {item["clip_id"]: item for item in reference["predictions"]} if reference else {}
    if ref and ref.keys() != predicted.keys():
        raise ValueError("Reference clip IDs must match")
    confusion = {label: {candidate: 0 for candidate in LABELS} for label in LABELS}
    cards = []
    latency = []
    max_probability_error = 0.0
    for clip_id in sorted(predicted):
        record = predicted[clip_id]
        source = actual[clip_id]
        label, choice = source["label"], record["prediction"]
        probs = record["probabilities"]
        if label not in LABELS or choice not in LABELS or len(probs) != 3:
            raise ValueError("Unexpected label or probability shape")
        confusion[label][choice] += 1
        latency.append(float(record["latency_ms"]))
        if ref:
            max_probability_error = max(max_probability_error,
                                        max(abs(float(a) - float(b)) for a, b in
                                            zip(probs, ref[clip_id]["probabilities"], strict=True)))
            if choice != ref[clip_id]["prediction"]:
                raise ValueError(f"Reference decision mismatch for {clip_id}")
        wav = clips / (clip_id + ".wav")
        if not wav.is_file():
            raise ValueError(f"Missing staged audio: {clip_id}")
        encoded = base64.b64encode(wav.read_bytes()).decode("ascii")
        bars = "".join(
            f'<div class="bar"><span>{name}</span><meter min="0" max="1" value="{float(prob):.6f}"></meter>'
            f'<strong>{float(prob):.1%}</strong></div>'
            for name, prob in zip(LABELS, probs, strict=True)
        )
        status = "correct" if label == choice else "miss"
        cards.append(
            f'<article class="card {status}"><div class="meta"><span>{html.escape(clip_id)}</span>'
            f'<span class="badge">{status}</span></div><audio controls preload="none" '
            f'src="data:audio/wav;base64,{encoded}"></audio>'
            f'<p>Prediction <strong>{html.escape(choice)}</strong> · Truth <strong>{html.escape(label)}</strong></p>'
            f'{bars}<small>{float(record["latency_ms"]):.2f} ms median local inference</small></article>'
        )
    if ref and max_probability_error > 0.001:
        raise ValueError(f"Reference probability error {max_probability_error:.6g} exceeds 0.001")
    total = len(predicted)
    correct = sum(confusion[label][label] for label in LABELS)
    summary = {"clip_count": total, "accuracy": correct / total,
               "confusion_rows_true_cols_pred": [[confusion[a][b] for b in LABELS] for a in LABELS],
               "median_latency_ms": statistics.median(latency),
               "max_probability_error_vs_torch": max_probability_error if ref else None,
               "prediction_parity": bool(ref), "host_label_free_payload": True}
    table_rows = "".join(
        f'<tr><th>{label}</th>' + "".join(f'<td>{confusion[label][candidate]}</td>' for candidate in LABELS) + "</tr>"
        for label in LABELS
    )
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tiny audio command demo</title><style>
body{{font:16px/1.5 system-ui;background:#0d1722;color:#e6eff7;max-width:1100px;margin:auto;padding:28px}}
h1{{font-size:2rem;margin-bottom:0}} p.lead{{color:#a8c1d3}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:14px}}
.card{{background:#162839;border:1px solid #35516a;border-radius:14px;padding:16px}}.card.correct{{border-top:4px solid #48d5a8}}
.card.miss{{border-top:4px solid #ffb35c}}.meta{{display:flex;justify-content:space-between;font-weight:bold}}
.badge{{font-size:.75rem;text-transform:uppercase;color:#a8c1d3}}audio{{display:block;width:100%;margin:15px 0}}
.bar{{display:grid;grid-template-columns:45px 1fr 52px;gap:8px;align-items:center;font-size:.85rem}}
meter{{width:100%;height:16px}}small{{display:block;margin-top:12px;color:#a8c1d3}}
table{{border-collapse:collapse;margin:15px 0 25px}}th,td{{padding:7px 15px;border:1px solid #35516a;text-align:center}}
</style></head><body><h1>Tiny audio command demo</h1>
<p class="lead">Local recognition of <strong>go</strong> and <strong>stop</strong> from held-out speakers.
Play a clip to hear the input. Scores were produced from an anonymous cohort; labels were joined afterward.</p>
<p><strong>{correct}/{total}</strong> correct · <strong>{summary['median_latency_ms']:.2f} ms</strong> median inference ·
<strong>{max_probability_error:.6g}</strong> maximum PyTorch score difference</p>
<h2>Confusion counts</h2><table><thead><tr><th>True \\ Predicted</th><th>go</th><th>stop</th><th>other</th></tr></thead>
<tbody>{table_rows}</tbody></table><div class="grid">{''.join(cards)}</div>
<p class="lead">ARM64 Linux container evidence only. This pilot does not measure iPhone latency, energy,
ambient-noise false triggers, or Ditto behavior.</p></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page)
    (output.parent / "demo-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = write_demo(json.loads(args.predictions.read_text()), json.loads(args.truth.read_text()),
                         args.clips, args.output, json.loads(args.reference.read_text()))
    print(json.dumps(summary, indent=2))
