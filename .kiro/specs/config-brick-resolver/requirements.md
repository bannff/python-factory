# Requirements: Config Brick as Central Backend Resolver

## Introduction

Every brick in the factory currently does its own `os.environ.get("X_BACKEND", "default")` independently in `server.py`. Nobody uses the config brick. Meanwhile, the config brick already has layered config (`add_layer` / `get_layered`), an SSM adapter that reads from Parameter Store, and an env adapter. The art-platform CDK stacks already write SSM params (e.g. `/art/support/neo4j/uri = bolt://10.0.2.69:7687`).

This spec wires them together: the config brick becomes the central resolver for all infrastructure settings, the same way the MCP aggregator is the central resolver for all tools. Bricks snap to whatever infrastructure is available — like magnets.

## The Analogy

```
MCP aggregator:  list_bricks → get_brick_tools → call_brick_tool
Config resolver:  bootstrap layers → get_layered("neo4j.uri") → brick auto-configures
```

## Current State

- 6 bricks read `os.environ.get()` for backend selection: memory, graph, events, kb, storage, security
- 4 bricks read `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` directly: memory, events, kb, storage
- Dockerfile has 10+ hardcoded `ENV` directives for backend wiring
- SSM params exist at `/art/support/neo4j/uri` and `/art/support/neo4j/instance-id` (written by CDK)
- Config brick has `ConfigRuntime` with `add_layer()`, `get_layered()`, `EnvConfigStore`, `SSMConfigStore`
- Config brick's `EnvConfigStore` uses a `FACTORY_` prefix — bricks use unprefixed vars like `NEO4J_URI`

## Related

- Bead: `python-factory-g6b` (Config brick as central backend resolver)
- Bead: `python-factory-hpx` (Deploy Neo4j in AgentCore VPC — superseded by this)
- Spec: `.kiro/specs/companion-x-infra/` (CDK stacks that write SSM params)
- File: `#[[file:components/config/src/factory/config/runtime/runtime.py]]`
- File: `#[[file:components/config/src/factory/config/runtime/adapters/ssm_adapter.py]]`
- File: `#[[file:components/config/src/factory/config/runtime/adapters/env_adapter.py]]`
- File: `#[[file:projects/companion_x/Dockerfile]]`

## Requirements

### Requirement 1: Bootstrap Layered Config on Startup

**User Story:** As a brick developer, I want the config runtime to be pre-bootstrapped with env + SSM layers when my brick initializes — so I can call `get_layered()` without setting up layers myself.

#### Acceptance Criteria

1. WHEN the config runtime initializes, it SHALL automatically add an env layer and (optionally) an SSM layer.
2. THE env layer SHALL read unprefixed env vars (e.g. `NEO4J_URI`, `GRAPH_BACKEND`) — not the current `FACTORY_` prefix — using a dot-notation key mapping (e.g. `neo4j.uri` → `NEO4J_URI`).
3. THE SSM layer SHALL read from the `/art/support/` prefix, mapping SSM paths to dot-notation keys (e.g. `/art/support/neo4j/uri` → `neo4j.uri`).
4. THE SSM layer SHALL be best-effort: if boto3 is unavailable or SSM is unreachable, the runtime SHALL log a warning and continue with env + defaults only.
5. LAYER priority SHALL be: SSM (lowest) → env vars (highest). Env vars always override SSM.
6. THE bootstrap SHALL happen lazily on first `get_layered()` call, not at import time — to avoid slowing down local dev where SSM is irrelevant.

### Requirement 2: Bricks Use Config Runtime Instead of os.environ.get()

**User Story:** As a brick developer, I want a single function call to resolve my backend settings — so I don't scatter `os.environ.get()` calls with hardcoded defaults throughout my server.py.

#### Acceptance Criteria

1. EACH brick's `server.py` SHALL resolve backend settings via the config runtime's `get_layered()` method.
2. THE config brick SHALL expose a convenience function (e.g. `get_infra(key, default)`) in its `interface.py` that wraps `get_runtime().get_layered(key, default)` with auto-bootstrap.
3. BRICKS SHALL use consistent dot-notation keys: `neo4j.uri`, `neo4j.user`, `neo4j.password`, `neo4j.database`, `graph.backend`, `memory.backend`, `memory.embeddings`, `kb.backend`, `events.backend`, `storage.doc.backend`, `storage.graph.backend`, `security.persistence`.
4. THE following bricks SHALL be updated: memory, graph, events, kb, storage, security.
5. LOCAL dev SHALL continue to work unchanged — if no SSM and no env vars are set, bricks fall back to their current defaults (in-memory, networkx, chroma, etc.).

### Requirement 3: Dockerfile Cleanup

**User Story:** As a DevOps engineer, I want the Dockerfile to have minimal env vars — so backend wiring is discovered from SSM at runtime, not baked into the image.

#### Acceptance Criteria

1. THE Dockerfile SHALL remove all brick backend selector env vars (`GRAPH_BACKEND`, `MEMORY_BACKEND`, etc.).
2. THE Dockerfile SHALL remove hardcoded `NEO4J_URI`, `NEO4J_USER` env vars.
3. THE Dockerfile MAY retain `AWS_REGION=us-east-1` to help the SSM adapter find the right region.
4. BRICKS SHALL auto-discover Neo4j connection from SSM (`/art/support/neo4j/uri`) without any Dockerfile env vars.
5. IF SSM is unreachable (e.g. local dev without AWS creds), bricks SHALL fall back to in-memory/local defaults gracefully.

### Requirement 4: Neo4j Connection Convenience

**User Story:** As a brick developer building a Neo4j adapter, I want a single call to get the full Neo4j connection config — so I don't repeat uri/user/password resolution in every adapter.

#### Acceptance Criteria

1. THE config brick SHALL expose a `get_neo4j_config()` convenience function returning `{"uri": ..., "user": ..., "password": ..., "database": ...}`.
2. ALL Neo4j adapters (memory, events, kb, storage, graph) SHALL use this function instead of their own `os.environ.get()` calls.
3. THE function SHALL resolve each field through `get_layered()` with sensible defaults.

### Requirement 5: Env Adapter Key Mapping

**User Story:** As a brick developer, I want the env adapter to understand both `FACTORY_`-prefixed keys and unprefixed infrastructure keys — so existing env vars like `NEO4J_URI` work without renaming.

#### Acceptance Criteria

1. THE config brick SHALL provide an env adapter (or adapter configuration) that maps dot-notation keys to unprefixed env vars: `neo4j.uri` → `NEO4J_URI`, `graph.backend` → `GRAPH_BACKEND`, etc.
2. THE mapping SHALL use a consistent convention: dots become underscores, all uppercase. E.g. `storage.doc.backend` → `STORAGE_DOC_BACKEND`.
3. THE existing `FACTORY_`-prefixed `EnvConfigStore` SHALL remain available for application-level config — the infra env adapter is a separate layer for infrastructure wiring.
