# Requirements: Companion-X Cloud Engine

## Introduction

Companion-X runs locally as an MCP server with 31 components and 6 bases. This spec adds a cloud-side compute layer — a Fargate worker triggered by Veritas VeriDrift SNS signals that runs automated security reviews using Strands graph workflows. The cloud engine is ADDITIVE — companion-x stays full-featured locally. Cloud adds persistence (Neo4j), proactive triggers, heavy compute, and team sharing.

This is a new Polylith project (`projects/companion_x_engine`) that wires existing bricks — no new bricks are created.

## Related

- GitHub Issue #360: Companion-X Cloud Architecture RFC (v3)
- GitHub Issue #359: Live Testing Gaps
- Existing project: `projects/companion_x/` (local MCP server — stays unchanged)
- Workflow brick: `components/workflow/` (has run management, step execution, celery/dagster adapters)
- Agent brick: `components/agent/` (has swarm launch, graph workflow)
- Security brick: `components/security/` (has threat modeling, code analysis)
- Evals brick: `components/evals/` (has LLMAJ evaluators)

## Existing Code References

- #[[file:projects/companion_x/pyproject.toml]] — existing project wiring (reference for new project)
- #[[file:components/workflow/src/factory/workflow/runtime/execution/adapters/celery_adapter.py]] — existing async execution adapter
- #[[file:components/agent/src/factory/agent/interface.py]] — agent brick public API
- #[[file:components/security/src/factory/security/core.py]] — security analysis types
- #[[file:.agents/recipes/security-ops.md]] — security operations recipe

## Requirements

### Requirement 1: Polylith Project Scaffold

**User Story:** As a developer, I want a new Polylith project `companion_x_engine` that wires the bricks needed for cloud-side security analysis, so I can deploy it independently from the local MCP server.

#### Acceptance Criteria

1. THE project SHALL be created at `projects/companion_x_engine/` using `foreman_create_project`.
2. THE project SHALL wire these bricks: agent, security, evals, graph, kb, llm_gateway, workflow, events, telemetry, logger, storage, mcp_utils, config, permissions, auth, memory.
3. THE project SHALL NOT wire UI-only bricks: ui, dashboard, flet_dashboard, browser, games, blockchain, payments, hardware.
4. THE project SHALL include a `worker` base for task consumption (SQS polling).
5. THE project's `pyproject.toml` SHALL declare pip dependencies resolved from brick imports via `foreman_resolve_dependencies`.

### Requirement 2: VeriDrift SQS Consumer

**User Story:** As a security platform, I want the cloud engine to consume VeriDrift SNS messages (forwarded to SQS) and trigger automated security reviews when Veritas graph changes are detected.

#### Acceptance Criteria

1. THE engine SHALL include an SQS consumer that polls a configurable queue for VeriDrift messages.
2. THE consumer SHALL parse VeriDrift event payloads to extract: app ID, change type (pipeline update, resource change, ownership change), and affected resources.
3. FOR each VeriDrift event, THE consumer SHALL start a workflow run via the workflow brick's `start_run()`.
4. THE consumer SHALL use exponential backoff on SQS polling errors.
5. THE SQS queue URL SHALL be configurable via environment variable `VERIDRIFT_QUEUE_URL`.
6. THE consumer SHALL emit telemetry spans for each event processed.

### Requirement 3: Security Review Workflow Definition

**User Story:** As a security builder, I want a pre-configured security review workflow that runs the full analysis pipeline (recon → threat model → scan → eval → report) as a Strands graph workflow.

#### Acceptance Criteria

1. THE engine SHALL include a workflow definition YAML at `projects/companion_x_engine/workflows/security_review.yaml`.
2. THE workflow SHALL define these steps: `recon` (query Veritas for app topology), `context` (build security context in graph), `threat_model` (STRIDE analysis via security brick), `eval` (LLMAJ scoring via evals brick), `report` (generate findings document).
3. EACH step SHALL be executable by the workflow brick's step runner.
4. THE workflow SHALL support partial execution (resume from a failed step).
5. THE workflow SHALL emit events via the events brick at each step transition.

### Requirement 4: Neo4j Persistence for Findings

**User Story:** As a security team, I want security review findings persisted in Neo4j so they're queryable across reviews, searchable via the KB, and visible to all team members' companion-x instances.

#### Acceptance Criteria

1. THE engine's report step SHALL store findings as Neo4j nodes with labels `Finding`, `ThreatModel`, `SecurityReview`.
2. FINDINGS SHALL be linked to the Veritas app entity via `FOUND_IN` relationships.
3. FINDINGS SHALL include embedding vectors (via llm_gateway) for semantic search.
4. THE engine SHALL use the graph brick's Neo4j adapter for all graph operations.
5. THE engine SHALL use the KB brick's Neo4j vector store for document-style findings (reports, recommendations).

### Requirement 5: Fargate Task Definition

**User Story:** As a DevOps engineer, I want a Dockerfile and ECS task definition for the cloud engine so I can deploy it to Fargate Spot.

#### Acceptance Criteria

1. THE project SHALL include a `Dockerfile` that builds the companion_x_engine project.
2. THE project SHALL include a `task-definition.json` template for ECS Fargate.
3. THE task definition SHALL specify Fargate Spot capacity provider.
4. THE task definition SHALL configure environment variables for: `NEO4J_URI`, `NEO4J_PASSWORD`, `VERIDRIFT_QUEUE_URL`, `AWS_DEFAULT_REGION`.
5. THE Dockerfile SHALL use a multi-stage build with a slim Python base image.

### Requirement 6: Blueprint Integration

**User Story:** As a developer, I want the cloud engine's infrastructure requirements to be declarable via the blueprint base's `infrastructure_spec()` pattern, so CDK generation works automatically.

#### Acceptance Criteria

1. THE engine SHALL include an `infrastructure.py` module that returns infrastructure specs for: ECS Fargate service, SQS queue, S3 bucket (reports), and IAM roles.
2. THE specs SHALL follow the normalizer's supported shapes (flat or list format).
3. THE blueprint base's `blueprint_generate_cdk` tool SHALL be able to generate a CDK stack from these specs.
