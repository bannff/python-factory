# Dataset Generation Requirements

The canonical requirements and implementation status live in
`.github/spec/ml-dataset-generation.md`. This file preserves the original
P0/P1/P2 requirement grouping and must not be used to infer that unfinished
execution behavior is implemented.

## P0: Extraction and Async Decoupling
1. **Component Boundary**: Dataset generation must occur within `components/dataset/`, not `machine_learning`.
2. **Global Consumption**: Generated datasets must be consumable by `evals`, RAG apps, or `machine_learning` as simple URIs.
3. **Non-Blocking Architecture**: Pipeline tasks take hours. The public API and MCP tools must return immediately with a `job_id`. Long-running tasks must execute in an out-of-process worker queue.
4. **No Interface Hardcoding**: Domain-specific pipeline stage logic (e.g., `s2m`) must remain an internal implementation detail of the `dataset` worker layer.

## P1: Worker Validation and Reproducibility
1. **Durable Execution**: Select and document the worker backend through the
	corresponding Beads issue. The implementation must provide leases, retries,
	cancellation, restart recovery, idempotency, and checkpoint resume.
2. **Recipe Execution**: Execute a versioned declarative recipe through
	checkpointable stage adapters and materialize named training views only
	after schema and quality gates pass.
3. **Reproducibility**: Persist immutable input, recipe, stage, context, tool
	schema, quality, provenance, and authorized-fallback digests in the final
	manifest.

## P2: Machine Learning Refactor
1. The `machine_learning` API must be stripped of generation logic. It must assume datasets already exist and are strictly referenced by URI or ID.
2. The dataset worker must emit a verified `training_uri` for the selected
	view before an ML backend can launch.
3. Companion-X must submit and observe jobs through MCP using frozen bounded
	context and tool-schema snapshots; it must not execute individual stages.
