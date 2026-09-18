# Design: Companion-X Cloud Engine

## Overview

A new Polylith project that runs as a Fargate worker, consuming VeriDrift signals and executing security review workflows. Uses existing bricks — no new components.

## Architecture

```
VeriDrift SNS ──► SQS Queue ──► companion_x_engine (Fargate Spot)
                                 │
                                 ├── SQS Consumer (polls queue)
                                 │     └── parses VeriDrift event
                                 │
                                 ├── Workflow Brick (orchestrates steps)
                                 │     ├── recon step (Veritas MCP query)
                                 │     ├── context step (graph brick → Neo4j)
                                 │     ├── threat_model step (security brick)
                                 │     ├── eval step (evals brick → LLMAJ)
                                 │     └── report step (storage → S3, graph → Neo4j)
                                 │
                                 ├── Neo4j (findings + vectors + KB)
                                 ├── S3 (report artifacts)
                                 ├── Bedrock (LLM via llm_gateway)
                                 └── OTLP → X-Ray (telemetry)
```

## Project Structure

```
projects/companion_x_engine/
├── pyproject.toml              # Polylith project config
├── Dockerfile                  # Multi-stage build
├── task-definition.json        # ECS Fargate template
├── infrastructure.py           # Blueprint-compatible infra specs
└── workflows/
    └── security_review.yaml    # Pre-configured workflow definition
```

## Key Design Decisions

1. **No new bricks** — the engine wires existing bricks. The SQS consumer is a thin entry point in the worker base.
2. **Workflow brick drives orchestration** — not Step Functions, not custom code. The workflow definition YAML defines the pipeline.
3. **Neo4j is the single persistence layer** — findings as graph nodes, reports as KB documents with embeddings, all in one database.
4. **Veritas is read-only** — the engine queries Veritas MCP for enrichment but never writes to it.
5. **Blueprint-compatible** — infrastructure specs follow the existing normalizer patterns so CDK generation works.

## SQS Consumer Design

The consumer extends the existing worker base pattern. It polls SQS, deserializes VeriDrift events, and dispatches to the workflow brick:

```python
# Pseudocode — actual implementation in worker base
while True:
    messages = sqs.receive_messages(queue_url, max=10, wait=20)
    for msg in messages:
        event = parse_veridrift_event(msg.body)
        workflow.start_run("security_review", input={
            "app_id": event.app_id,
            "change_type": event.change_type,
            "resources": event.affected_resources,
        })
        sqs.delete_message(msg)
```

## Workflow Definition

```yaml
id: security_review
name: Automated Security Review
steps:
  - id: recon
    type: tool_call
    tool: veritas_get_app_topology
    input_map: {app_name: "$.input.app_id"}

  - id: context
    type: tool_call
    tool: graph_add_entity
    depends_on: [recon]

  - id: threat_model
    type: tool_call
    tool: security_analyze
    depends_on: [context]
    input_map: {target: "$.input.app_id", analysis_type: "threat_model"}

  - id: eval
    type: tool_call
    tool: evals_run_experiment
    depends_on: [threat_model]

  - id: report
    type: tool_call
    tool: storage_blob_put
    depends_on: [eval]
```

## Files Created

| File | Purpose |
|------|---------|
| `projects/companion_x_engine/pyproject.toml` | Polylith project wiring |
| `projects/companion_x_engine/Dockerfile` | Container build |
| `projects/companion_x_engine/task-definition.json` | ECS Fargate config |
| `projects/companion_x_engine/infrastructure.py` | Blueprint infra specs |
| `projects/companion_x_engine/workflows/security_review.yaml` | Workflow definition |

## Files NOT Changed

| File | Why |
|------|-----|
| `projects/companion_x/` | Local MCP server stays unchanged |
| Any component brick | Engine uses existing bricks as-is |
| `bases/worker/` | Existing worker base handles SQS pattern |
