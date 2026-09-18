# ML Observatory Design

Bead: `python-factory-eplkz`
Architecture gates: initial `APPROVE_WITH_CHANGES`; second factory gate corrections incorporated below.

## Decision

Build one data-declared ML Observatory with five modes and neutral read projections. Do not build a CAN dashboard, duplicate MLflow, merge learning events into training counts, or fabricate provenance.

Release 1 assembles evidence already present. Promotion workflows, drift/calibration, advanced comparison, artifact viewers, controlled entity focus, and live-model enumeration remain extension seams until canonical contracts exist.

## Gate 0 — live source convergence

Before visual acceptance, restart Companion-X from this checkout and require the live ML schema to expose dashboard/training/Observatory tools plus exactly these ordered view IDs:

1. `ml-overview`
2. `ml-experiments`
3. `ml-models` (preserved existing ID)
4. `ml-learning-runs` (preserved existing ID)
5. `ml-lineage`

Stale-process results are not release evidence.

## Architecture

```text
runtime/
  observatory_sources.py     source envelopes + sanctioned suppliers
  observatory_projection.py separate populations, progress, attention, receipt artifacts
  observatory_lineage.py    verified nodes/edges + explicit missing links
mcp/
  observatory_tools.py      two thin deterministic tools
  views_observatory.py      Overview
  views_experiments.py      Experiments
  views_models.py           Models (existing ID retained)
  views_learning.py         Learning (existing ID retained)
  views_lineage.py          Lineage
         │
         ▼
ml_get_views (five pinned data declarations)
         │
         ▼
Generic UI: ID-based multi-view selector + Metric data_path + neutral A2UI Lineage
```

No base changes. No direct imports from dataset/evals/events/graph/storage. No self-MCP recursion.

## Source boundaries

Each source returns an envelope:

```jsonc
{"name":"training_receipts","health":"healthy","durability":"durable","freshness":"...","value":[],"error":null}
```

Failures return `value:null`, never `[]`.

- **Training receipts:** a new source adapter obtains `get_service("tool_invoker")` from `factory.mcp_utils.interface` and invokes `storage_doc_find(collection="ml_training_runs", query={}, limit=500)`. It unwraps and validates raw records while preserving failures. It does not call `ml_list_training_runs` from an ML tool and does not use the current reader's failure-as-empty result.
- **Learning:** an injected/within-brick supplier calls the existing learning projection directly and wraps exceptions as unavailable. It never reaches events internals.
- **Fine-tuning:** `observatory_tools.register` receives the existing server runtime supplier; source evaluation calls `runtime.get_finetuner().list_jobs()` inside an exception boundary.
- **Live models:** the current `TrackingRuntime` has point lookup but no public enumeration. Release 1 injects no live-model supplier and reports this source unavailable/count `null`; it never accesses `_inference_registry`. Child Bead `python-factory-vx2hp` owns a public enumeration seam.

## Population truth table

`population_state` is nullable because exclusive state cannot be proved if either primary source is unavailable.

| Training | Learning | State |
|---|---|---|
| available 0 | available 0 | `empty` |
| available >0 | available 0 | `training_only` |
| available 0 | available >0 | `learning_only` |
| available >0 | available >0 | `mixed` |
| unavailable | any | `null` |
| any | unavailable | `null` |

Known counts remain visible. Unknown counts are `null`. A training-unavailable/learning-active result says “Learning activity is available; training receipts are unavailable,” never “no receipts.” Aggregate `health` is computed separately.

## Summary contract

```jsonc
{
  "population_state": null,
  "health": "degraded",
  "message": "Learning activity is available; training receipts are unavailable.",
  "sources": [],
  "overview": {
    "training_runs": null,
    "experiments": null,
    "receipt_models": null,
    "fine_tuning_jobs": 0,
    "live_models": null,
    "regressions": null,
    "learning_runs": 15
  },
  "series": [{"label":"Run 1","value":0.91}],
  "attention": [],
  "models": []
}
```

Overview Chart consumes the already supported top-level `series` extraction with `xKey="label"` and `yKey="value"`. Release 1 does not modify Chart or add Chart `data_path`.

## Receipt-backed model projection

A receipt with `model_path` yields a projection, not a canonical registry identity:

```jsonc
{"row_id":"receipt-model:<run-id>","entity_id":null,"source":"training_receipt","source_run_id":"...","artifact_uri":"...","dataset_refs":[],"evaluation_refs":[],"provenance_state":"partial"}
```

## Verified lineage matrix

| Source fields required | Nodes | Verified edge | Evidence reference | Missing-link behavior |
|---|---|---|---|---|
| receipt `run_id` | `TrainingRun` | none | receipt/run ID | dataset and evaluation always missing unless canonical fields later exist |
| `run_id` + non-empty `model_path` | `TrainingRun`, `ModelArtifact` | `PRODUCED` | `<run_id>:model_path` | if absent, model/artifact link is missing |
| non-empty `tracker_experiment_id`/`tracker_run_id` | matching source-native tracker nodes | only deterministic parent relation represented by those explicit fields | field-qualified receipt ref | names/model types never create identity |
| learning stitched run ID + explicit graph event ID; `graph_id` for graph node | workflow/run, graph event, optional Graph | run `HAS_EVENT`; graph relation only with graph event evidence | source event ID | no graph node from `graph_id` alone |
| explicit reward event ID | workflow/run, `RewardEvent` | `HAS_EVENT` | reward event ID | no RewardEvent→Wallet inference |
| explicit wallet event ID and wallet/transaction field | workflow/run, wallet event/artifact | `HAS_EVENT` | wallet event ID | no temporal joins |
| explicit memory event ID and `memory_id`/`summary_type` | workflow/run, memory event/artifact | `HAS_EVENT` | memory event ID | no next-run inference |
| explicit convergence event ID and `metric_id`/`metrics_recorded`/`converged` | workflow/run, metric/convergence event | `HAS_EVENT` | convergence event ID | no evaluation identity unless explicit |

Every node uses renderer-local `node_id`, nullable canonical `entity_id`, `source`, `source_ref`, `evidence`, and `evidence_refs`. Every edge is `verified`. Learning records without explicit dataset/evaluation/model references report those missing links. Target app, profile, workflow type, and domain/vulnerability class remain metadata, not identities.

## Information architecture

- **Overview (`ml-overview`):** six path-bound Metric cards, honest state banner, top-level-series progress Chart, attention list, recent learning list.
- **Experiments (`ml-experiments`):** grouped longitudinal rows with score, delta, sparkline, regression, and run details.
- **Models (`ml-models`):** receipt-backed artifacts plus fine-tuning jobs; live-registry source shown unavailable until its public supplier exists.
- **Learning (`ml-learning-runs`):** existing stage-filtered refresh view, preserving Story/Timeline/Artifacts.
- **Lineage (`ml-lineage`):** neutral supplied-data graph, verified edges only, explicit missing links, disconnected components, 100-node cap.

## Generic UI changes

### `BrickViewRenderer`

`viewIndex` is initial fallback only. Active state is a view ID stored per brick in generic workbench state; metadata supplies labels/descriptions. A selector renders only for multiple views. One-view content keeps current DOM/content behavior. CanvasContextBridge publishes selected subview state.

### Metric

`MetricCardRenderer` accepts nested `data_path` and resolves it before existing extraction. The Python A2UI catalog declares the property.

### Lineage

Add neutral `Lineage` to the Python catalog, native component mapping, shared component map, renderer, and parity tests. It accepts static data or `data_tool`/`data_path`, clamps to 100 nodes, lays out deterministically left-to-right, and never hardcodes graph tools.

## Agent control split

Release 1 adds `fe_select_brick_view(brick, view_id)` using the existing CopilotKit `useFrontendTool` pattern. The handler validates against known brick/view metadata and only mutates workbench state. Shared-renderer never imports CopilotKit.

`fe_focus_view_entity` is deferred to child Bead `python-factory-7zfe9` because the current allowlist lacks a controlled-focus renderer seam. No DOM querying or bespoke dispatcher is permitted.

## Collision-safe allowlist

Allowed existing files: ML `server.py`, `mcp/__init__.py`, `mcp/views*.py`, capabilities metadata; `frontends/next-dashboard/components/canvas/brick-view-renderer.tsx`; generic workbench/context/frontend-tool files for view selection only; shared-renderer metric/component registry/index files; UI A2UI catalog/native mapping files; focused new tests and this spec. New files may be added under ML observatory runtime/MCP/views and shared-renderer Lineage modules/tests.

Forbidden without another Bead: active evals/events/graph/storage files; ML model adapters (`chronos*`, `lnn*`, `patchtst*`, `peft*`, transformer/T5); ML `runtime.py` and fine-tuning factory; `pyproject.toml`; unrelated specs; direct upstream brick internals. Canonical docs outside this allowlist are deferred to `python-factory-u780l`.

## SRP and validation

Separate source envelopes, aggregation, lineage, MCP registration, and each view builder. All new Python files stay below 200 LOC. Validate with Hypothesis/fixtures, exact schema/view tests, selector/single-view/Metric/Lineage tests, targeted pytest/Vitest/type/build checks, restarted live MCP probes, and guardian with only pre-existing branch/LOC/OpenArcade failures dispositioned.
