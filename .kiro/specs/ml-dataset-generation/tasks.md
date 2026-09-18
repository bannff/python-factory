# Dataset Generation Tasks

This task list is subordinate to the canonical status and acceptance criteria
in `.github/spec/ml-dataset-generation.md`. Each remaining task must have a
Beads issue before implementation begins.

Completed foundations:

- `dataset` brick scaffold, public contracts, local durable store, detached worker, and MCP surface.
- `machine_learning` generation removal and typed dataset handoff.
- Agentic-Datasets v2 adapter primitives, schema gates, checkpoint storage, and compatibility canaries.

Tracked remaining work:

1. Implement the versioned recipe graph, worker-owned stage executor, requested view materialization, and final bundle manifest.
2. Select and implement durable worker recovery semantics: queue/lease, retries, idempotency, cancellation, restart reconciliation, and checkpoint resume.
3. Enforce quality, provenance, authorized fallback, immutable context, and APIGenMT tool-schema snapshot policy.
4. Complete the dataset-to-MLX handoff and public MCP backend selection, then decide and document AI-Fine-Tuning adapter scope and the initial production tracker.
5. Add the Companion-X MCP control-plane workflow and end-to-end validation.
6. Implement the CAN recipe after the generic bundle contract is complete.
