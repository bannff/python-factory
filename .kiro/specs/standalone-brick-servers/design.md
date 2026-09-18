# Design: Standalone Brick MCP Servers

## Overview

Add a thin `mcp/server.py` + `__main__.py` entry point to any brick so it can run as an independent stdio MCP server. The brick's existing `server.py::create_mcp_server()` does all the work — the standalone shell just calls it and runs.

Primary use case: split topology where AgentCore hosts most bricks, but Midway-dependent bricks (Veritas, SIPP) run locally on the developer's machine.

## Architecture: Split Topology

```
┌─────────────────────────────────────────────────────┐
│                   Kiro IDE / Agent                   │
│                                                      │
│  mcp.json configures 3 servers:                      │
│  ┌─────────────────┐ ┌──────────┐ ┌──────────┐      │
│  │  companion-x    │ │ veritas  │ │   sipp   │      │
│  │  (remote/local) │ │ (local)  │ │ (local)  │      │
│  └────────┬────────┘ └────┬─────┘ └────┬─────┘      │
└───────────┼───────────────┼────────────┼─────────────┘
            │               │            │
     ┌──────▼──────┐  ┌────▼────┐  ┌────▼────┐
     │  AgentCore  │  │ stdio   │  │ stdio   │
     │  (cloud)    │  │ local   │  │ local   │
     │             │  │         │  │         │
     │ auth, kb,   │  │ Midway  │  │ Midway  │
     │ graph, ...  │  │ cookies │  │ cookies │
     │ 20+ bricks  │  │ → real  │  │ → real  │
     │             │  │ Veritas │  │ SIPP    │
     └─────────────┘  └─────────┘  └─────────┘
```

Key insight: the agent sees tools from all three servers in a flat namespace. It doesn't know or care which server hosts which tool. Swapping a local server for a remote one (e.g., when Veritas MCP Server ships 4/17/2026) is a config change only.

## Standalone Entry Point Pattern

Two files per brick, under 20 lines total:

### `mcp/server.py` — The entry point

```python
"""Standalone MCP server for <brick> brick.

Run: python -m factory.<brick>.mcp.server
"""
from __future__ import annotations

from factory.<brick>.server import create_mcp_server


def main() -> None:
    """Run <brick> as a standalone stdio MCP server."""
    mcp = create_mcp_server()
    mcp.run()


if __name__ == "__main__":
    main()
```

### `mcp/__main__.py` — Enables `python -m` execution

```python
"""Allow running as: python -m factory.<brick>.mcp.server"""
from factory.<brick>.mcp.server import main

main()
```

That's it. The brick's existing `server.py::create_mcp_server()` handles runtime init, adapter selection (via env vars), and MCP tool/resource/prompt registration. The standalone shell adds zero logic.

## Adapter Selection (No Changes Needed)

Both Veritas and SIPP already select adapters via env vars:

```python
# veritas/runtime/runtime.py
backend = os.environ.get("VERITAS_BACKEND", "memory")

# sipp/runtime/runtime.py  
backend = os.environ.get("SIPP_BACKEND", "memory")
```

For standalone local use with real services:
- `VERITAS_BACKEND=midway` → uses MidwayVeritasAdapter (real Veritas graph)
- `SIPP_BACKEND=midway` → uses MidwaySIPPAdapter (real SIPP catalog)

No new config mechanism needed.

## Kiro Power mcp.json (Split Topology)

The Kiro Power's `mcp.json` configures all servers. This extends the existing kiro-power-packaging spec:

```json
{
  "mcpServers": {
    "companion-x": {
      "command": "uv",
      "args": ["run", "python", "-m", "factory.mcp_server.core"],
      "cwd": "/path/to/python-factory",
      "env": {
        "MCP_SERVER_NAME": "companion-x",
        "MCP_INCLUDE_BRICKS": "auth,permissions,telemetry,agent,evals,integrations,memory,llm_gateway,workflow,kb,graph,storage,security,cache,events,config,ui,notification,logger,http",
        "MEMORY_BACKEND": "neo4j",
        "MEMORY_EMBEDDINGS": "bedrock",
        "GRAPH_BACKEND": "neo4j",
        "KB_BACKEND": "neo4j",
        "NEO4J_URI": "bolt://localhost:17687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "YOUR_PASSWORD",
        "AWS_PROFILE": "YOUR_PROFILE",
        "AWS_DEFAULT_REGION": "us-east-1"
      },
      "autoApprove": [
        "list_bricks", "get_brick_tools", "get_brick_resources",
        "get_brick_prompts", "get_capabilities", "health_check",
        "call_brick_tool", "read_brick_resource", "render_brick_prompt"
      ]
    },
    "veritas": {
      "command": "uv",
      "args": ["run", "python", "-m", "factory.veritas.mcp.server"],
      "cwd": "/path/to/python-factory",
      "env": {
        "VERITAS_BACKEND": "midway"
      },
      "autoApprove": []
    },
    "sipp": {
      "command": "uv",
      "args": ["run", "python", "-m", "factory.sipp.mcp.server"],
      "cwd": "/path/to/python-factory",
      "env": {
        "SIPP_BACKEND": "midway"
      },
      "autoApprove": []
    }
  }
}
```

Note: `MCP_INCLUDE_BRICKS` on companion-x excludes `veritas` and `sipp` since they run standalone. This avoids duplicate tool registration.

## Tenet Audit

| Tenet | Compliance | Notes |
|-------|-----------|-------|
| MCP-First | ✅ | Standalone servers expose full MCP primitives |
| Polymorphic | ✅ | Same adapter pattern, same env var selection |
| Clean Architecture | ✅ | Entry point is pure transport shell, no logic |
| No Cross-Imports | ✅ | Entry point imports only its own brick's `server.py` |
| Gateway Architecture | ✅ | Parallel path (standalone), not bypass — aggregator unchanged |
| <200 LOC | ✅ | ~15 lines total per brick |

## Future: Veritas MCP Server Swap (4/17/2026)

When the official Veritas MCP Server ships, replace the local entry in `mcp.json`:

```json
{
  "veritas": {
    "command": "uvx",
    "args": ["veritas-mcp-server@latest"],
    "env": { "AUTH_METHOD": "cloudauth" }
  }
}
```

No code changes. The agent sees the same tool names from a different server. This is the power of the split topology — each server is independently replaceable.

## What This Does NOT Change

- The aggregator (`core.py`) — untouched
- Brick internals (runtime, adapters, MCP tools) — untouched
- Existing `server.py::create_mcp_server()` — untouched
- BRICKS_INDEX.yaml — no changes needed
- Tests — standalone entry points are thin shells, tested by running them

## Open Questions

1. Should standalone servers include a `--transport` flag for SSE/HTTP in addition to stdio? (Leaning no for v1 — stdio is sufficient for local use.)
2. Should we add a `standalone: true` field to BRICK.yaml? (Leaning no — any brick CAN be standalone, it's just a matter of adding the entry point.)
