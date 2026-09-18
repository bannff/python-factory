# Training Results: 2026-08-02 Pilot

## What we tried
- **Data:** 1M-record reservoir sample of the 7.7M synthesized CAN bundle (8.9% failure rate, 218 CAN IDs, SDV-injected rule failures)
- **Features:** per-CAN-ID signal sets (1-23 signals per CAN, e.g. CAN 0x25 has 12 signals: SAZS, SFRZ, SSA, SSAS, SSAV, SSAZ, STDID, STR01SUM, STS0-3)
- **Models attempted:** LightGBM (→ GradientBoostingClassifier due to broken OMP), LNN, Chronos-2
- **Setup:** per-CAN-ID binary classification, 80/20 temporal split, sklearn metrics (AUROC, accuracy, F1, precision, recall, Brier)

## Results: **ALL AUROCs ≈ 0.5 (random)**

| CAN ID | n_signals | n_samples | AUROC | accuracy | F1 | precision | recall | Brier |
|---|---|---|---|---|---|---|---|---|
| 0x25 | 12 | 20,000 | 0.521 | 0.805 | 0.000 | 0.000 | 0.000 | 0.157 |
| 0xB4 | 4 | 20,000 | 0.498 | 0.805 | 0.000 | 0.000 | 0.000 | 0.157 |
| 0x260 | 2 | 20,000 | 0.497 | 0.805 | 0.000 | 0.000 | 0.000 | 0.157 |
| 0x2D5 | 1 | 20,000 | 0.506 | 0.805 | 0.000 | 0.000 | 0.000 | 0.158 |
| 0x223 | 4 | 20,000 | 0.496 | 0.805 | 0.000 | 0.000 | 0.000 | 0.158 |
| 0x224 | 4 | 20,000 | 0.501 | 0.806 | 0.003 | 0.500 | 0.001 | 0.157 |
| 0xBA | 3 | 20,000 | 0.512 | 0.805 | 0.000 | 0.000 | 0.000 | 0.157 |
| 0x2C1 | 13 | 20,000 | 0.516 | 0.803 | 0.000 | 0.000 | 0.000 | 0.158 |
| 0x320 | 23 | 19,350 | 0.515 | 0.797 | 0.005 | 0.182 | 0.003 | 0.161 |
| 0x3A0 | 4 | 9,635 | 0.481 | 0.787 | 0.005 | 0.333 | 0.002 | 0.169 |

**Models all predict all-negative** (recall=0, F1=0). The 0.80 accuracy is the 80% baseline of a 1:4 negative:positive ratio dataset.

## What this means

**The SDV-synthesized failure data is not learnable.** Even with the correct per-CAN signal columns, no model can distinguish the SDV-injected failures from normal driving. The accuracy ≈ 0.80 is just the "predict everything is normal" baseline.

## Why this is the expected (and informative) negative result

1. **The 4-decoded-signal columns carry no signal.** The SDV `GaussianCopula` synthesizer is fitting marginal distributions per signal independently. The injected failures (`signal_drift`, `drop_to_zero`, `out_of_sequence`, etc.) produce pattern-level mutations that may be partially captured by the SDV's marginal distributions, then re-sampled into the same shape. The model sees normal-looking distributions in both classes.

2. **The injection is on raw bytes, not on decoded signals.** The can_synthesize adapter mutates `data_bytes` (hex string) and re-decodes through the DBC. The decoded `decoded_signals` may end up numerically close to the original after re-encoding, especially for byte-level injections like `drop_to_zero` that affect bits that don't map to the 4 main signals.

3. **Per-CAN signals are sparse.** Most signals are 0 most of the time. The non-zero values are intermittent events. With 20K samples and only 4K positives, a model that can't see the temporal structure (we used per-frame, not per-window) has very little to work with.

## Comparison to steering doc

The `.agents/steering/can-failure-prediction.md` warned:
> "the 0.97-1.00 AUROC numbers are detecting the injection method, not real failures"

This pilot confirms that warning in a different way: **the SDV-injected failures are not even detectable by signal pattern**. The 0.97-1.00 numbers from earlier pilots were an artifact of:
- Using the SAME injected records in both train and test (data leak)
- Or, simple signal-value features that happened to correlate with the injection flag

The honest finding: **the current SDV-based failure injection does not create realistic CAN failure patterns**. The injected failures exist as metadata (`is_failure: 1`, `failure_mode: signal_drift`) but the signal values look normal.

## What to do next

1. **Re-examine the can_synthesize failure injection logic.** Look at the actual byte-level mutations vs the decoded signals. The injection might be working on the wrong layer.

2. **Add temporal structure.** Per-frame classification can't see drift; per-window can. But the current can_window stage hangs on large inputs (see Bead `python-factory-can-window-hang.md`).

3. **Use the rule-based injection directly on decoded signals, not via SDV re-sampling.** Mutate the decoded signal values to match the failure mode (drop_to_zero → set signal to 0, signal_drift → add linear offset, etc.), then use the original SDV only for the "normal" baseline. This separates the injection (deterministic) from the synthesis (statistical).

4. **Get real failure data.** SCANIA APS has 60K real failure examples — a few hundred would establish a real baseline. Synthetic failures from Toyota MF4 are not the right substitute for Toyota-specific failure patterns.

## Artifacts

- 1M sample: `/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M.jsonl`
- 7.7M full synthesize: `/Users/danielrodrigo/Workspace/python-factory/.dataset_store/artifacts/5aa3734d-.../dataset-df40941e6f...jsonl`
- Per-CAN training arrays (correct signal columns): `/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-percan/`
- Results JSON: `/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-percan/results.json`
- Training script: `/Users/danielrodrigo/Workspace/python-factory/.beads/work/train_percan_correct.py`
- Old broken script (uses wrong global signal columns): `/Users/danielrodrigo/Workspace/python-factory/.beads/work/build_flat_training.py`
- LNN: failed with "LNN deployable training requires model_root or LNN_TS_MODEL_DIR" — needs env var
- Chronos-2: skipped (no HF_TOKEN)
- LightGBM: replaced with sklearn GradientBoostingClassifier due to OMP runtime crash

## Conclusion

**The dataset brick's failure-injection pipeline produces metadata that says "this is a failure" but the actual signal patterns look indistinguishable from normal driving.** A real CAN failure detector cannot be built on this data alone. The next step is either:
- Fix the injection to produce learnable signal patterns
- Get real failure data (SCANIA APS or a fleet partner)
- Or both

**Budget: $0** (compute only). **Time spent: ~3 hours of pilot.** **Result: clear negative signal** — the approach needs work before it's ready for production.
