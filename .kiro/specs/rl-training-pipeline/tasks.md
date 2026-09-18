# RL Training Pipeline — Tasks

## Task 1: Transcript Extractor
- [ ] Create `components/games/runtime/transcript_extractor.py`
- [ ] `extract_transcripts()` — query graph for finished GameSession nodes with HAS_MOVE neighbors
- [ ] `to_training_jsonl()` — convert to `{"input", "output", "reward"}` JSONL format
- [ ] `shape_rewards()` — gamma-discounted terminal reward propagation
- [ ] Filter by game_type, min_eval_score, since timestamp
- [ ] Hypothesis tests for reward shaping math

## Task 2: Training Pipeline Orchestrator
- [ ] Create `components/games/runtime/training_pipeline.py`
- [ ] `run_training_cycle()` — extract → store dataset → fine-tune → record convergence
- [ ] All cross-brick calls via tool_invoker (graph, storage, ml, memory)
- [ ] Graceful skip when bricks unavailable

## Task 3: MCP Tools
- [ ] Add `games_extract_transcripts` to `mcp/operational.py`
- [ ] Add `games_run_training_cycle` to `mcp/operational.py`
- [ ] Update `games_get_capabilities` to advertise training features

## Task 4: Graph Lineage Nodes
- [ ] Add `TrainingBatch` entity type to graph on each training run
- [ ] `TRAINED_ON` edges from TrainingBatch → GameSession (which games fed this batch)
- [ ] `PRODUCED` edge from TrainingBatch → ModelCheckpoint
- [ ] `SCORED_BY` edge from GameSession → EvalResult (link eval scores to games)

## Task 5: Memory Integration
- [ ] After each training batch, `memory_store` a training insight summary
- [ ] Include: game_type, batch_id, win_rate_before, win_rate_after, key_patterns
- [ ] Agents can `memory_retrieve("sql injection training insights")` during gameplay

## Task 6: KB Strategy Guides
- [ ] Ingest strategy guides for each security game type via `kb_ingest`
- [ ] One guide per game type: detection playbook, common patterns, scoring tips
- [ ] Agents retrieve during gameplay via `kb_search`

## Task 7: Storage Integration
- [ ] Store JSONL datasets via `storage_save` (blob adapter)
- [ ] Store model checkpoints via `storage_save`
- [ ] Version datasets with batch_id in metadata

## Task 8: End-to-End Recipe
- [ ] Create `.agents/recipes/rl-training-loop.md`
- [ ] Full cycle: create games → play → extract → train → evaluate → converge
- [ ] Verify data lands in correct stores (graph, memory, kb, storage)
- [ ] Verify convergence detection stops training appropriately

## Task 9: Convergence Wiring
- [ ] After each training batch, play N eval games with updated model
- [ ] Feed average eval score to ConvergenceState
- [ ] If converged: stop pipeline, store final model, log completion memory
- [ ] If not converged: loop with updated model

## Task 10: Hypothesis Tests
- [ ] Property tests for transcript_extractor (reward shaping, JSONL format)
- [ ] Property tests for training_pipeline (mock all brick calls)
- [ ] Stateful machine: random game→extract→train sequences maintain invariants
