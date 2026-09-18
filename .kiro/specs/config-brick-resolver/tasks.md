# Tasks: Config Brick as Central Backend Resolver

## Phase 1: Config Brick Core

- [x] 1. Create `InfraEnvConfigStore` adapter at `components/config/src/factory/config/runtime/adapters/infra_env.py`. Implements `ConfigStore` protocol. Maps dot-notation keys to uppercase-underscore env vars (`neo4j.uri` → `NEO4J_URI`). No prefix, no hardcoded mapping dict — pure convention.
  - Requirements: 5
  - Files: `components/config/src/factory/config/runtime/adapters/infra_env.py`

- [x] 2. Add lazy bootstrap to `ConfigRuntime`. On first `get_layered()` call, auto-add SSM layer (prefix `/art/support/`, best-effort) and InfraEnv layer (highest priority). Add `_bootstrapped` flag to avoid re-bootstrapping. SSM failure logs warning and continues.
  - Requirements: 1
  - Files: `components/config/src/factory/config/runtime/runtime.py`

- [x] 3. Add `get_infra()` and `get_neo4j_config()` convenience functions to config brick's `interface.py`. `get_infra(key, default)` wraps `get_runtime().get_layered(key, default)`. `get_neo4j_config()` returns dict with uri/user/password/database.
  - Requirements: 2, 4
  - Files: `components/config/src/factory/config/interface.py`

## Phase 2: Wire Bricks

- [x] 4. Update memory brick `server.py`: replace `os.environ.get("MEMORY_BACKEND", ...)` with `get_infra("memory.backend", "memory")`. Replace Neo4j connection params with `get_neo4j_config()`.
  - Requirements: 2, 4
  - Files: `components/memory/src/factory/memory/server.py`

- [x] 5. Update events brick `server.py`: replace `os.environ.get("EVENTS_BACKEND", ...)` and Neo4j/Redis env vars with `get_infra()` / `get_neo4j_config()`.
  - Requirements: 2, 4
  - Files: `components/events/src/factory/events/server.py`

- [x] 6. Update graph brick `server.py`: replace `os.environ.get("GRAPH_BACKEND", ...)` with `get_infra("graph.backend", "networkx")`.
  - Requirements: 2
  - Files: `components/graph/src/factory/graph/server.py`

- [x] 7. Update kb brick `server.py`: replace `os.environ.get("KB_BACKEND", ...)` and Neo4j env vars with `get_infra()` / `get_neo4j_config()`.
  - Requirements: 2, 4
  - Files: `components/kb/src/factory/kb/server.py`

- [x] 8. Update storage runtime `runtime.py`: replace `os.environ.get("STORAGE_DOC_BACKEND", ...)`, `os.environ.get("STORAGE_GRAPH_BACKEND", ...)`, and Neo4j env vars with `get_infra()` / `get_neo4j_config()`.
  - Requirements: 2, 4
  - Files: `components/storage/src/factory/storage/runtime/runtime.py`

- [x] 9. Update security brick `server.py`: replace `os.environ.get("SECURITY_PERSISTENCE", ...)` with `get_infra("security.persistence", "memory")`.
  - Requirements: 2
  - Files: `components/security/src/factory/security/server.py`

## Phase 3: Dockerfile Cleanup & Validation

- [x] 10. Remove hardcoded backend env vars from `projects/companion_x/Dockerfile`. Keep only `AWS_REGION=us-east-1`. Remove `NEO4J_URI`, `NEO4J_USER`, `GRAPH_BACKEND`, `MEMORY_BACKEND`, `MEMORY_EMBEDDINGS`, `KB_BACKEND`, `EVENTS_BACKEND`, `STORAGE_DOC_BACKEND`, `STORAGE_GRAPH_BACKEND`, `SECURITY_PERSISTENCE`.
  - Requirements: 3
  - Files: `projects/companion_x/Dockerfile`

- [x] 11. Run existing tests (`uv run pytest`) and `foreman_guardian_check` to verify no regressions. All bricks should still default to in-memory/local backends when no SSM or env vars are present.
  - Requirements: 2, 3
  - Files: none (validation)

- [x] 12. Build Docker image, push to ECR, deploy to AgentCore via `fix-protocol`. Test memory_store through comp-x-v2 MCP to verify Neo4j connection resolves from SSM.
  - Requirements: 1, 3, 4
  - Files: none (deployment + testing)
