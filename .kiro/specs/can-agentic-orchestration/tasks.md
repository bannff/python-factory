# CAN Agentic Orchestration — Tasks

**Date:** 2026-07-24
**Status:** APPROVED — ready for implementation
**Epic:** python-factory-dth

## Pre-Implementation: Reconcile with Existing Agents

> **Meta-architect requirement:** Before implementing new agents, reconcile with existing CAN agents.

### Task 0.1: Audit existing agents
- [x] Review `defaults_can_agents.py` for existing CAN agent configs
- [x] Review `defaults_can_pipeline.py` for existing graph structure
- [x] Document overlap between new design and existing agents
- [x] Decide Option B: keep training + evaluation fused in can-trainer

### Task 0.2: Fix tool name errors
- [x] Update spec: `events_dispatch` → `events_publish`
- [x] Update spec: note `can_profile/synthesize/augment` are recipe stages
- [x] Update SKILL.md files to use correct tool names

### Task 0.3: Define event type schemas
- [x] Define `can.dataset.created` payload schema (Pydantic)
- [x] Define `can.iteration.completed` payload schema (Pydantic)
- [x] Define `can.model.promoted` payload schema (Pydantic)
- [x] Define `can.retrain.decision` payload schema (Pydantic)

## Phase 1: Data Creation Agent

### Task 1.1: Create can-data-creator skill
- [x] Create `components/agent/src/factory/agent/skills/can-data-creator/SKILL.md`
- [ ] Update skill to use correct tool names (recipe-driven)
- [ ] Wire to dataset brick MCP tools
- [ ] Test with recipe-based data creation

### Task 1.2: Integrate Relativix labels
- [ ] Create adapter to read tier-3 parquet files
- [ ] Map tier-3 schema to our canonical schema
- [ ] Join tier-2 signals with tier-3 labels
- [ ] Validate label quality

### Task 1.3: Wire as AgentConfig
- [ ] Add `can-data-creator` to `defaults_can_agents.py`
- [ ] Add as optional node in `defaults_can_pipeline.py`
- [ ] Test integration with existing pipeline

### Task 1.4: Validate data creation pipeline
- [ ] Test end-to-end: raw data → labeled dataset
- [ ] Validate signal plausibility
- [ ] Validate temporal consistency
- [ ] Validate label quality

## Phase 2: Training Orchestrator Agent

### Task 2.1: Create can-training-orchestrator skill
- [ ] Create `components/agent/src/factory/agent/skills/can-training-orchestrator/SKILL.md`
- [ ] Define agent role, tools, workflow, decision logic
- [ ] Wire to ML brick MCP tools
- [ ] Test with single model family

### Task 2.2: Implement model competition
- [ ] Train all 7 model families in parallel
- [ ] Compare models via ml_compare_timeseries
- [ ] Version best checkpoints
- [ ] Validate competition framework

### Task 2.3: Implement decision logic
- [ ] Add data size-based model selection
- [ ] Add AUROC-based retrain/progress decisions
- [ ] Add checkpoint versioning
- [ ] Validate decision logic

## Phase 3: Evaluation Agent

### Task 3.1: Create can-evaluator skill
- [ ] Create `components/agent/src/factory/agent/skills/can-evaluator/SKILL.md`
- [ ] Define agent role, tools, workflow
- [ ] Wire to evals brick MCP tools
- [ ] Test with single evaluator

### Task 3.2: Implement 6-evaluator framework
- [ ] Run all 6 evaluators (AUROC, AUPRC, Brier, lead-time, false-alarm, episode-recall)
- [ ] Record results via evals_record_run
- [ ] Compare against previous runs
- [ ] Validate evaluation pipeline

## Phase 4: Feedback Loop Agent

### Task 4.1: Create can-feedback-loop skill
- [ ] Create `components/agent/src/factory/agent/skills/can-feedback-loop/SKILL.md`
- [ ] Define agent role, tools, workflow
- [ ] Wire to memory and events bricks
- [ ] Test single feedback iteration

### Task 4.2: Implement closed-loop
- [ ] Check model performance against thresholds
- [ ] Make retrain/progress decisions
- [ ] Store decisions in memory
- [ ] Dispatch events for monitoring
- [ ] Validate improvement over iterations

## Phase 5: Meta-Orchestrator Agent

### Task 5.1: Create can-orchestrator skill
- [ ] Create `components/agent/src/factory/agent/skills/can-orchestrator/SKILL.md`
- [ ] Define agent role, tools, workflow
- [ ] Wire all sub-agents together
- [ ] Test end-to-end pipeline

### Task 5.2: Validate full system
- [ ] Run complete pipeline: data creation → training → evaluation → feedback
- [ ] Validate model improvement over iterations
- [ ] Validate explainability of decisions
- [ ] Validate extensibility (add new model family)

## Phase 6: Documentation

### Task 6.1: Update specs
- [ ] Update `can-failure-prediction.md` with agentic architecture
- [ ] Update `Rando.md` with new status
- [ ] Update steering docs with new insights

### Task 6.2: Create documentation
- [ ] Create README for agentic orchestration
- [ ] Document skill file formats
- [ ] Document decision logic
- [ ] Document success criteria

## Bead Tracking

| Bead | Phase | Task | Status |
|------|-------|------|--------|
| python-factory-can-agentic-1 | 1 | 1.1 | Pending |
| python-factory-can-agentic-2 | 1 | 1.2 | Pending |
| python-factory-can-agentic-3 | 1 | 1.3 | Pending |
| python-factory-can-agentic-4 | 2 | 2.1 | Pending |
| python-factory-can-agentic-5 | 2 | 2.2 | Pending |
| python-factory-can-agentic-6 | 2 | 2.3 | Pending |
| python-factory-can-agentic-7 | 3 | 3.1 | Pending |
| python-factory-can-agentic-8 | 3 | 3.2 | Pending |
| python-factory-can-agentic-9 | 4 | 4.1 | Pending |
| python-factory-can-agentic-10 | 4 | 4.2 | Pending |
| python-factory-can-agentic-11 | 5 | 5.1 | Pending |
| python-factory-can-agentic-12 | 5 | 5.2 | Pending |
| python-factory-can-agentic-13 | 6 | 6.1 | Pending |
| python-factory-can-agentic-14 | 6 | 6.2 | Pending |
