# ML Observatory Implementation Tasks

Bead: `python-factory-eplkz`

## 0. Hard gate: runtime/source convergence

- Restart the API/MCP process from the checkout before visual acceptance.
- Probe live schemas for dashboard/training/Observatory tools and exactly `ml-overview`, `ml-experiments`, `ml-models`, `ml-learning-runs`, `ml-lineage` in that order.
- Do not debug UI against the stale process found during investigation.

## 1. Neutral source envelopes

- Add source-envelope helpers with independent `health`, `durability`, `freshness`, nullable `value`, and error.
- Read raw training receipts with `factory.mcp_utils` `storage_doc_find(collection="ml_training_runs", query={}, limit=500)` so exceptions remain distinguishable from empty; never self-invoke an ML MCP tool.
- Wrap the existing within-brick learning projection in an exception-aware supplier.
- Inject the existing `TrackingRuntime` supplier into Observatory MCP registration and obtain fine-tuning jobs through `get_finetuner().list_jobs()`.
- Report live models unavailable/count `null`; do not read `_inference_registry`. Public enumeration is child Bead `python-factory-vx2hp`.

## 2. Observatory aggregation

- Implement every row of the training/learning availability truth table: all four available-source states plus training unavailable, learning unavailable, and both unavailable.
- Make `population_state=null` whenever either primary population source is unavailable; retain known counts and never emit an exclusive/empty claim in unknown states.
- Build separate training/experiment/receipt-model/fine-tuning/regression/learning counts, progress, and attention records.
- Deduplicate receipt-backed model rows without claiming canonical model IDs.
- Emit Overview progress as top-level `series` compatible with the existing Chart extractor; do not modify Chart.
- Add Hypothesis coverage for state/count/order/dedup/malformed/source-failure invariants.

## 3. Evidence-backed lineage

- Implement the design's field-level verified-edge matrix with renderer-local node IDs and nullable source-native IDs.
- Permit only field-backed receipt `PRODUCED` and explicit learning `HAS_EVENT`/graph relations; never infer temporal Reward→Wallet or next-run links.
- Always expose missing receipt dataset/evaluation links; expose missing model link without `model_path`; expose missing learning dataset/evaluation/model links without canonical refs.
- Add property and fixture coverage, including disconnected graphs and 100-node bound.

## 4. MCP surface

- Register deterministic `ml_get_observatory_summary` and `ml_get_observatory_lineage` with the injected runtime supplier.
- Update capabilities within the allowlist and add schema/registration tests.

## 5. Five pinned brick-declared views

- Return, in order: `ml-overview`, `ml-experiments`, existing `ml-models`, existing `ml-learning-runs`, `ml-lineage`.
- Keep each builder below 200 LOC; reuse existing training/fine-tuning/learning builders where compatible.
- Make Overview useful in learning-only, all-empty, and all unavailable/degraded truth-table states.
- Test exact IDs/order/metadata/tool references.

## 6. Generic frontend capabilities

- Add metadata-driven multi-view selection to BrickViewRenderer, retained per brick by view ID; preserve single-view DOM/content.
- Store selected subview in generic workbench state and publish it through CanvasContextBridge.
- Add `fe_select_brick_view` via existing CopilotKit `useFrontendTool`; validate inputs and mutate state only.
- Add nested `data_path` to Metric and catalog metadata.
- Add neutral Lineage to Python A2UI catalog, native mapping, shared component map/renderer, and parity tests.
- Cover loading/error/stale/empty/disconnected states.
- Do not implement entity focus, DOM querying, or a dispatcher; child Bead `python-factory-7zfe9` owns the controlled-focus seam.

## 7. Collision safety

- Modify only files allowed by the design allowlist.
- Do not touch active evals/events/graph/storage changes, `pyproject.toml`, unrelated specs, branch-owned ML model adapters, ML `runtime.py`, or fine-tuning factory.
- Preserve user-owned worktree changes and file separate Beads for missing upstream evidence/contracts.

## 8. Validation

- Run existing targeted ML and frontend tests before changing tests where practical.
- Run focused ML pytest, shared-renderer tests, Next canvas/workbench tests, and frontend type/build checks.
- Probe the restarted Companion-X MCP server and verify exact tools/views plus honest source states.
- Visually verify empty, learning-only, unavailable, and populated fixtures where a safe local dashboard is available.
- Run guardian and document only pre-existing unrelated failures.

## 9. Documentation and closure

- Treat this spec and focused code comments as eplkz documentation.
- Do not edit canonical docs outside the allowlist; child Bead `python-factory-u780l` owns that follow-up.
- Record deferred promotion/drift/comparison/artifact-viewer, live enumeration (`python-factory-vx2hp`), and entity focus (`python-factory-7zfe9`) scope.
- Store completion context in Companion-X memory with `user_id="kiro-agent"`.
- Close `python-factory-eplkz` with validation evidence.
