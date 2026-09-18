---
name: compx-platform
description: Companion-X MCP platform — 30+ bricks with tools, resources, and prompts for security engineering.
---
# Companion-X MCP Platform

You have access to 30+ MCP bricks. Each brick has tools, resources, and prompts.

## Discovery

- `list_bricks()` — see all available bricks
- `get_brick_tools(brick_name)` — see a brick's tools with schemas
- `get_brick_resources(brick_name)` — schemas and docs
- `render_brick_prompt(brick_name, prompt_name)` — guided workflows

## Key Bricks for Security Work

### Veritas (app security graph, 6B+ nodes)
- `get_app_topology(app_name=..., exact=true)` — full app topology
- `get_app_security_profile(app_name=..., exact=true)` — security posture
- `query_veritas(cypher_query='MATCH ...')` — raw Cypher queries
- `search_resources(resource_type=..., limit=20)` — find resources
- `get_data_flows(resource_type=..., resource_identifier=...)` — data flows

### Memory (agent observations, strategies)
- `memory_store(content='...', user_id='kiro-agent', category='fact', memory_type='long_term')` — store finding
- `memory_retrieve(user_id='kiro-agent', query='...', limit=5)` — search memories
- `memory_list(user_id='kiro-agent', limit=20)` — list all memories
- Always use `user_id='kiro-agent'` for all memory operations

### Graph (knowledge graph — backend-agnostic)
- `graph_add_entity(entity_id=..., entity_type=..., properties={...})` — add node
- `graph_add_relationship(source_id=..., target_id=..., relationship_type=...)` — add edge
- `graph_find_entities(entity_type=..., properties={"run_id": "..."})` — typed lookup by type / property dict
- `graph_get_findings_for_run(run_id=...)` — Finding rows joined with CWE/OCSF taxonomy for a run
- `graph_count_entities_by_run(run_id=..., labels=[...])` — per-label counts scoped to a run
- `graph_get_workflow_summary(run_id=...)` — composite run summary (counts + verdict histogram + target_app)
- `graph_get_recent_findings(severity=..., app=..., run_id=..., limit=...)` — recent findings filter
- `graph_get_target_app(target_app=..., run_id=...)` — TargetApp singleton lookup
- `graph_get_tool_invocations_for_run(run_id=..., limit=...)` — ToolInvocation timeline
- `graph_list_recent_tool_invocations(limit=...)` — most-recent N ToolInvocation rows globally (drives Timeline tab)
- Use `graph_find_entities` for portable filtered entity reads and the run-scoped typed tools above for evidence; raw backend queries are not part of Graph's public surface.

### KB (knowledge base for proven findings)
- `kb_ingest(content='...', metadata={...})` — store proven finding for RAG
- `kb_search(query='...')` — search knowledge base

### Builder (code.amazon.com access)
- `builder_list_package_files(package_name='...')` — list repo files
- `builder_read_package_file(package_name='...', file_path='...')` — read file
- `builder_search_code(query='...', search_type='code')` — search code

### Security (threat modeling, analysis)
- `security_threat_model(target='...')` — STRIDE analysis
- `security_analyze(target='...')` — security analysis

### Sandbox (LocalStack AWS emulator)
- `sandbox_list_environments()` — find sandbox env_id
- `sandbox_deploy_cfn(env_id=..., stack_name=..., template_body=...)` — deploy
- `sandbox_execute(env_id=..., command='...')` — run AWS CLI

### Evals (LLMAJ evaluators)
- `evals_evaluate(evaluator='goal_success', input='...', output='...')` — score
- `evals_create_suite(name='...')` — create eval suite

### Games (gamification)
- `games_create(game_type='security_assessment', config={...})` — create game
- `games_security_move(game_id=..., action='submit_finding', params={...})` — record move

### Blockchain (rewards)
- `blockchain_transfer(from_wallet='system', to_wallet='...', amount=..., memo='...')` — issue reward

### Metrics (time-series tracking)
- `metrics_record(metric_id='...', value=...)` — record metric

### SIPP (security intelligence)
- `sipp_query(query='...')` — query security intelligence

### Dataset (async generation, validation, materialization)
- `dataset_submit_generation(request={...})` — submit recipe, returns `{job_id}`
- `dataset_get_job(job_id='...')` — poll job status
- `dataset_cancel_job(job_id='...')` — cancel a running job
- `dataset_get_artifact(job_id='...')` — get immutable artifact reference
- `dataset_resolve_artifact(dataset_uri='...')` — resolve URI to manifest

### Machine Learning (experiment tracking, fine-tuning, time-series)
- `ml_list_finetuning_methods()` — list supported techniques (LoRA, AdaLoRA, IA3, etc.)
- `ml_list_finetuning_jobs()` — list all fine-tuning jobs
- `ml_get_finetuning_job(job_id='...')` — get full job details
- `ml_get_job_status(job_id='...')` — get status and metrics
- `ml_list_checkpoints(job_id='...')` — list saved checkpoints
- `ml_list_stage_artifacts(job_id='...')` — list stage artifact checkpoints
- `ml_train_timeseries(model_type='tcn', X_uri='...', y_uri='...', ...)` — train time-series classifier (`lightgbm` | `lstm` | `tcn` | `patchtst`)
- `ml_predict_timeseries(model_id='...', X_uri='...')` — score a windowed dataset
- `ml_compare_timeseries(model_ids=[...], metric='auroc')` — rank models on a single metric
- `ml_list_timeseries_models()` — list trained time-series models

### Evals — CAN computational metrics
- `evals_evaluate_can_model(y_true=..., y_pred=..., y_score=None)` — bundled accuracy/precision/recall/f1 (plus auroc/auprc/brier when `y_score` given and both classes present). Auto-called by `train_top_can_ids` (machine_learning brick) after each per-CAN-ID LightGBM fit; results merge into `job.metrics`.
- `evals_evaluate_computational(evaluator_name='can_auroc', y_true=..., y_pred=..., scores=...)` — six CAN-specific deterministic evaluators:
  - `can_auroc` — area under ROC (headline discrimination)
  - `can_auprc` — area under precision-recall
  - `can_brier` — Brier score (calibration)
  - `can_lead_time` — mean seconds of advance warning before failure
  - `can_false_alarm` — false alarms per hour of normal driving
  - `can_episode_recall` — fraction of fault episodes detected

### CAN pipeline agents (Epic 6 — Agentic Dataset Skills)
Registered standalone agent personas that compose the Relativix CAN
failure prediction pipeline. The agent graph reflects a 5-stage data
pipeline (ingest → profile → synthesize → window → augment) plus the
post-pipeline ML train step:
- `can-ingest` — MF4 parser + DBC matcher (skills: can-analyst, compx-platform)
- `can-profiler` — signal boundary / temporal correlation (skills: can-analyst, compx-platform)
- `can-synthesizer` — synthetic CAN + failure injection; also orchestrates
  the `can-window` and `can-augment` recipe stages via the recipe
  materializer (skills: can-recipe-author, compx-platform)
- `can-trainer` — time-series training + 6-metric eval (skills: can-evaluator, compx-platform)

The `can-window` and `can-augment` data stages are recipe-driven
transformations (no conversational agent persona) executed by
`factory.dataset.runtime.adapters.can_window` and
`factory.dataset.runtime.adapters.can_augment` as part of a single
`recipe://local/can-pipeline-aug@1` submission. The
`can-pipeline` graph has dedicated `window` and `augment` nodes that
share the `can-synthesizer` agent persona for runtime dispatch.

The graph config `can-pipeline` is registered via
`factory.agent.registry.defaults_can_pipeline` and can be launched
through the standard graph execution path
(`spawn_registered_graph(graph_id='can-pipeline', ...)`).

For dataset workflows, use the `dataset-generation` skill for detailed guidance.
For CAN-specific workflow guidance, use the `can-analyst`,
`can-recipe-author`, and `can-evaluator` skills.

## Storage Rules

- **Memory**: agent observations, strategies, learnings (ephemeral)
- **Graph**: structural app model — entities + relationships (persistent)
- **KB**: proven/confirmed findings for future RAG retrieval (permanent)
- Use all three appropriately based on what you're storing
