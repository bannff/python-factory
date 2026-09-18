# CAN Agentic Orchestration — Requirements

**Date:** 2026-07-24
**Status:** Draft
**Epic:** python-factory-dth

## 1. Functional Requirements

### FR-1: Data Creation
The system SHALL create labeled training datasets from raw CAN data.

**Acceptance Criteria:**
- Can ingest raw CAN data (MF4, JSONL, parquet)
- Can decode signals using DBC files
- Can generate synthetic failures (8 modes)
- Can integrate real failure labels (Relativix tier-3)
- Can validate signal plausibility and temporal consistency
- Can materialize URI-addressable dataset with manifest

### FR-2: Model Training
The system SHALL train multiple model families in competition.

**Acceptance Criteria:**
- Can train LightGBM, LSTM, TCN, PatchTST, TimeGAN (currently supported)
- Can train Chronos-2, LNN, Ensemble (after ML brick extension)
- Can train families in parallel
- Can compare models via evaluation metrics
- Can version best checkpoints
- Can adapt model selection based on data characteristics

> **Note:** Chronos-2, LNN, and Ensemble require ML brick extension before implementation.

### FR-3: Model Evaluation
The system SHALL evaluate models with 6 evaluators.

**Acceptance Criteria:**
- Can run AUROC, AUPRC, Brier, lead-time, false-alarm, episode-recall
- Can record results via evals_record_run
- Can compare against previous runs
- Can detect distribution shift
- Can trigger retraining if needed

### FR-4: Feedback Loop
The system SHALL implement closed-loop improvement.

**Acceptance Criteria:**
- Can check model performance against thresholds
- Can make retrain/progress decisions
- Can store decisions in memory
- Can dispatch events for monitoring
- Can improve model performance over iterations

### FR-5: Agent Orchestration
The system SHALL use agents with skills for orchestration.

**Acceptance Criteria:**
- Can create skill files for each agent role
- Can wire agents to MCP tools
- Can compose agents for complex workflows
- Can log agent decisions for explainability
- Can adapt workflows based on context

## 2. Non-Functional Requirements

### NFR-1: Extensibility
The system SHALL be extensible without code changes.

**Acceptance Criteria:**
- New model families can be added via skill updates
- New evaluators can be added via evaluator catalog
- New data sources can be added via dataset recipes
- New decision logic can be added via skill files

### NFR-2: Explainability
The system SHALL provide explainable decisions.

**Acceptance Criteria:
- Agent decisions are logged in natural language
- Model rankings are transparent
- Evaluation metrics are visible
- Feedback loop decisions are documented

### NFR-3: Performance
The system SHALL meet performance requirements.

**Acceptance Criteria:**
- Data creation completes in < 1 hour for 100K samples
- Model training completes in < 30 minutes per family
- Evaluation completes in < 10 minutes per model
- Feedback loop completes in < 5 minutes per iteration

### NFR-4: Reliability
The system SHALL be reliable and fault-tolerant.

**Acceptance Criteria:**
- Can recover from failed training runs
- Can retry failed evaluations
- Can fallback to simpler models if complex models fail
- Can preserve checkpoints across failures

## 3. Data Requirements

### DR-1: Input Data
The system SHALL accept the following input data:
- Raw CAN data (MF4, JSONL, parquet)
- DBC files (universal + vehicle-specific)
- Relativix tier-3 labels (real failures)
- Configuration parameters

### DR-2: Output Data
The system SHALL produce the following output data:
- Labeled training datasets (URI-addressable)
- Trained models (URI-addressable)
- Evaluation results (recorded in evals brick)
- Decision logs (stored in memory brick)
- Event logs (dispatched via events brick)

## 4. Integration Requirements

### IR-1: Dataset Brick
The system SHALL integrate with the dataset brick for data creation.

**Acceptance Criteria:**
- Can call dataset_submit_generation
- Can call dataset_get_job
- Can call dataset_get_artifact
- Can call dataset_resolve_artifact

### IR-2: ML Brick
The system SHALL integrate with the ML brick for model training.

**Acceptance Criteria:**
- Can call ml_train_timeseries
- Can call ml_continue_timeseries
- Can call ml_sample_timeseries
- Can call ml_compare_timeseries

### IR-3: Evals Brick
The system SHALL integrate with the evals brick for evaluation.

**Acceptance Criteria:**
- Can call evals_evaluate_can_model
- Can call evals_evaluate_computational
- Can call evals_record_run
- Can call evals_get_run_regression

### IR-4: Memory Brick
The system SHALL integrate with the memory brick for feedback.

**Acceptance Criteria:**
- Can call memory_store
- Can call memory_retrieve
- Can tag memories with domain_class="can_failure"

### IR-5: Events Brick
The system SHALL integrate with the events brick for monitoring.

**Acceptance Criteria:**
- Can dispatch events via events_dispatch
- Can record lifecycle outcomes
- Can trigger retraining based on events

## 5. Compliance Requirements

### CR-1: Factory Tenets
The system SHALL comply with factory tenets.

**Acceptance Criteria:**
- MCP-First: All brick interactions via MCP tools
- <200 LOC per file
- No cross-imports (only factory.<brick>.interface)
- Views as data (dicts in mcp/views.py)
- SDK-First when wrapping third-party SDKs
- Adapter pattern via runtime/ports.py

### CR-2: Dev Principles
The system SHALL comply with dev principles.

**Acceptance Criteria:**
- Clean Architecture separation
- Gateway Architecture for bases
- Single Responsibility
- Property-Based Testing with Hypothesis

## 6. Success Criteria

### SC-1: Data Creation
- Can create labeled datasets from raw CAN data + Relativix labels
- Dataset quality meets validation thresholds
- Dataset is URI-addressable and reproducible

### SC-2: Model Training
- Can train all 7 model families in competition
- Models are versioned and comparable
- Training adapts to data characteristics

### SC-3: Model Evaluation
- Can evaluate with 6 evaluators
- Results are recorded and comparable
- Distribution shift is detected

### SC-4: Feedback Loop
- Can make retrain/progress decisions
- Models improve over iterations (AUROC increases)
- Decisions are logged and explainable

### SC-5: Agent Orchestration
- Agents are skill-driven, not hardcoded
- Workflows are composable and flexible
- Decisions are transparent and auditable
