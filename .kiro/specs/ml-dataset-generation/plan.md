# Dataset Generation Plan

## Objective
Extract and componentize the dataset generation pipeline (formerly tied to the `machine_learning` brick) into a dedicated `dataset` brick. 
This decouples dataset creation from fine-tuning, allowing produced datasets to be consumed globally (e.g., by `evals`, RAG apps, or `machine_learning`) without hardcoding them into the fine-tuning lifecycle.

## Architectural Verdict
1. **Dedicated Brick**: Create a `components/dataset/` brick. The `machine_learning` brick will pivot to orchestration/MLFlow and consume generic dataset URIs.
2. **Asynchronous Execution (Non-Blocking)**: Because the legacy A->B pipeline takes hours, it must not block the main FastAPI/MCP event loops. The `dataset` brick will act as a lightweight job dispatcher and status tracker. Actual execution will happen in a persistent out-of-process worker queue.
3. **No Hardcoded Lifecycles**: Specific execution concepts (like `s2m` or `apigenmt`) will be owned by the `dataset` worker layer, not leaked into global interfaces.

*Note: The exact persistent queuing backend (e.g., RQ, Celery, or subprocess state tracking) requires further research before full deployment.*

## Milestones

Completed foundations:

1. Scaffold `dataset` brick and freeze public job/artifact contracts.
2. Refactor generation authority out of `machine_learning`.
3. Add the MCP job/status/artifact surface and local detached-worker foundation.
4. Add pinned Agentic-Datasets v2 adapter and checkpoint primitives.

Remaining milestones, tracked in Beads:

5. Build the worker execution strategy and versioned recipe executor.
6. Add durable retry, idempotency, restart recovery, and checkpoint resume.
7. Enforce quality/provenance/fallback/tool-schema policies and emit usable training views.
8. Wire the Companion-X MCP control-plane workflow and validate the end-to-end handoff.
9. Decide production tracking and AI-Fine-Tuning adapter scope.
10. Deliver the CAN vertical recipe last.
