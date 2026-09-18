# ML Observatory Requirements

Bead: `python-factory-eplkz`

## Vision

The Companion-X ML tab is an agent-drivable observatory for the improvement loop:

`DatasetVersion → Experiment → TrainingRun → ModelArtifact → EvalRun → RewardEvent → LearningMemory → NextRun`

It uses the visual language of Metrics, Evals, Timeline, and Graph while remaining domain-agnostic. CAN fields are data in `domain_metadata`, never branches in runtime or React code.

## Definitions

- **Training run**: a real model-training receipt persisted in `ml_training_runs`.
- **Learning run**: an event-backed recursive-learning projection; never model training.
- **Receipt-backed model artifact**: a training receipt with an artifact URI. A renderer key is not a canonical model ID.
- **Population state**: `empty|learning_only|training_only|mixed|null`; `null` means one or both primary population sources are unavailable, so exclusivity cannot be proved.
- **Source health**: `healthy|degraded|error`, independent from population state.
- **Unknown count**: `null`, used when a source is unavailable; never coerced to zero.

## R0 — Runtime/source convergence gate

1. Before UI acceptance, the running Companion-X process must be restarted from the checkout.
2. Live schemas must expose `ml_get_dashboard_summary`, training-run tools, `ml_get_observatory_summary`, `ml_get_observatory_lineage`, and exactly these ordered view IDs: `ml-overview`, `ml-experiments`, `ml-models`, `ml-learning-runs`, `ml-lineage`.
3. Frontend behavior must not be debugged against a stale MCP process.

## R1 — Useful first paint

1. The tab presents a persistent Observatory header and selectable modes: Overview, Experiments, Models, Learning, and Lineage.
2. The first paint shows stable loading skeletons, not a lone spinner.
3. Overview exposes separate counts for training runs, experiments, receipt-backed models, fine-tuning jobs, regressions, and learning runs.
4. When all healthy sources are empty, the page explains dataset → train → evaluate and exposes agent-driven next actions without inventing data.
5. A degraded source retains available data and shows freshness/durability status.

## R2 — Honest mixed-state and availability handling

1. Population state follows this complete truth table, where `T` is training receipts and `L` is learning runs:

| T source/count | L source/count | `population_state` | Required claim |
|---|---|---|---|
| available / 0 | available / 0 | `empty` | No persisted training or learning runs. |
| available / >0 | available / 0 | `training_only` | Training receipts exist; no learning runs. |
| available / 0 | available / >0 | `learning_only` | Learning loop active; no persisted training receipts yet. |
| available / >0 | available / >0 | `mixed` | Training and learning activity exist. |
| unavailable / `null` | available / 0 or >0 | `null` | Report known learning count; training availability is unknown. Never claim “no receipts.” |
| available / 0 or >0 | unavailable / `null` | `null` | Report known training count; learning availability is unknown. Never claim an exclusive/empty population. |
| unavailable / `null` | unavailable / `null` | `null` | Both populations are unavailable; do not claim emptiness. |

2. Learning and training populations are visible separately and never combined into one ambiguous runs count.
3. A counter is zero only when its canonical source is available and empty; an unavailable source reports `null/unknown`.
4. `population_state` is independent from aggregate `health`; partial known data remains visible during degradation.

## R3 — Progress over time

1. Experiments show latest primary score, best/average score, run count, model type, delta, sparkline, and regression state.
2. Training runs expose available AUROC/F1/AUPRC/Brier, configuration, artifact path, timestamp, and predecessor comparison.
3. Overview presents recent metric movement and an attention queue for regressions, failures, and incomplete provenance.
4. Overview progress uses the existing Chart-supported top-level `series` shape (`[{label,value,...}]`) or the existing dashboard series; Release 1 does not change Chart extraction.
5. Empty trends explain which action produces data.

## R4 — Models and fine-tuning

1. Models mode lists receipt-backed artifacts and canonical live-registry entries as distinct sources when a public registry supplier is available.
2. Until public live-model enumeration exists, its source is unavailable with count `null`; callers never inspect `TrackingRuntime._inference_registry`.
3. Fine-tuning jobs remain distinct with status, method, base model, objective, loss, checkpoints, and errors.
4. A model row identifies its source run and only references datasets/evaluations actually present in canonical records.
5. Missing provenance is explicit; derived UI keys are not presented as canonical model IDs.

## R5 — Learning-loop observability

1. Learning mode shows stage, score, reward/penalty, memory status, convergence, last event, update time, and artifacts.
2. A run expands to Story, Event Timeline, and Artifacts.
3. Refresh retains prior data.
4. Rewarded, penalized, stored, and converged states remain distinct.
5. Event IDs are labeled as events unless a canonical reward/metric entity ID exists.

## R6 — Evidence-backed lineage

1. Each node has renderer-local `node_id`, nullable source-native `entity_id`, `entity_type`, `source`, `source_ref`, `evidence`, and `evidence_refs`.
2. Release 1 emits only these field-backed edges:
   - receipt `run_id` creates `TrainingRun`; non-empty `model_path` creates `ModelArtifact`; edge `TrainingRun -PRODUCED-> ModelArtifact` is evidenced by `run_id:model_path`;
   - non-empty `tracker_experiment_id`/`tracker_run_id` may create their matching source-native nodes/links; names and model types alone never establish identity;
   - a learning workflow/run node may link to explicit graph launch/completion/failure, reward, wallet, memory, metric, or convergence event/artifact nodes only when their source event IDs and corresponding fields are present;
   - a Graph node requires both `graph_id` and graph-event evidence.
3. No edge is inferred from timestamp order. In particular, RewardEvent→Wallet and next-run edges are not emitted without explicit source references.
4. Missing receipt dataset and evaluation links are always recorded; missing model/artifact linkage is recorded when `model_path` is absent; missing canonical registry-model linkage is recorded until a canonical ID exists.
5. Learning records without explicit dataset/evaluation/model references emit those kinds in `missing_links`; they are never synthesized from target/profile/domain metadata.
6. Domain metadata copies source fields and never synthesizes CAN/security provenance.
7. The neutral Lineage type is registered in the Python A2UI catalog and frontend component map with parity tests.

## R7 — Agent control

1. Existing `fe_navigate_canvas` opens ML.
2. Release 1 adds generic `fe_select_brick_view(brick, view_id)` using existing CopilotKit `useFrontendTool`; it validates inputs and only mutates generic per-brick selected-view workbench state.
3. Selected subview is published by CanvasContextBridge and consumed by `BrickViewRenderer`; shared-renderer does not import CopilotKit.
4. Controlled entity focus is deferred to child Bead `python-factory-7zfe9`; Release 1 must not query the DOM, add a bespoke dispatcher, or claim `fe_focus_view_entity` exists.
5. Training/stopping/export/cleanup remain MCP operations with confirmation gates where required.

## R8 — Architecture and collision safety

1. Runtime aggregation lives in separate sub-200-LOC modules for source envelopes, population aggregation, and lineage.
2. MCP registration is a thin sub-200-LOC module; view builders are split by mode.
3. Training receipts use raw `storage_doc_find` through `factory.mcp_utils` so source failure is distinguishable from empty; Observatory tools never self-invoke ML MCP tools.
4. Learning uses an exception-wrapped within-brick projection supplier. Fine-tuning uses an injected supplier from `TrackingRuntime.get_finetuner().list_jobs`; live-model enumeration remains unavailable until child Bead `python-factory-vx2hp` provides a public supplier.
5. No dataset/evals/events/graph/storage internals are imported.
6. Views remain data from `ml_get_views`; frontend changes are reusable selector/metric/lineage capabilities.
7. Selector state is retained by view ID; `viewIndex` is only the initial fallback; single-view bricks retain current DOM/content behavior.
8. Existing tools and fields remain backward compatible.
9. Do not modify active evals/events/graph/storage files or branch-owned ML model adapters/runtime/factory files. Missing upstream contracts become separate Beads work.

## R9 — Quality and documentation boundary

1. Hypothesis tests cover population count separation, state transitions including unavailable truth-table rows, ordering, model deduplication, malformed records, and evidence-only lineage.
2. MCP tests cover registration/schema and exactly five pinned views.
3. Frontend tests cover selector retention/fallback, single-view compatibility, nested Metric `data_path`, lineage evidence/disconnected/100-node bounds, and loading/error/stale states.
4. Targeted pytest/Vitest and frontend type/build checks pass; live Companion-X probes pass after restart.
5. Guardian shows zero new failures; pre-existing branch-name/LOC/OpenArcade failures are explicitly dispositioned.
6. This spec records shipped behavior. Canonical docs outside the allowlist are deferred to child Bead `python-factory-u780l`.
