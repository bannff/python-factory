# Edge visual quality — ARM64 inference run

**Run:** `edge-visual-inference-20260930`
**Status:** Single-device inference demonstrated; model utility gate not demonstrated; Ditto mesh not run.

## What ran

The fold-specific grayscale-statistics logistic model ran inside the existing
`edge-lab` Linux ARM64 container with Python 3.12. Pillow 12.3.0 was installed
using its pinned ARM64 wheel hash. The model scored all 135 official fold-0
images in 1.57 seconds (11.60 ms/image). The model artifact is 6,280 bytes.
The host and container scores were identical across the full cohort (maximum
absolute difference 0.0).

The device received original image bytes, a frozen label-free manifest, the
model, and the inference code. Host-only labels were joined after predictions
returned. No training framework, NumPy, scikit-learn, or Ditto license was
needed inside the device for this inference-only pass.

## Held-out result

| Images | Positive | TP | FP | FN | TN | Recall | FPR | AP | AUROC |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 135 | 18 | 16 | 12 | 2 | 105 | 0.889 | 0.103 | 0.876 | 0.955 |

The frozen exploratory gate requires recall ≥0.70, FPR ≤0.10, and AP >0.50.
It is **not demonstrated** because 12/117 normal images were false alerts
(10.26%, above the 10% ceiling). Do not tune the threshold against fold 0.
The operational value is a triage signal for human inspection, not automatic
rejection.

## Reproducibility and limits

- Model SHA-256: `6593e82d64ac4222e0540cbd7b0ad12e88361195447b13a42004827eba1dfcbc`
- Frozen assignment SHA-256: `b3ecc202c51fff5b83d58a36522afd73befb30076c3a40aab089712c99c54e07`
- Runtime: Linux ARM64, CPython 3.12, Pillow 12.3.0; 6.3 KB model; no native
  iPhone/Android compatibility or power/performance claim.
- This run used one container. It does not demonstrate Ditto synchronization,
  multiple peers, or offline mesh coordination. The next layer is a second
  device that syncs compact task claims and review alerts while images remain
  local.
- Training used official folds 1–2; evaluation used official fold 0 only.
- Dataset: KolektorSDD, Kolektor Group (2019), CC BY-NC-SA 4.0; noncommercial
  research only.

Machine-readable local output is retained under the ignored `results/` run
artifact directory. The run summary and metrics above are the curated,
version-controlled result record.
