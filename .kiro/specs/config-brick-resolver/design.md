# Design: Config Brick as Central Backend Resolver

## Overview

The config brick becomes the infrastructure discovery layer. Like the MCP aggregator discovers tools, the config runtime discovers infrastructure. On first access, it bootstraps env + SSM layers. Bricks call `get_layered("neo4j.uri")` and get the right value — from SSM in production, from env vars in Docker Compose, from defaults in local dev.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Config Runtime                         │
│                                                           │
│  Layers (last wins):                                      │
│    1. SSM (/art/support/*)     ← CDK writes these        │
│    2. InfraEnvConfigStore      ← NEO4J_URI, GRAPH_BACKEND│
│                                                           │
│  get_layered("neo4j.uri")                                 │
│    → checks InfraEnv first (NEO4J_URI)                    │
│    → falls back to SSM (/art/support/neo4j/uri)           │
│    → falls back to caller default                         │
│                                                           │
│  get_neo4j_config()                                       │
│    → {"uri": ..., "user": ..., "password": ..., ...}      │
└──────────┬────────────────────────────────────────────────┘
           │
    ┌──────┴──────┐
    │  Bricks     │
    │             │
    │  memory     │  get_layered("memory.backend", "memory")
    │  graph      │  get_layered("graph.backend", "networkx")
    │  events     │  get_layered("events.backend", "memory")
    │  kb         │  get_layered("kb.backend", "neo4j")
    │  storage    │  get_layered("storage.doc.backend", "tinydb")
    │  security   │  get_layered("security.persistence", "memory")
    └─────────────┘
```

## Key Design Decisions

### 1. InfraEnvConfigStore (new adapter)

The existing `EnvConfigStore` uses a `FACTORY_` prefix. Infrastructure env vars like `NEO4J_URI` and `GRAPH_BACKEND` are unprefixed. Rather than changing the existing adapter (which would break application-level config), we add a new `InfraEnvConfigStore` that maps dot-notation keys to uppercase-underscore env vars:

```
neo4j.uri         → NEO4J_URI
graph.backend     → GRAPH_BACKEND
storage.doc.backend → STORAGE_DOC_BACKEND
```

Convention: replace dots with underscores, uppercase everything. No prefix. This is a pure convention — no mapping dict needed.

### 2. Lazy Bootstrap

The config runtime bootstraps layers on first `get_layered()` call:

```python
def get_layered(self, key, default=None):
    if not self._bootstrapped:
        self._bootstrap()
    # ... existing layer resolution
```

`_bootstrap()` adds:
1. SSM layer (prefix `/art/support/`, best-effort)
2. InfraEnv layer (highest priority)

This means:
- Local dev: no SSM, no env vars → defaults win → in-memory backends
- Docker Compose: env vars set → env layer wins → configured backends
- AgentCore: SSM available + maybe env vars → SSM provides Neo4j URI, env can override

### 3. Convenience Functions in interface.py

The config brick's `interface.py` exposes:

```python
from factory.config.interface import get_infra, get_neo4j_config

# Single value
uri = get_infra("neo4j.uri", "bolt://localhost:7687")

# Full Neo4j config dict
neo4j = get_neo4j_config()
# {"uri": "bolt://10.0.2.69:7687", "user": "neo4j", "password": "...", "database": "neo4j"}
```

These are thin wrappers around `get_runtime().get_layered()`.

### 4. Brick server.py Changes

Each brick's `server.py` replaces `os.environ.get()` with `get_infra()`:

Before:
```python
backend = os.environ.get("MEMORY_BACKEND", "memory")
uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
```

After:
```python
from factory.config.interface import get_infra, get_neo4j_config
backend = get_infra("memory.backend", "memory")
neo4j = get_neo4j_config()
```

### 5. Dockerfile Cleanup

Before (10+ env vars):
```dockerfile
ENV NEO4J_URI=bolt://localhost:7687
ENV NEO4J_USER=neo4j
ENV GRAPH_BACKEND=neo4j
ENV MEMORY_BACKEND=neo4j
# ... 6 more
```

After (1 env var):
```dockerfile
ENV AWS_REGION=us-east-1
```

Everything else discovered from SSM at runtime.

## Key-to-Env Mapping Convention

The `InfraEnvConfigStore` uses a simple convention — no hardcoded mapping dict:

```python
def _key_to_env(self, key: str) -> str:
    """neo4j.uri → NEO4J_URI"""
    return key.upper().replace(".", "_")
```

This means any dot-notation key automatically maps to the corresponding env var. Bricks and the Dockerfile use the same naming convention.

## SSM Namespace

CDK writes params under `/art/support/`:

| SSM Path | Dot Key | Value |
|----------|---------|-------|
| `/art/support/neo4j/uri` | `neo4j.uri` | `bolt://10.0.2.69:7687` |
| `/art/support/neo4j/instance-id` | `neo4j.instance.id` | `i-0f92fd649d00eceff` |

The SSM adapter already handles this mapping (slash → dot conversion with prefix stripping).

## Files Changed

| File | Change |
|------|--------|
| `components/config/src/factory/config/runtime/adapters/infra_env.py` | New: InfraEnvConfigStore |
| `components/config/src/factory/config/runtime/runtime.py` | Add lazy bootstrap with SSM + InfraEnv layers |
| `components/config/src/factory/config/interface.py` | Add `get_infra()`, `get_neo4j_config()` |
| `components/memory/src/factory/memory/server.py` | Use `get_infra()` / `get_neo4j_config()` |
| `components/graph/src/factory/graph/server.py` | Use `get_infra()` |
| `components/events/src/factory/events/server.py` | Use `get_infra()` / `get_neo4j_config()` |
| `components/kb/src/factory/kb/server.py` | Use `get_infra()` / `get_neo4j_config()` |
| `components/storage/src/factory/storage/runtime/runtime.py` | Use `get_infra()` / `get_neo4j_config()` |
| `components/security/src/factory/security/server.py` | Use `get_infra()` |
| `projects/companion_x/Dockerfile` | Remove hardcoded backend env vars |

## What Does NOT Change

- The existing `EnvConfigStore` (FACTORY_ prefix) — still available for app config
- The `SSMConfigStore` — used as-is, just wired as a layer
- The `ConfigStore` protocol — no changes
- Brick runtime code / adapters — only `server.py` wiring changes
- Local dev workflow — defaults still work with no config
