# Tasks: Companion-X Cloud Engine

## Tasks

- [ ] 1. Create `projects/companion_x_engine/` Polylith project via `foreman_create_project` with bricks: agent, security, evals, graph, kb, llm_gateway, workflow, events, telemetry, logger, storage, mcp_utils, config, permissions, auth, memory, worker.
  - Requirements: 1
  - Files: `projects/companion_x_engine/pyproject.toml`

- [ ] 2. Create `security_review.yaml` workflow definition with steps: recon, context, threat_model, eval, report. Each step maps to an existing MCP tool.
  - Requirements: 3
  - Files: `projects/companion_x_engine/workflows/security_review.yaml`

- [ ] 3. Implement VeriDrift SQS consumer entry point in the worker base pattern. Parse VeriDrift event payloads, dispatch to workflow brick's `start_run()`. Configurable via `VERIDRIFT_QUEUE_URL` env var.
  - Requirements: 2
  - Files: `projects/companion_x_engine/` (entry point module)

- [ ] 4. Implement report step logic: store findings as Neo4j nodes (`Finding`, `ThreatModel`, `SecurityReview` labels) with `FOUND_IN` relationships to app entities. Generate embeddings for semantic search. Store report artifacts in S3 via storage brick.
  - Requirements: 4
  - Files: `projects/companion_x_engine/` (report step module)

- [ ] 5. Create Dockerfile (multi-stage, slim Python base) and `task-definition.json` template for ECS Fargate Spot. Configure env vars for Neo4j, SQS, AWS region.
  - Requirements: 5
  - Files: `projects/companion_x_engine/Dockerfile`, `projects/companion_x_engine/task-definition.json`

- [ ] 6. Create `infrastructure.py` with blueprint-compatible infrastructure specs for: ECS Fargate service, SQS queue, S3 bucket, IAM roles. Validate with `blueprint_validate_specs`.
  - Requirements: 6
  - Files: `projects/companion_x_engine/infrastructure.py`
