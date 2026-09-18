---
name: "companion-x"
displayName: "Companion-X"
description: "Drive Companion-X — the Python Software Factory's assistant cockpit — over MCP. Progressive discovery over every composed brick: agents, memory, workflow, evals, games, sandbox, terminal, and more."
keywords: ["companion-x", "mcp", "bricks", "agent", "memory", "workflow", "evals"]
author: "wdaniero"
---

# Companion-X

## Overview

Companion-X is the flagship project of the Python Software Factory. This power
mounts its MCP server so an agent (Kiro, KiroCrew, any MCP client) can operate
the product: list bricks, load their tools on demand, and call them.

Two ways to connect — pick one:

| Mode | When | How |
|---|---|---|
| **Stdio (this `mcp.json`)** | You want a private server process with your own brick scope | `uv run python -m factory.mcp_server.core`, run from the repo root |
| **HTTP to the live API** | Companion-X is already running (`scripts/companion-x-ui.sh`) and you want to drive *that* instance with its real data | `{"type": "http", "url": "http://127.0.0.1:8000/mcp/", "headers": {"Authorization": "Bearer <MCP_LOCAL_AUTH_TOKEN>"}}` |

The token for HTTP mode is `MCP_LOCAL_AUTH_TOKEN` in `projects/companion_x/.env`.
Never commit it.

## Onboarding

1. Clone and install: `uv sync` from the repo root.
2. Copy `projects/companion_x/.env.example` to `projects/companion_x/.env` and set
   your model provider (OpenRouter by default).
3. Run the MCP server **from the repo root** so the editable install resolves
   every brick. The `mcp.json` here deliberately omits `cwd`; set it to your
   checkout path if your client requires an absolute working directory.
4. All storage defaults are container-free (SQLite, networkx, files under
   `.storage/`). Backend adapters are selected by env vars documented in
   `projects/companion_x/README.md` — source the `.env` file rather than
   duplicating its values in this power.

## Using the tools

Progressive discovery: only nine meta-tools are exposed until you load a brick.

```text
list_bricks                                  what's registered (tools_count: -1 = not loaded yet)
get_brick_tools("memory")                    lists AND lazy-loads one brick
call_brick_tool("memory", "memory_retrieve", '{"query": "...", "user_id": "kiro-agent"}')
read_brick_resource("graph://schemas/taxonomy/security")
```

`arguments` to `call_brick_tool` is a JSON **string**. Always pass `user_id` to
memory tools. Scope the surface with `MCP_INCLUDE_BRICKS` — you get exactly the
bricks you name, nothing more.

## Guardrails

- Read and exercise the product through MCP; do not restart or reconfigure a
  running owner stack through this connection.
- Automated smoke instances belong on `API_PORT=18000 NEXT_PORT=13000`, never
  on the owner's `:8000/:3000`.
- Steering for architecture, brick anatomy, and MCP tool categories lives in
  `.kiro/steering/` and `.agents/steering/` in the repo.
