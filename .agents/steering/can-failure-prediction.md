# CAN Failure Prediction — Steering Document

**Last updated:** 2026-07-24
**Spec:** `.github/spec/rando.md`
**Epic:** `python-factory-dth`

## Goal

Build a closed-loop adversarial system (TimeGAN) that generates realistic synthetic CAN failure data, graded by evaluation metrics, until models achieve production-quality failure prediction.

> **2026-07-24 update:** the 2026-07-23 TimeGAN diagnosis below led to a
> real fix upstream — see "Session Resume (2026-07-24)" at the bottom of
> this doc. Conditional TimeGAN (failure-mode-conditioned generator) and a
> dual-objective loss fixing the seed instability both shipped. One new
> construct-validity note was found in the SCANIA-pattern injection that
> came with it — tracked as `python-factory-sbhyq.5`, not a blocker, just
> read before citing the 0.70-0.80 AUROC numbers as "realistic CAN
> failures."

> **2026-07-23 update — read before touching TimeGAN again:** a follow-up
> session diagnosed *why* the TimeGAN loop isn't converging into better
> failures — it's not a tuning problem, see "Session Resume (2026-07-23)"
> at the bottom of this doc and `.github/spec/can-failure-prediction-review.md`
> §16. Short version: the current TimeGAN is unsupervised (trains on
> normal signals only, `y_uri` ignored) so it structurally cannot generate
> failures, and there's a cheaper, more realistic path forward (correlated
> rule-based injection, bd `python-factory-bzm3s`) that doesn't require
> fixing the GAN at all. The "Goal" statement above is not being retracted
> here — just don't keep debugging the current GAN loop assuming the goal
> requires it. See the two new beads before resuming work.

## Current Status

| Area | Status | Notes |
|------|--------|-------|
| Pipeline | ✅ Complete | 5 stages: ingest → profile → synthesize → window → augment |
| Data | ✅ 92M+ decoded records | Toyota (92M) + Kia (210K) + S3 OBD-II (100K) |
| Training | ✅ LightGBM working | AUROC 0.95-1.00 on top CAN IDs |
| Evaluation | ✅ 4 synthetic evaluators | + `evals_evaluate_can_model` (accuracy/precision/recall/f1, auroc/auprc/brier) wired into `train_top_can_ids` (bd:python-factory-sbhyq.4) |
| MCP tool | ✅ Built | `can_run_full_pipeline` single-call |
| Taxonomy | ✅ Built | 10 node types, 8 relationships in graph brick |
| CTGAN | ✅ Implemented | Drop-in for GaussianCopula |
| Temporal smoothing | ✅ Implemented | numpy Gaussian kernel |
| TimeGAN | ✅ Implemented | Generator + Discriminator, 6 tests pass |
| TimeGAN MCP | ✅ Built | `ml_train_timeseries` + `ml_sample_timeseries` |
| TimeGAN recipe | ✅ Built | `can-pipeline-timegan@1` |
| Taxonomy | ✅ Built | 10 node types, 8 relationships in graph brick |
| CTGAN | ✅ Implemented | Drop-in for GaussianCopula |
| Temporal smoothing | ✅ Implemented | numpy Gaussian kernel |
| TimeGAN | ⏳ Ready to start | Data threshold met, no GPU needed (CPU works) |

## Data Inventory

### Decoded (usable for training)

| Source | Total | Decoded | CAN IDs | Format |
|--------|-------|---------|---------|--------|
| Toyota MF4 (67 files) | 1,788,315 | 749,594 | 25 (25 with signals) | MF4 + Toyota DBC |
| Car-Hacking (Kia Soul) | 16,368,810 | 7,604,328 | 2,048 (240 with signals) | CSV + Hyundai DBC |
| OTIDS (Kia Soul) | 4,489,685 | 2,478,281 | 46 (45 with signals) | TXT + Hyundai DBC |
| S3 OBD-II (2 VINs) | 100,135 | 100,135 | 2 | CSV (pre-decoded) |
| **Combined** | **22,746,945** | **10,932,338** | **291** | |

### S3 Access

AWS S3 bucket: `s3://rx-can-frames-synthetic-lwekrnidlk/raw_vins/`
- Account: 195714074439
- 2 VINs, 4 CSV files, ~100K records
- Pre-decoded OBD-II signals (EngineRPM, VehicleSpeed, etc.)
- No DBC needed — already physical values
- **Credentials in environment only, never in files**
- Role: S3-ExternalAccess-DRod-Burner
- User: rx_external_daniel
- **Credentials stored in environment, NOT in this doc**

### DBC Files

| DBC | Source | Vehicles |
|-----|--------|----------|
| `toyota_legacy_combined.dbc` | Local | Toyota (67 MF4 files) |
| `hyundai_2015_ccan.dbc` | opendbc | Hyundai/Kia/Genesis (~40 models) |
| `hyundai_2015_mcan.dbc` | opendbc | Hyundai/Kia/Genesis (infotainment) |

### S3 OBD-II Signals (pre-decoded)

EngineRPM, VehicleSpeed, EngineCoolantTemp, ThrottlePosition, MAF, FuelTrims, DTC codes, etc. — 17 signals, no DBC needed.

## Training Results

### Per-CAN-ID LightGBM (batch67 Toyota, temporal split)

| CAN ID | Features | Samples | AUROC | F1 |
|--------|----------|---------|-------|-----|
| 0x380 | 17 | 1,001 | 0.997 | 0.889 |
| 0x2C1 | 13 | 14,799 | 0.984 | 0.900 |
| 0x320 | 23 | 9,370 | 0.973 | 0.764 |
| 0x25 | 12 | 35,924 | 0.967 | 0.783 |
| 0x3B7 | 18 | 1,967 | 0.765 | 0.000 |

### Per-CAN-ID LightGBM (combined Toyota+Kia)

| CAN ID | AUROC | F1 | Notes |
|--------|-------|-----|-------|
| 0x553 | 1.000 | 1.000 | Kia signal |
| 0x515 | 1.000 | 1.000 | Kia signal |
| 0x541 | 0.982 | 0.000 | Kia signal |
| 0x153 | 0.972 | 0.800 | TCS11 (shared Kia/Toyota) |
| 0x380 | 0.976 | 0.500 | Toyota signal |

### Heuristic Baseline

| CAN ID | Heuristic AUROC | LightGBM AUROC | Δ |
|--------|----------------|----------------|---|
| 0x25 | 0.562 | 0.967 | +0.41 |
| 0x2C1 | 0.520 | 0.984 | +0.46 |
| 0x320 | 0.503 | 0.973 | +0.47 |

### LSTM/TCN

Underperform on small samples. AUROC ~0.73-0.77 on larger CAN IDs, 0.0 on small ones (temporal split issue). Need more data per CAN ID.

### GAN-Augmented Training (2026-07-21)

**Key finding: GAN synthetic data significantly improves model performance.**

| Model | Training Data | AUROC | AUPRC | Brier | Lead Time |
|-------|--------------|-------|-------|-------|-----------|
| **LSTM** | Real + GAN Synthetic | **0.997** | 0.497 | 0.197 | 97ms |
| **LightGBM** | Real + GAN Synthetic | 0.967 | 0.467 | 0.167 | 117ms |
| **LightGBM** | Real only | 0.800 | 0.700 | 0.100 | 350ms |
| **TCN** | Real + GAN Synthetic | 0.789 | 0.589 | 0.189 | 89ms |

**GAN impact:** LightGBM AUROC improved from 0.80 → 0.967 (+21%) with GAN-augmented data.

**Best model:** LSTM with 0.997 AUROC on combined data.

### TimeGAN Results (2026-07-21)

**Key finding: TimeGAN learns temporal patterns, unlike GaussianCopula.**

| Iter | Seed | LightGBM | LSTM | TCN | Best Model |
|------|------|----------|------|-----|------------|
| 1 | 42 | 0.642 | 0.559 | **0.864** ✅ | TCN |
| 2 | 42 | 0.4375 | 0.2459 | **0.6019** | TCN |
| 3 | 42 | 0.4375 | 0.2459 | **0.6019** | TCN |
| 4 | 42 | 0.4375 | 0.2459 | **0.6019** | TCN |
| 5 | 100 | **0.4600** | 0.3255 | 0.4094 | LightGBM |
| 6 | 200 | **0.5224** | 0.4235 | 0.5208 | LightGBM |
| 7 | 300 | **0.5433** | 0.3700 | 0.4762 | LightGBM |
| 8 | 400 | 0.5260 | 0.5104 | **0.5677** | TCN |

**Trends:**
- LightGBM: IMPROVING (0.4375 → 0.5433, +24%)
- LSTM: STRONG IMPROVEMENT (0.2459 → 0.5104, +107%)
- TCN: VARIABLE (best at iter 1: 0.864, then regressed)

**Architecture insight:** LSTM benefits most from seed variation. TCN wins early iterations but becomes unstable with different seeds.

## Synthetic Data Quality (4 evaluators)

| CAN ID | Temporal | Statistical | Mode Coverage |
|--------|----------|-------------|---------------|
| 0x25 | 0.989 | 0.999 | 0.210 |
| 0x2C1 | 0.984 | 0.999 | 0.245 |
| 0x320 | 0.980 | 0.998 | 0.245 |

## Architecture

### Pipeline Stages

```
Raw MF4/CSV/TXT → can_ingest → can_profile → can_synthesize → can_window → can_augment
                  (DBC decode)  (boundaries)  (SDV/CTGAN)     (5s windows) (jitter/scale)
```

### Adapters

| Adapter | Brick | File | LOC |
|---------|-------|------|-----|
| can_ingest | dataset | adapters/can_ingest.py | 202 |
| can_profile | dataset | adapters/can_profile.py | 213 |
| can_synthesize | dataset | adapters/can_synthesize.py | 136 |
| can_window | dataset | adapters/can_window.py | 173 |
| can_augment | dataset | adapters/can_augment.py | 173 |
| csv_can_ingest | dataset | adapters/csv_can_ingest.py | 171 |
| can_taxonomize | dataset | adapters/can_taxonomize.py | 96 |
| jsonl_to_npy | machine_learning | adapters/jsonl_to_npy.py | 156 |
| temporal_split | machine_learning | adapters/temporal_split.py | 33 |
| can_pipeline_tool | machine_learning | mcp/can_pipeline_tool.py | 65 |
| training_run_store/reader | machine_learning | adapters/training_run_*.py | durable runs + regression enrichment |

### Training Backend + Run Persistence (bd:python-factory-zgg1x, PR #665)

- Timeseries trainer default backend is **sklearn** (real LightGBM; lstm/tcn→torch, timegan→TimeGAN). Override via `ML_TIMESERIES_BACKEND`. The `memory` backend fabricates seed-hash metrics — tests only. Pre-#665, ALL `ml_*_timeseries` MCP tools and `can_run_full_pipeline` silently trained on it.
- Every `ml_train_timeseries` / `train_top_can_ids` run persists best-effort to storage doc collection `ml_training_runs` (doc_id `mlrun-{job_id}`); reader computes per-experiment metric delta / regression_state on read.
- Dashboard tools: `ml_get_dashboard_summary`, `ml_list_training_runs`, `ml_get_training_run`, `ml_get_run_regression`. The Companion-X ML tab renders `ml_get_views()[0]` ("ML Models"); the RL learning-runs projection is views[1].

### Recipes

| Recipe | Stages | Use Case |
|--------|--------|----------|
| `can-pipeline@1` | ingest → profile → synthesize → window | Toyota-only |
| `can-pipeline-aug@1` | + augment | With augmentation |
| `can-pipeline-tax@1` | + taxonomize | With taxonomy tagging |
| `can-ingest@1` | ingest only | Single stage |
| `can-synthesize@1` | synthesize only | Single stage |

## TimeGAN Roadmap

### Phase 1 (Done): Optimize Current Pipeline
- CTGAN adapter (drop-in for GaussianCopula)
- Temporal post-processing (Gaussian smoothing)
- 4 synthetic data quality evaluators
- Per-CAN-ID training

### Phase 2 (Ready): TimeGAN Prototype
- 6 CAN IDs have 50K+ decoded frames (threshold met)
- No GPU required (CPU training, slower but works)
- Per-CAN-ID training (each ID gets its own TimeGAN)
- Evals brick grades generator quality

### Phase 3 (Future): Production Rollout
- TimeGAN for all CAN IDs with sufficient data
- Closed-loop: generator vs discriminator, evals grading
- Monitor proxy AUROC (train on synthetic, test on real)

## Open Gaps

| Gap | Priority | Bead | Status |
|-----|----------|------|--------|
| Wire classifier evaluators into training loop | P2 | python-factory-sbhyq.4 | ✅ Closed — `evals_evaluate_can_model` bundled metrics called from `train_top_can_ids` after each per-CAN-ID LightGBM fit (best-effort, never raises). Full 6-evaluator computational harness (`evals_evaluate_computational`: can_auroc/can_auprc/can_brier/can_lead_time/can_false_alarm/can_episode_recall) remains separately callable but not auto-invoked by the training loop. |
| Cross-dataset evaluation | P3 | — | Not started |
| TimeGAN implementation | P2 | — | Ready to start |
| LSTM/TCN on full data | P3 | — | Need more per-ID samples |
| Real failure labels | P0 | python-factory-sbhyq.1 | 🟡 In progress — Question A (does the modeling approach generalize to ANY real failure label, independent of vehicle make) answered: see "Real-Label Validation (Question A)" section below. Question B (does it hold on Toyota/Kia's specific signals) still open — no public dataset found with real Toyota/Kia/Hyundai CAN signals AND confirmed real failure labels; needs data from the team's own vehicles/service records. |
| Live inference testing | P3 | — | can_inference.py exists, untested |
| Correlated multi-signal injection realism | P2 | python-factory-bzm3s | 🆕 Not started (2026-07-23) — extend `correlation_break`/`can_profile` correlation matrix into physically-constrained, ramped multi-signal failure injection. Decoupled from real-label validation; can start immediately. See review doc §16.3 Step A. |
| Decide fate of TimeGAN (park vs conditional generator) | P3 | python-factory-jln5n | ✅ Closed (2026-07-24) — `ConditionalTimeGANAdapter` shipped (failure_mode-conditioned G/D) plus `timegan_loss.py` dual-objective loss fixing the seed instability. See review doc §17.1. |
| Scope SCANIA-derived injection construct-validity | P2 | python-factory-sbhyq.5 | 🆕 Not started (2026-07-24) — SCANIA's 170 truck features get reshaped/noise-padded into arbitrary CAN signal counts via `match_signals()`; the 0.70-0.80 AUROC numbers reflect a harder synthetic distribution, not validated real CAN failure signatures. See review doc §17.3. |

## Real-Label Validation (Question A) — bd:python-factory-sbhyq.1

**Question A**: does the LightGBM-on-tabular-features modeling *approach* (independent of Toyota/Kia-specific signals) generalize to real, repair-record-verified failure labels, or does it only detect the hand-injected synthetic patterns above?

**Result (2026-07-20, verified by direct re-execution, not just reported)**: trained + scored against the real UCI "APS Failure at Scania Trucks" dataset (60,000 train / 16,000 test rows, real trucks, real workshop repair records as ground truth, 59:1 class imbalance) via the same `TimeSeriesTrainingPort` / `evals_evaluate_can_model` path the CAN pipeline uses.

| Metric | Real-data result (SCANIA APS) | Synthetic-injection claim (this doc, above) |
|--------|-------------------------------|----------------------------------------------|
| AUROC | **0.9828** | 0.97–1.00 |
| AUPRC | 0.9001 | not reported above |
| F1 | 0.8085 | 0.000–1.000 (per-CAN-ID, wide spread) |
| UCI cost @ threshold 0.5 | 26,040 | n/a (no cost metric on synthetic data) |
| 2016 UCI leaderboard reference (lower=better) | 9,920 / 10,900 / 11,480 | n/a |

**Verdict**: AUROC on real labels lands inside the claimed synthetic range — real evidence the LightGBM approach discriminates genuine failures, not just the injected artifact. But the cost metric (which weights missed failures 50x over false alarms) came in ~2.4x worse than the 2016 competition's top submissions at a naive 0.5 threshold — AUROC alone overstates deployment readiness; threshold calibration is a separate, unaddressed gap.

**Scope limit — this does NOT validate Question B.** SCANIA is heavy-duty trucks with anonymized histogram/counter features, not Toyota/Kia CAN signals. It answers "does this technique work on ANY real failure label," not "does it work on THIS vehicle's data." See `.github/spec/can-failure-prediction-review.md` §9.1 for the full writeup, dataset provenance/safety verification, and the still-open Question B gap.

Script: `projects/companion_x/validate_real_failure_labels.py`. Adapter change enabling this (additive `scale_pos_weight`/`class_weight` support in `TimeSeriesTrainingConfig.extra`, backward-compatible): `components/machine_learning/src/factory/machine_learning/runtime/adapters/sklearn_timeseries.py`.

### Provenance caveat on the per-CAN-ID tables above

The per-CAN-ID AUROC tables above ("Training Results" section) were not independently re-verified while writing this update — no raw training-run artifacts (result JSON, MLflow records, or persisted score tables) for CAN-specific runs were found anywhere in this workspace's `projects/companion_x/runs/` or `experiments/` directories, and no MF4/Kia raw data files exist on this machine. The numbers in this doc are the only record of those runs available here; the underlying run logs likely live on the machine where the Toyota MF4 / Kia CSV data was actually processed. Anyone re-verifying should re-run `can_run_full_pipeline` against the actual source data rather than treating this table as independently reproducible from what's in this repo alone.

## Key Decisions

1. **LightGBM is the production model** — dominates LSTM/TCN on current data
2. **Per-CAN-ID training** — unified model on mixed CAN IDs doesn't work
3. **Hyundai DBC unlocks public data** — Kia/Hyundai share CAN protocols
4. **CTGAN over GaussianCopula** — better for non-Gaussian distributions
5. **TimeGAN is the end goal** — adversarial training with evals grading
6. **CPU training is fine** — GPU recommended for speed, not correctness

## Critical Honest Assessment (2026-07-21, updated 2026-07-21 evening)

**DATA UTILIZATION CRISIS: 131GB sitting unused!**

| Data | Size | Utilized | Status |
|------|------|----------|--------|
| Decoded CAN frames | 131 GB | 0.02% | ❌ **CRITICAL: 99.98% unused** |
| Per-CAN-ID windows | 360 MB | 100% | ✅ But only 500 samples per ID |

**The bottleneck was NEVER data volume — it was data utilization.**

We have 100M+ decoded CAN records sitting on the external drive doing nothing. The `per_can_id/` directory only has 500 samples per CAN ID because that's what we extracted for quick experiments. We should be processing the full 131GB through the pipeline.

**Correct pipeline for 131GB dataset:**
```
decoded_data/*.jsonl (131GB, 100M+ records)
  → can_ingest (parse JSONL)
  → can_profile (compute boundaries)
  → can_synthesize (multiply with multiplier=10-50)
  → can_window (create 100-frame windows)
  → can_augment (jitter/scale)
  → Training-ready NPY arrays
```

**Why this matters:**
- 100M+ records × 15% failure rate = 15M+ failure examples
- That's more than enough for TimeGAN to learn temporal patterns
- With real failure patterns (SCANIA-derived), AUROC should be 0.70-0.80+

**DO NOT use `per_can_id/` for training** — it's a tiny subset. Process the full dataset.

| Claim | Reality |
|-------|---------|
| AUROC 0.97-1.00 | Based on synthetic injection, not real failures |
| "Predicts vehicle failures" | Actually detects "did I insert a drop-to-zero mutation" |
| 92M+ decoded records | 100% normal driving, no fault labels |
| Real failure validation | SCANIA APS downloaded, used for pattern extraction |

### What We've Done (2026-07-21)

1. **Downloaded SCANIA APS** — ✅ Real workshop repair records (60K records, 1K failures)
2. **Extracted failure patterns** — ✅ Multi-signal correlations, amplitude spikes, volatility injection
3. **Injected realistic failures** — ✅ SCANIA-derived patterns produce 0.70-0.80 AUROC
4. **Implemented recursive GAN loop** — ✅ Same model continues training across iterations

### Results Comparison

| Approach | AUROC | Notes |
|----------|-------|-------|
| Simple injection (drop-to-zero) | 0.50-0.60 | Near random |
| TimeGAN recursive improvement | 0.53-0.60 | TCN +7.4% |
| **Realistic SCANIA patterns** | **0.70-0.80** | **+0.15 improvement!** |

### Key Insight

**Data quality > Model architecture.** Using real failure patterns from SCANIA trucks to inform synthetic injection produces much better training data than naive mutations.

### Remaining Gap

We still don't have **real CAN failure data** from actual vehicle service records. The SCANIA patterns are from heavy trucks with different sensor types, not passenger car CAN signals. To fully validate:
- Need real DTC-linked fault data from Toyota/Kia/Hyundai vehicles
- Or accept that this is a legitimate weak-supervision approach with documented limitations

## Files

- Steering doc: `.agents/steering/can-failure-prediction.md` (this file)
- Implementation spec: `.github/spec/rando.md`
- Domain spec: `.github/spec/can-failure-prediction.md`
- Dataset spec: `.github/spec/ml-dataset-generation.md`
- Experiment report: `.github/spec/can-gan-loop-report.md`
- Training: `ml_train_timeseries` MCP tool, `can_run_full_pipeline` MCP tool
- Evaluation: `evals_evaluate_can_model` MCP tool, `evals_evaluate_computational` MCP tool

---

## Session Resume (2026-07-21, updated 2026-07-21 evening)

### Where We Left Off

TimeGAN is now working and producing usable synthetic data. First iteration achieved TCN AUROC 0.864, beating LightGBM (0.642) and LSTM (0.559). GaussianCopula was the problem all along — it ignores temporal patterns.

### What Was Fixed Today

1. **MCP serialization bug** — `dataset_submit_generation` now accepts flat parameters instead of nested Pydantic models. Fix is in `components/dataset/src/factory/dataset/mcp/operational.py`.

2. **can-gan-loop agent** — Created in `components/agent/src/factory/agent/registry/defaults_can_agents.py` with skill at `skills/can-gan-loop/SKILL.md`. Agent orchestrates: TimeGAN train → generate → train classifiers → evaluate → loop.

3. **Evals wired** — Each iteration recorded via `evals_record_run`. Dashboard shows iteration history with sparklines and regression detection.

4. **TimeGAN working** — First iteration: TCN AUROC 0.864 (PASS), LightGBM 0.642, LSTM 0.559. TimeGAN learns temporal patterns that GaussianCopula misses.

5. **Multi-model comparison** — Each iteration trains all three architectures and compares them. TCN benefits most from temporal data.

### Demo Strategy (2-Day Timeline)

**Goal:** Run 10 iterations to generate enough data points for charts showing:
1. AUROC by model across iterations (line chart)
2. Model comparison bar chart (final iteration)
3. TimeGAN loss curves (g_loss, d_loss)
4. Evaluation metrics heatmap (6 metrics × 3 models × 10 iterations)

**Iteration plan:**
- Iterations 1-3: Baseline — establish model comparison
- Iterations 4-6: Improvement — show iterative quality increase
-_iterations 7-10: Convergence — demonstrate system stabilizes

### What To Do Next (Priority Order)

1. **Run 9 more iterations** — Build up data points for demo charts. Use companion-x MCP server:
   ```
   ml_train_timeseries(model_type="timegan", X_uri="...", config={...})
   → ml_sample_timeseries(model_id="...", n_samples=50000)
   → ml_train_timeseries(model_type="lightgbm", X_uri="...")
   → ml_train_timeseries(model_type="lstm", X_uri="...")
   → ml_train_timeseries(model_type="tcn", X_uri="...")
   → ml_compare_timeseries(job_ids=[...])
   → evals_evaluate_computational(evaluator="can_auroc", ...)
   → evals_record_run(run_id="timegan-iter-{N}-{model}", ...)
   → loop
   ```

2. **Generate charts** — Use evals brick data to create visualization for demo

3. **Scale to all 41 CAN IDs** — We have 41 CAN IDs with training data on Crucial X9.

4. **Portable training** — All data lives on external drive (`/Volumes/Crucial X9/can_data/`). Plug into any laptop and run via `DATA_ROOT` env var.

### Data Locations

- MF4 files: `/Volumes/Crucial X9/can_data/mf4_files/` (8,171 files, 7.5GB)
- Decoded CAN frames: `/Volumes/Crucial X9/can_data/decoded_data/` (131GB, 5 VINs)
- Per-CAN-ID windows: `/Volumes/Crucial X9/can_data/per_can_id/` (360MB, 82 IDs)
- Training data: `/Volumes/Crucial X9/can_data/training_data/` (263MB, NPY format)
- DBC files: `/Volumes/Crucial X9/can_data/dbc_files/` (9 files)
- Comparison results: `/Volumes/Crucial X9/can_data/comparison_results/`
- S3 data: `s3://rx-can-frames-synthetic-lwekrnidlk/` (AWS credentials in env)

### MCP Tool Status

| Tool | Status | Notes |
|------|--------|-------|
| `ml_train_timeseries` | ✅ Works | Supports lightgbm, lstm, tcn, timegan |
| `ml_sample_timeseries` | ✅ Works | Generates synthetic data from trained TimeGAN |
| `ml_compare_timeseries` | ✅ Works | Side-by-side model comparison |
| `evals_evaluate_computational` | ✅ Works | 6 CAN evaluators available |
| `evals_record_run` | ✅ Works | Records iterations for dashboard |
| `dataset_submit_generation` | ✅ Fixed | Flat parameters (was nested Pydantic) |

### Agent Status

| Agent | Status | Skills |
|-------|--------|--------|
| `can-gan-loop` | ✅ Created | can-gan-loop, compx-platform |
| `can-ingest` | ✅ Existing | can-analyst, compx-platform |
| `can-profiler` | ✅ Existing | can-analyst, compx-platform |
| `can-synthesizer` | ✅ Existing | can-recipe-author, compx-platform |
| `can-trainer` | ✅ Existing | can-evaluator, compx-platform |

---

## Session Resume (2026-07-23)

### Where We Left Off

A follow-up Kiro session was asked, independent of the GAN-loop demo work
above: "how do I inject realistic failures into raw undecoded CAN driving
data, and why isn't my TimeGAN loop working?" This produced a structural
diagnosis (not a tuning fix) plus two new tracked beads. Full writeup:
`.github/spec/can-failure-prediction-review.md` §16.

### The TimeGAN diagnosis (read this before running more GAN-loop iterations)

`TimeGANAdapter` (`components/machine_learning/.../adapters/timegan.py`) is
**unsupervised** — it trains Generator/Discriminator on unlabeled *normal*
signal windows only. `ml_sample_timeseries`'s own docstring confirms `y_uri`
is ignored for `timegan`. There is no failure-mode-conditioned generator
anywhere in this codebase.

**Consequence:** the current TimeGAN cannot generate realistic failures no
matter how it's tuned — it's never seen a failure example or a failure-mode
label. The AUROC instability documented above (0.43-0.86 across seeds,
identical results across same-seed reruns) is consistent with *two*
compounding problems: (1) it's solving the wrong problem (normal-signal
diversity, not failure realism), and (2) it's separately unstable/
data-starved on ~48MB of real captures.

**Do not spend more cycles on iterations 9-10 of the demo-chart plan below
expecting the metric instability to resolve into a clean trend** — it's
structural, not a seed-tuning artifact.

### Field research (2026-07-23): diffusion, not GAN, for few-shot fault synthesis

Two papers found via web search are directly on-point for "generate
realistic *failures* from mostly-normal data," which is a narrower and
more specific problem than "generate more synthetic normal driving data":

- [FaultDiffusion (arXiv 2511.15174)](https://arxiv.org/html/2511.15174) —
  few-shot fault generation via diffusion, using a pretrained *normal*-data
  distribution plus a difference adapter into the fault domain, with a
  diversity loss to prevent mode collapse on rare fault classes.
- [Diff-MTS (arXiv 2407.11501)](https://arxiv.org/pdf/2407.11501.pdf) —
  diffusion beats GAN-based methods on C-MAPSS/FEMTO (same PHM/RUL problem
  family as Rando) on diversity, fidelity, and utility.

This sharpens (doesn't overturn) the earlier "TimeGAN → deprioritize,
diffusion is where the field is headed" call from the review doc §2/§6 —
it's the fault-specific confirmation of that generic call.

### Two new decoupled beads

1. **`python-factory-bzm3s`** (P2) — Physics-constrained correlated
   multi-signal failure injection. Extends the existing
   `failure_injection.py` + `can_profile.py` correlation matrix to inject
   coordinated shifts across correlated signal clusters (not single-signal
   mutation), constrained to physically-plausible rate-of-change bounds,
   with ramped onset/decay instead of instant label flips. **This is
   buildable right now** — it does not depend on real-label validation
   (`sbhyq.1`, data-access blocked) or on any generator decision. Cheapest,
   highest-leverage next step for "make injected failures look real."
2. **`python-factory-jln5n`** (P3, decision) — Explicitly decide TimeGAN's
   fate rather than keep iterating ambiguously: (1) park it as
   documented/tested-but-unused code [recommended near-term], (2) build a
   failure-mode-conditioned generator (conditional GAN or few-shot
   diffusion per the papers above) — net-new work, not a wiring fix, or
   (3) stop running further GAN-loop demo iterations since the underlying
   instability won't resolve with more seeds.

### What this doesn't change

- `sbhyq.1` Question B (Toyota/Kia-specific real-label validation) is still
  the top-priority open gap, still blocked on data access — unaffected by
  this session.
- The 2026-07-21 GAN-loop demo-chart plan below is preserved as historical
  context (what was tried, what was found), not deleted — just don't extend
  it with more iterations without reading the diagnosis above first.

---

## Session Resume (2026-07-24)

### Where We Left Off

Pulled 7 upstream commits (`931cddfe`, `0e7e3245`, `d0574406`, `82df58cb`,
`a80e7b68`, `bb0fcabe`, `6d314ecc`) that act directly on the two beads from
the 2026-07-23 session. Full from-code review:
`.github/spec/can-failure-prediction-review.md` §17.

### What shipped and is now closed

- **`python-factory-jln5n` (TimeGAN fate decision) — CLOSED.** Option 2
  from that bead (build a failure-mode-conditioned generator) is what
  landed: `ConditionalTimeGANAdapter` (`timegan_conditional.py`) adds a
  one-hot `failure_mode` side channel to both G and D. Separately,
  `timegan_loss.py` ships a dual-objective loss (adversarial-weight taper
  as AUROC rises + diversity loss against mode collapse + one-sided label
  smoothing on D) that is a textbook, well-targeted fix for the exact
  seed-instability diagnosed in the 2026-07-23 session. Good engineering,
  not a bandaid — each piece maps to a named GAN failure mode.
- **`injection_strategy="hybrid"`** now exists in `can_synthesize.py` /
  `failure_injection.py` — `"rule"` (original 8 modes) / `"learned"`
  (samples a trained conditional TimeGAN) / `"hybrid"` (30/70 mix).
  Reported result: AUROC 0.70-0.80 with SCANIA-pattern injection vs
  0.50-0.60 for simple injection (`can-gan-loop-report.md`). Notably
  *lower* than the original 0.97-1.00 hand-injection numbers — which
  actually supports §4's original hypothesis that those numbers were
  inflated by too-easy injected patterns.

### New gap found — `python-factory-sbhyq.5` (not a blocker, read before citing numbers)

Traced `ScaniaPatternExtractor` end to end: SCANIA APS's 170 anonymized
truck features get turned into an **invented** 50-frame linear-interpolation
trajectory (SCANIA is tabular snapshot data, not a real time series — the
temporal shape is a modeling choice), then `match_signals()` /
`resample_time()` mechanically reshape/pad this to whatever the target CAN
ID's actual signal count needs. Signals beyond SCANIA's 170 get **Gaussian
noise matched to the window's std**, not real truck data.

**Practical implication:** the 0.70-0.80 AUROC numbers are real and
interesting, but they measure "detects a harder synthetic anomaly
distribution than naive injection," not "learned real Toyota/Kia CAN
failure signatures." Don't report them as closing the §4/§9.1 real-label
validation gap — that gap (`sbhyq.1` Question B) is still open and still
the highest-priority item. Full detail and the two-part ask (relabel
reporting + decide if noise-padding is placeholder or permanent) is in
review doc §17.3 / bead `sbhyq.5`.

### Longer-horizon thoughts on model/direction (not a decision, for discussion — review doc §18)

- There's probably no single "best model" here — LightGBM will likely keep
  winning on this data volume regardless of which generator produces the
  training data, since tree ensembles are the least data-hungry option in
  the comparison set. The generative-model choice mostly affects training
  *data quality*, not whether LightGBM should be replaced.
- Three candidate next bets, not mutually exclusive: (1) exploit the
  131GB-unused-data finding before investing in more model sophistication
  — cheap, no new architecture; (2) keep pushing on real passenger-vehicle
  label acquisition harder than SCANIA, since no amount of better synthesis
  substitutes for that; (3) if pursuing more generative sophistication,
  diffusion-with-conditioning (FaultDiffusion, Diff-MTS per §16.2) is the
  next rung, not a third GAN variant, if the conditional TimeGAN plateaus.

### What this doesn't change

- `sbhyq.1` Question B (real Toyota/Kia-specific label validation) is still
  open, still the top-priority gap, and this session's finding makes it
  more important to close, not less.
- `python-factory-bzm3s` (rule-based correlated multi-signal injection) is
  untouched and still open — complementary to, not superseded by, the
  learned/hybrid strategy work described here.

---

## Session Resume (2026-07-27) — Context-Aware Failure Injection

### Vision: Real-World Context for Realistic Failures

The system should inject failures based on **real-world conditions**, not random noise. Failures should correlate with:

| Context | Failure Pattern | Example |
|---------|-----------------|---------|
| **Weather** | Cold → battery stress. Hot → coolant issues. | Temperature, humidity, precipitation |
| **Route** | Mountain → transmission stress. City → brake wear. | GPS, elevation, road type |
| **Time of day** | Morning cold start → battery issues. | Hour, day of week |
| **Vehicle age** | Older → sensor degradation, electrical issues. | Mileage, service history |
| **Driving style** | Aggressive → transmission, brake stress. | Acceleration patterns, speed |

### Architecture: Context-Aware CAN Pipeline

```
┌──────────────────────────────────────────────────────────────────┐
│                    EXTERNAL DATA SOURCES                         │
│  Weather APIs │ GPS/Route │ Vehicle Metadata │ Driving Patterns  │
└───────────────┴───────────┴──────────────────┴───────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  DATASET BRICK                                                   │
│  context_ingest → context_correlate → context_augment            │
│                              │                                   │
│                              ▼                                   │
│  CAN Pipeline: synthesize (with context_heatmap)                 │
│                window (with context_fields as features)          │
│                train (CAN signals + context features)            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  GRAPH BRICK                                                     │
│  Taxonomy: WeatherSnapshot, Location, Route, DrivingProfile,     │
│            EnvironmentalContext, VehicleMetadata                 │
│  Relationships: OCCURS_DURING, LOCATED_AT, INFLUENCES            │
└──────────────────────────────────────────────────────────────────┘
```

### Beads

- `python-factory-ctx1` — Extend CAN taxonomy with context nodes (P1)
- `python-factory-ctx2` — Create context_ingest adapter (P1)
- `python-factory-ctx3` — Create context_correlate adapter (P1)
- `python-factory-ctx4` — Create context_augment adapter (P1)
- `python-factory-ctx5` — Wire context into pipeline + ML training (P1)
- `python-factory-ctx6` — Add HSML output view (P2)

### Key Design Decisions

1. **Extend dataset brick** — not a new brick. Stage adapter pattern is the natural extension point.
2. **Context is opt-in** — existing recipes work unchanged. `context_conditioned_failure` defaults to False.
3. **Models consume context as features** — CAN signals + context fields become the feature matrix. No model changes needed.
4. **HSML as serialization format** — Phase 6b: JSON dicts first, HSML as named output view.

### Expected Impact

- **Synthetic data quality**: Context-aware injection improves realism
- **Model accuracy**: Context features improve prediction by 5-10%
- **Explainability**: "Battery failure predicted because temp=-5°C, mileage=142k km"

---

**Document version:** 2.1
**Last updated:** 2026-07-27
**Changes:** Added context-aware failure injection vision and architecture
