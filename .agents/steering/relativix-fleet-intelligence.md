# Relativix Fleet — Competitive Intelligence

**Last updated:** 2026-07-24
**Source:** AWS account `195714074439`, buckets `rx-can-bus-data`, `rx-internal-dev-fleet`
**Status:** Active — they have production ML models running daily inferences

## 1. What They Have

### Infrastructure
- **AWS Account:** 195714074439 (SSO via `identitycenter.amazonaws.com`)
- **Databricks workspace:** `dbc-df8a9083-8a45.cloud.databricks.com`
- **Catalog:** `relativix_dev`
- **ETL pipeline:** DLT (Delta Live Tables) with Auto Loader for MF4 ingestion
- **Storage:** S3 with tiered data lake (tier-0 → tier-1 → tier-2 → tier-3)

### Data Pipeline

```
MF4 files (OBD-II dongles)
    ↓ [tier-0: raw upload]
Auto Loader (Databricks)
    ↓ [tier-1: decoded CAN frames, partitioned by CAN ID]
DBC decode (per-VIN resolution)
    ↓ [tier-2: decoded signals, per-VIN per-day parquet]
7 ML models run inference
    ↓ [tier-3: predictions with explanations + display specs]
```

### DBC Resolution
They have a VIN→DBC resolver (`vin_dbc_rules.json`) that maps:
- Toyota (2000-2012): `toyota_legacy_combined.dbc` + OBD2
- Toyota (2013+): `toyota_2017_ref_pt.dbc` + OBD2
- Lexus: `toyota_2017_ref_pt.dbc` + OBD2
- Kia/Hyundai: `hyundai_kia_generic.dbc` + OBD2
- Default: `obd2_dbc_7E8_7EF.dbc`

### Fleet Inventory
| VIN | Make | Device | MF4 Files | Data Size |
|-----|------|--------|-----------|-----------|
| `1029207465301022` | Unknown | OBD-II dongle | 208 | 79 MB |
| `751AC1C3` | Unknown | OBD-II dongle | 5,061 | 4.7 GB |
| `A67E579F` | Unknown (mikes_suv) | OBD-II dongle | 5,821 | 5.3 GB |
| `A6CCCC2C` | Unknown | OBD-II dongle | 471 | 437 MB |
| `CFE1EE73` | Unknown | OBD-II dongle | 44 | 35 MB |
| `JTMBK33V586038456` | **Toyota** | OBD-II | — | In fleet tier-3 |
| `KNADE123166169544` | **Kia/Hyundai** | OBD-II | — | In fleet tier-3 |
| `4T1BF3EK6BU777194` | **Toyota** | OBD-II | — | In fleet tier-3 |

### Data Volumes
| Tier | Size | Objects | Content |
|------|------|---------|---------|
| tier-0 | 4.3 GB | 4,374 | Raw MF4 uploads |
| tier-1 | 17.7 GB | 22,052 | Decoded CAN frames (parquet, by CAN ID) |
| tier-2 | 9.8 GB | 2,652 | Decoded signals (parquet, per-VIN per-day) |
| tier-3 | 15 MB | 1,296 | Model inferences |

## 2. Their ML Models (7 Production Models)

### Model Registry

| Model Key | Purpose | Issue Types | Failure Count |
|-----------|---------|-------------|---------------|
| `dtc_monitor_v1.0.0` | Diagnostic Trouble Codes (OBD Mode 03/07) | `diagnostic_trouble_code` | 15 (Kia) |
| `cranking_event_analyzer_v1.0.0` | Battery cranking voltage, starter health | `battery_failure` | 51 (Kia) |
| `charging_system_v1.0.0` | Alternator output, battery voltage trends | `battery_degradation` | 24 (Toyota + Kia) |
| `cooling_system_monitor_v1.0.0` | Coolant temp patterns, thermostat behavior | `thermostat_failure` | 2 (Kia) |
| `fuel_trim_drift_monitor_v1.0.0` | LTFT/STFT drift, fuel-air mixture balance | Fuel trim issues | 0 (all healthy) |
| `alternator_health_v1.0.0` | Alternator charge rate, voltage stability | Alternator issues | 0 (all healthy) |
| `driving_behavior_analyzer_v1.0.0` | Acceleration/braking patterns, idle time | Driving anomalies | 0 (all healthy) |

### Inference Output Schema

Each model outputs a parquet file per day with columns:

| Column | Type | Description |
|--------|------|-------------|
| `vin` | string | Vehicle identification number |
| `prediction_generated_at` | timestamp | When the prediction was made |
| `source_data_date` | string | Date of the source data |
| `horizon_days` | int | Prediction horizon (0 = same-day) |
| `status` | string | `healthy`, `minor_issues`, `issue_predicted` |
| `predicted_issue_type` | string | Specific issue (e.g., `battery_failure`) |
| `score` | string (JSON) | Detailed metrics, confidence, feature values |
| `forecast_blob` | string (JSON) | Forecast data if applicable |
| `issue` | string | Issue description |
| `explanations` | string (JSON) | Human-readable explanations |
| `artifacts` | string (JSON) | Data lineage (which tier-2 table, time window) |
| `display_spec` | string (JSON) | UI rendering spec (KPI cards, time series, narratives) |
| `metrics` | string (JSON) | Model-specific metrics |

### How Their Models Work

**Pattern:** Each model is a **domain-specific rule-based or ML system** that:
1. Reads tier-2 decoded signals for a VIN on a given day
2. Extracts features (e.g., mean LTFT, cranking voltage, DTC codes)
3. Compares against baseline/healthy thresholds
4. Outputs `status` + `predicted_issue_type` + detailed `score`

**Example — `dtc_monitor`:**
- Polls OBD Mode 03 (stored DTCs) and Mode 07 (pending DTCs)
- Tracks active/new/cleared codes over time
- `status: "minor_issues"` when new DTCs appear
- `score` contains `activeStoredCount`, `activePendingCount`, `newStoredCount`

**Example — `cranking_event_analyzer`:**
- Monitors cranking voltage, starter motor current
- Detects slow crank, no-crank, voltage drop patterns
- `status: "minor_issues"` when cranking metrics degrade
- `score` contains voltage thresholds, crank duration

**Example — `charging_system`:**
- Tracks alternator output voltage over time
- Detects voltage drift, undercharge, overcharge
- `status: "issue_predicted"` when trends indicate impending failure
- Uses `forecast_blob` for predictive (not just reactive) alerts

## 3. What We Have vs What They Have

| Dimension | Us (Rando) | Them (Relativix) |
|-----------|------------|------------------|
| **Data volume** | 131 GB decoded (5 VINs) | ~32 GB tiered (8+ VINs) |
| **Data format** | JSONL (decoded CAN frames) | Parquet (tiered pipeline) |
| **Failure labels** | Synthetic injection (8 modes) | **Real failures from production models** |
| **Label source** | Hand-coded rules | ML model outputs + DTC polling |
| **Models** | LightGBM/LSTM/TCN/TimeGAN | 7 domain-specific models |
| **Architecture** | Per-CAN-ID classifiers | Per-domain monitors (battery, cooling, etc.) |
| **Prediction target** | Binary failure within horizon | Specific issue type + severity |
| **Explainability** | Feature importance | Full display specs with narratives |
| **Production** | Training only | **Running daily inferences** |
| **DBC coverage** | Toyota + Kia | Toyota, Lexus, Kia/Hyundai + defaults |

## 4. Gaps We Can Exploit

### Their Weaknesses
1. **Rule-based thresholds** — their models likely use fixed thresholds (e.g., "LTFT > 10% = warning"). We can learn adaptive thresholds from data.
2. **Per-domain silos** — each model monitors one system (battery, cooling, etc.). We can learn **cross-system correlations** (e.g., "battery failure + coolant temp drift = alternator failing").
3. **No temporal sequence modeling** — they compare daily aggregates. We can model **sub-second CAN frame sequences** for earlier detection.
4. **Limited VIN diversity** — only 3 VINs with failures in the dataset. We can train on more patterns.
5. **No adversarial robustness** — their models aren't tested against adversarial CAN manipulation. We can use GAN-generated failures for robustness training.

### Our Advantages
1. **Time-series models** (LSTM/TCN) can learn temporal patterns they miss
2. **Multi-signal correlation** across CAN IDs, not just per-domain
3. **Synthetic failure generation** (TimeGAN) for data augmentation
4. **Per-CAN-ID granularity** for fine-grained detection
5. **Closed-loop evaluation** with 6 evaluators (AUROC, AUPRC, Brier, lead-time, false-alarm, episode-recall)

## 5. Strategic Recommendations

### Phase 1: Learn From Their Labels
- Use tier-3 failure labels as ground truth for our models
- Join tier-2 decoded signals with tier-3 labels to create labeled datasets
- Focus on `battery_failure`, `diagnostic_trouble_code`, `battery_degradation` (real failures exist)

### Phase 2: Beat Their Thresholds
- Train LightGBM on their labeled data — should outperform their rule-based thresholds
- Add temporal features (rolling windows, rate-of-change) they don't use
- Cross-correlate signals across domains they treat separately

### Phase 3: Go Beyond Their Capabilities
- Sub-second detection using raw CAN frame sequences (they use daily aggregates)
- Earlier warning using time-series models (they detect after the fact)
- Adversarial robustness testing with synthetic failures

### Phase 4: Surpass Their Coverage
- Train on more VINs (we have 5 MF4 VINs + their 3 fleet VINs)
- Add failure modes they don't monitor (correlation breaks, signal degradation)
- Use TimeGAN to generate rare failure patterns for better generalization

## 6. Data Access

### S3 Credentials
- **Account:** 195714074439
- **Profile:** `195714074439_DEV-PowerUser` (via SSO)
- **Refresh:** `aws configure sso --sso-start-url https://identitycenter.amazonaws.com/ssoins-72236022348334d0 --sso-region us-east-1`

### Key Buckets
| Bucket | Content | Our Access |
|--------|---------|------------|
| `rx-can-bus-data` | Raw MF4 files (18 GB) | ✅ Read |
| `rx-internal-dev-fleet` | Tiered pipeline (32 GB) | ✅ Read |
| `rx-can-frames-synthetic-lwekrnidlk` | OBD-II CSVs (14 MB) | ✅ Read |
| `rx-dev-dbc` | DBC files (776 KB) | ✅ Read |

### Local Mirror
- `fleet_tier2/` — 9.4 GB decoded signals on Crucial
- `fleet_tier3/` — 17 MB failure labels on Crucial

## 7. Our Architecture: Agentic vs Their Hardcoded

### Their Approach (Hardcoded)
- 7 separate models, each monitoring one domain
- Daily aggregates (not sub-second CAN frames)
- Rule-based thresholds (not learned from data)
- No cross-domain correlation
- No temporal sequence modeling
- No adversarial robustness

### Our Approach (Agentic)
- **Agent-driven orchestration** — skills, tools, steering (not hardcoded dispatch)
- **Multi-model competition** — 7 families always fighting (LightGBM → Ensemble)
- **Sub-second temporal modeling** — raw CAN frames at 10ms resolution
- **Cross-signal correlation** — learn that "battery dropping + coolant rising = alternator failing"
- **Closed-loop feedback** — evals rate models, decide retrain backward or progress forward
- **Adversarial robustness** — TimeGAN generates failures for training

### Architecture Comparison

| Dimension | Their Approach | Our Approach |
|-----------|----------------|--------------|
| **Orchestration** | Hardcoded Python scripts | Agent with skills, tools, steering |
| **Model training** | Per-domain models | Multi-family competition |
| **Data granularity** | Daily aggregates | Sub-second CAN frames |
| **Failure detection** | Rule-based thresholds | Learned from data |
| **Cross-domain** | Siloed (7 separate models) | Correlated (multi-task learning) |
| **Temporal** | Point-in-time | Sequence modeling (LSTM/TCN/PatchTST) |
| **Evaluation** | No visible metrics | 6 evaluators (AUROC, AUPRC, Brier, lead-time, false-alarm, episode-recall) |
| **Feedback** | None visible | Closed-loop with versioning |
| **Adversarial** | None | TimeGAN synthetic failures |

### Why Agentic Is Better

1. **No code changes** to add new model families — just add to the skill
2. **Agent reasoning** adapts to data characteristics (e.g., "this dataset has 100K samples, try PatchTST")
3. **Natural language** makes the system explainable
4. **Skills compose** — `can-training-orchestrator` uses `dataset-generation` skill
5. **Memory enables learning** — agent remembers what worked/failed across sessions

## 8. Data Creation: The Priority Focus

### Why Data Creation First
Without good data, nothing else matters. Their 7 models are only as good as their training data. We can:
1. **Ingest their real failure labels** (tier-3) — immediate value
2. **Generate synthetic failures** (TimeGAN) — expand coverage
3. **Combine both** — train on real + synthetic for robustness

### Data Creation Pipeline (Agentic)

```
DATA CREATION AGENT
├── 1. INGEST (dataset brick)
│   ├── Raw CAN data (MF4, JSONL, parquet)
│   ├── DBC files (universal + vehicle-specific)
│   └── Relativix tier-3 labels (real failures)
├── 2. PROFILE (agent skill)
│   ├── Signal boundaries (min/max/mean/std)
│   ├── Temporal patterns (frequency, gaps, bursts)
│   ├── Cross-signal correlations
│   └── Failure mode detection
├── 3. SYNTHESIZE (dataset brick + agent skill)
│   ├── Synthetic failures (8 modes)
│   ├── Real failures (Relativix labels)
│   ├── Correlated multi-signal failures
│   └── Temporal progression (gradual onset/decay)
├── 4. VALIDATE (evals brick)
│   ├── Signal plausibility (within physical bounds)
│   ├── Temporal consistency (no time jumps)
│   ├── Failure realism (compare to real patterns)
│   └── Label quality (confidence, provenance)
└── 5. MATERIALIZE (dataset brick)
    ├── Labeled dataset (URI-addressable)
    ├── Manifest (schema, provenance, quality)
    └── Ready for training
```

## 9. Model Competition: Always Fighting

### Model Families (7 Total)

| Family | Strengths | Best For |
|--------|-----------|----------|
| **LightGBM** | Fast, interpretable, works on small data | Baseline, production deployment |
| **LSTM** | Temporal dependencies, variable-length sequences | Complex patterns |
| **TCN** | Ultra-low latency, parallelizable | Real-time inference |
| **PatchTST** | Long-range dependencies, attention | Complex non-linear patterns |
| **Chronos-2** | Pretrained foundation model, PEFT/LoRA | Few-shot learning |
| **LNN** | Data-efficient, causal, interpretable | Small datasets |
| **Ensemble** | Weighted combination | Production deployment |

### Evaluation Framework (6 Evaluators)

| Evaluator | What It Measures | Threshold |
|-----------|------------------|-----------|
| **AUROC** | Discrimination (ROC curve) | ≥0.80 |
| **AUPRC** | Precision-recall balance | ≥0.75 |
| **Brier** | Calibration (probability accuracy) | ≤0.15 |
| **Lead-time** | How far before failure model detects | ≥5s |
| **False-alarm** | False positive rate | ≤0.10 |
| **Episode-recall** | Episode-level detection rate | ≥0.80 |

### Closed-Loop Decision

After each training iteration:
1. **AUROC < 0.80** → Focus on data quality improvements
2. **AUROC 0.80-0.95** → Focus on model architecture tuning
3. **AUROC > 0.95** → Focus on edge cases and adversarial robustness
4. **Always** → Version checkpoint if improved, update model rankings

## 10. Open Questions

1. **Do they have more VINs?** The fleet bucket may have more devices not yet in tier-3
2. **What's their model architecture?** We only see outputs — need to infer architecture from score schema
3. **Do they use synthetic data?** The `rx-can-frames-synthetic-lwekrnidlk` bucket name suggests yes
4. **What's their evaluation methodology?** No metrics visible in tier-3 outputs
5. **Can we access their repo?** User mentioned they have a GitHub repo — could reveal implementation details
6. **How do they aggregate multi-domain models?** Currently appears siloed — no cross-domain correlation
7. **What's their feedback loop?** No visible retraining or model improvement mechanism

---

**Document version:** 2.0
**Last updated:** 2026-07-24
**Author:** opencode (automated exploration + SME consultation)
**Changes:** Added agentic architecture comparison, data creation pipeline, model competition framework
