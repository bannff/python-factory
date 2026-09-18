# CAN Agentic Orchestration — Design Spec

**Date:** 2026-07-24
**Status:** Draft
**Author:** opencode + SME consultation
**Epic:** python-factory-dth

## 1. Overview

This spec defines an **agentic architecture** for CAN failure prediction that replaces hardcoded Python scripts with agent-driven orchestration. The system uses skills, tools, and steering to orchestrate data creation, model training, evaluation, and feedback loops.

### 1.1 Why Agentic?

| Hardcoded Approach | Agentic Approach |
|-------------------|------------------|
| Code changes to add new models | Add to skill file |
| Python dispatch chains | Agent reasoning adapts |
| No explainability | Natural language decisions |
| Rigid workflows | Flexible, composable skills |
| No memory across sessions | Memory brick enables learning |

### 1.2 Core Principle

**The system itself is agentic.** Agents with skills, tools, and steering orchestrate the entire pipeline. Code exists only in bricks (dataset, ML, evals) as MCP tools. Orchestration logic lives in skill files and agent reasoning.

## 2. Architecture

### 2.1 Important: Relationship to Existing Agents

> **Meta-architect note:** This design extends, not replaces, the existing CAN agents.
> The existing pipeline (`can-pipeline` graph in `defaults_can_pipeline.py`) already has:
> - `can-ingest` — ingests raw CAN data
> - `can-profiler` — profiles signal boundaries
> - `can-synthesizer` — generates synthetic failures
> - `can-trainer` — trains models
> - `can-gan-loop` — runs GAN training loop
>
> The new agents **augment** this pipeline:
> - `can-data-creator` — adds Relativix label integration (new capability)
> - `can-training-orchestrator` — adds multi-family competition (extends can-trainer)
> - `can-evaluator` — adds 6-evaluator framework (new capability)
> - `can-feedback-loop` — adds closed-loop improvement (new capability)
>
> The graph executor IS the orchestrator. We don't need a meta-agent.

### 2.2 Agent Roles

```
┌─────────────────────────────────────────────────────────────┐
│                    CAN ORCHESTRATION AGENTS                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  CAN Data Creator Agent (NEW)                                │
│  ├── Skill: can-data-creator                                 │
│  ├── Tools: dataset_submit_generation (recipe-driven)        │
│  ├── Purpose: Integrate Relativix labels into datasets       │
│  └── Output: URI-addressable dataset artifact                │
│                                                              │
│  CAN Training Orchestrator Agent (EXTENDS can-trainer)       │
│  ├── Skill: can-training-orchestrator                        │
│  ├── Tools: ml_train_timeseries, ml_compare_timeseries       │
│  ├── Purpose: Train multiple model families in competition   │
│  └── Output: Versioned model checkpoints                     │
│                                                              │
│  CAN Evaluation Agent (NEW)                                  │
│  ├── Skill: can-evaluator                                    │
│  ├── Tools: evals_evaluate_can_model, evals_record_run       │
│  ├── Purpose: Evaluate models with 6 evaluators              │
│  └── Output: Model rankings and performance metrics          │
│                                                              │
│  CAN Feedback Loop Agent (NEW)                               │
│  ├── Skill: can-feedback-loop                                │
│  ├── Tools: memory_store, memory_retrieve, events_publish    │
│  ├── Purpose: Closed-loop improvement via evals              │
│  └── Output: Retraining decisions, version updates           │
│                                                              │
│  Graph Executor (EXISTING — IS the orchestrator)             │
│  ├── Graph: can-pipeline                                     │
│  ├── Nodes: can-ingest → can-profiler → can-synthesizer     │
│  │         → [can-data-creator] → can-trainer → [evaluator]  │
│  └── Purpose: Sequence agent execution                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Skill Files

Each agent has a skill file that defines:
- **Role**: What the agent does
- **Tools**: Which MCP tools to use
- **Workflow**: Step-by-step process
- **Decision logic**: How to adapt to different situations
- **Output format**: What to return

### 2.4 Tool Dependencies

> **Meta-architect note:** `can_profile`, `can_synthesize`, `can_augment` are NOT standalone MCP tools.
> They are dataset stage adapters invoked through recipes via `dataset_submit_generation`.
> The correct pattern is recipe-driven, not direct tool calls.

```
dataset brick MCP tools
├── dataset_submit_generation (recipe-driven)
├── dataset_get_job
├── dataset_get_artifact
├── dataset_resolve_artifact
└── can_* (CAN-specific recipe stages, invoked via recipes)

machine_learning brick MCP tools
├── ml_train_timeseries
├── ml_continue_timeseries
├── ml_sample_timeseries
├── ml_compare_timeseries
└── ml_list_models

evals brick MCP tools
├── evals_evaluate_can_model
├── evals_evaluate_computational
├── evals_record_run
├── evals_get_run_regression
└── evals_compare_benchmarks

memory brick MCP tools
├── memory_store
├── memory_retrieve
└── memory_search_by_time

events brick MCP tools
└── events_publish (NOT events_dispatch)
```

### 2.5 Model Family Support

> **Meta-architect note:** Currently `ml_train_timeseries` only supports:
> `lightgbm`, `lstm`, `tcn`, `patchtst`, `timegan`
>
> **Not supported yet:** `chronos`, `lnn`, `ensemble`
>
> Before creating `can-training-orchestrator`, we must add these model types to the ML brick.

| Model Family | Current Support | Required Work |
|--------------|-----------------|---------------|
| LightGBM | ✅ Supported | None |
| LSTM | ✅ Supported | None |
| TCN | ✅ Supported | None |
| PatchTST | ✅ Supported | None |
| TimeGAN | ✅ Supported | None |
| Chronos-2 | ❌ Not supported | Add to ml_train_timeseries |
| LNN | ❌ Not supported | Add to ml_train_timeseries |
| Ensemble | ❌ Not supported | Add ml_compare_timeseries ensemble logic |

### 2.6 Event Types (Required)

> **Meta-architect note:** Every agent that publishes events MUST define event types and payload schemas.

| Event Type | Payload | Source Agent |
|------------|---------|--------------|
| `can.dataset.created` | `{dataset_uri, manifest_uri, quality, provenance}` | can-data-creator |
| `can.iteration.completed` | `{iteration, model_family, metrics, timestamp}` | can-training-orchestrator |
| `can.model.promoted` | `{model_id, rank, metrics, predecessor_id}` | can-evaluator |
| `can.retrain.decision` | `{direction: backward\|forward, reason, metrics}` | can-feedback-loop |
| `can.evaluation.completed` | `{suite_id, results, rankings}` | can-evaluator |

## 3. Data Creation Pipeline

### 3.1 CAN Data Creator Agent

**Skill file:** `skills/can-data-creator/SKILL.md`

**Purpose:** Transform raw CAN data into labeled training datasets.

**Workflow:**
1. **Ingest** raw CAN data (MF4, JSONL, parquet)
2. **Profile** signal boundaries, correlations, temporal patterns
3. **Synthesize** synthetic failures (8 modes) + real failures (Relativix labels)
4. **Validate** signal plausibility, temporal consistency, label quality
5. **Materialize** URI-addressable dataset with manifest

**Decision logic:**
- If data has real failure labels (Relativix tier-3) → use them as ground truth
- If data has no labels → generate synthetic failures
- If data has few VINs → augment with TimeGAN
- If data has many VINs → stratified sampling

### 3.2 CAN Training Orchestrator Agent

**Skill file:** `skills/can-training-orchestrator/SKILL.md`

**Purpose:** Train all model families in competition.

**Workflow:**
1. **Resolve** dataset URI from dataset brick
2. **Select** model families based on data characteristics
3. **Train** each family via ml_train_timeseries
4. **Evaluate** each with evals_evaluate_can_model
5. **Compare** models via ml_compare_timeseries
6. **Decision**: retrain backward or progress forward
7. **Version** best checkpoints

**Decision logic:**
- If dataset < 10K samples → LightGBM + LNN (data-efficient)
- If dataset 10K-100K samples → LightGBM + LSTM + TCN
- If dataset > 100K samples → All 7 families
- If AUROC < 0.80 → focus on data quality
- If AUROC 0.80-0.95 → focus on architecture tuning
- If AUROC > 0.95 → focus on edge cases

### 3.3 CAN Evaluation Agent

**Skill file:** `skills/can-evaluator/SKILL.md`

**Purpose:** Evaluate models with 6 evaluators.

**Workflow:**
1. **Run** 6 evaluators (AUROC, AUPRC, Brier, lead-time, false-alarm, episode-recall)
2. **Record** results via evals_record_run
3. **Compare** against previous runs via evals_get_run_regression
4. **Detect** distribution shift
5. **Trigger** retraining if needed

### 3.4 CAN Feedback Loop Agent

**Skill file:** `skills/can-feedback-loop/SKILL.md`

**Purpose:** Closed-loop improvement via evals.

**Workflow:**
1. **Check** model performance against thresholds
2. **Decide**: retrain backward (fix data) or progress forward (new architecture)
3. **Store** decision in memory for future reference
4. **Dispatch** events for monitoring
5. **Update** model rankings

## 4. Model Competition Framework

### 4.1 Model Families

| Family | Strengths | Best For | Training Tool |
|--------|-----------|----------|---------------|
| LightGBM | Fast, interpretable | Baseline | ml_train_timeseries(model_type="lightgbm") |
| LSTM | Temporal dependencies | Complex patterns | ml_train_timeseries(model_type="lstm") |
| TCN | Ultra-low latency | Real-time | ml_train_timeseries(model_type="tcn") |
| PatchTST | Long-range dependencies | Complex non-linear | ml_train_timeseries(model_type="patchtst") |
| Chronos-2 | Pretrained foundation | Few-shot learning | ml_train_timeseries(model_type="chronos") |
| LNN | Data-efficient | Small datasets | ml_train_timeseries(model_type="lnn") |
| Ensemble | Weighted combination | Production | ml_compare_timeseries(model_ids=[...]) |

### 4.2 Evaluation Framework

| Evaluator | What It Measures | Threshold | Tool |
|-----------|------------------|-----------|------|
| AUROC | Discrimination | ≥0.80 | evals_evaluate_computational(evaluator="can_auroc") |
| AUPRC | Precision-recall | ≥0.75 | evals_evaluate_computational(evaluator="can_auprc") |
| Brier | Calibration | ≤0.15 | evals_evaluate_computational(evaluator="can_brier") |
| Lead-time | Early detection | ≥5s | evals_evaluate_computational(evaluator="can_lead_time") |
| False-alarm | Specificity | ≤0.10 | evals_evaluate_computational(evaluator="can_false_alarm") |
| Episode-recall | Completeness | ≥0.80 | evals_evaluate_computational(evaluator="can_episode_recall") |

### 4.3 Closed-Loop Decision Tree

```
After each training iteration:
├── AUROC < 0.80
│   └── Focus on data quality improvements
│       ├── Check for label noise
│       ├── Add more failure examples
│       └── Improve signal preprocessing
├── AUROC 0.80-0.95
│   └── Focus on architecture tuning
│       ├── Hyperparameter optimization
│       ├── Feature engineering
│       └── Model ensemble
├── AUROC > 0.95
│   └── Focus on edge cases
│       ├── Adversarial robustness (TimeGAN)
│       ├── Rare failure modes
│       └── Cross-vehicle generalization
└── Always
    ├── Version checkpoint if improved
    └── Update model rankings
```

## 5. Implementation Plan

### Phase 1: Data Creation Agent (Priority 1)
1. Create `skills/can-data-creator/SKILL.md`
2. Wire to dataset brick MCP tools
3. Test with Relativix tier-3 labels
4. Validate output quality

### Phase 2: Training Orchestrator Agent (Priority 2)
1. Create `skills/can-training-orchestrator/SKILL.md`
2. Wire to ML brick MCP tools
3. Test with all 7 model families
4. Validate competition framework

### Phase 3: Evaluation Agent (Priority 3)
1. Create `skills/can-evaluator/SKILL.md`
2. Wire to evals brick MCP tools
3. Test with 6 evaluators
4. Validate evaluation pipeline

### Phase 4: Feedback Loop Agent (Priority 4)
1. Create `skills/can-feedback-loop/SKILL.md`
2. Wire to memory and events bricks
3. Test closed-loop iteration
4. Validate improvement over time

### Phase 5: Meta-Orchestrator Agent (Priority 5)
1. Create `skills/can-orchestrator/SKILL.md`
2. Wire all sub-agents together
3. Test end-to-end pipeline
4. Validate full system

## 6. Success Criteria

1. **Data Creation**: Can create labeled datasets from raw CAN data + Relativix labels
2. **Training**: Can train all 7 model families in competition
3. **Evaluation**: Can evaluate with 6 evaluators and compare models
4. **Feedback**: Can make retrain/progress decisions based on evals
5. **Improvement**: Models improve over iterations (AUROC increases)
6. **Explainability**: Agent decisions are logged and explainable
7. **Extensibility**: New model families can be added via skill updates

## 7. References

- [CAN Failure Prediction Spec](../../.github/spec/can-failure-prediction.md)
- [Rando Implementation Spec](../../.github/spec/Rando.md)
- [Relativix Fleet Intelligence](../../.agents/steering/relativix-fleet-intelligence.md)
- [Dataset Generation Skill](../../components/agent/src/factory/agent/skills/dataset-generation/SKILL.md)
- [CAN GAN Loop Skill](../../components/agent/src/factory/agent/skills/can-gan-loop/SKILL.md)
- [Dev Principles](../../.agents/steering/dev-principles.md)
