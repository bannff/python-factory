# Design: Companion-X Kiro Power

## Overview

Package Companion-X as a single Kiro Power. The POWER.md is a crisp brick catalog that triggers on keyword match and teaches agents the progressive discovery flow. Steering files provide optional deep-dive workflows.

## Power Structure

```
companion-x/
├── POWER.md          # Frontmatter + overview + brick catalog + discovery flow
├── mcp.json          # MCP server config (local + remote options)
└── steering/         # Optional deep-dive workflows (v2)
    ├── security-review.md
    ├── memory-pipeline.md
    └── ml-experiments.md
```

## POWER.md Design Philosophy

The key insight: agents don't explore proactively. They use what they can see. The POWER.md must:

1. Be activated via keyword matching (broad keywords across all brick domains)
2. Immediately show what's available (brick catalog table)
3. Teach the 3-step discovery flow (list → get_tools → call_tool)
4. Stay under 200 lines — no individual tool schemas, no verbose prose

### POWER.md Structure (target ~120 lines)

```markdown
---
name: "companion-x"
displayName: "Companion X"
description: "Progressive-discovery MCP server with 28+ bricks. Each brick is a full MCP interface with tools, resources, and prompts. Covers memory, knowledge base, graph, security, auth, events, workflow, ML, and more."
keywords: ["companion-x", "memory", "knowledge", "graph", "security", "auth", "cache", "events", "workflow", "agent", "evals", "ml", "mcp", "veritas", "permissions", "notification", "storage", "telemetry"]
author: "Daniel Rodrigo"
---

# Companion X

Progressive-discovery MCP server. 28+ bricks, each with full MCP primitives (tools, resources, prompts). One server, everything you need.

## How It Works

3-step progressive discovery — don't guess tool names, discover them:

1. `list_bricks` → see all available bricks
2. `get_brick_tools("memory")` → get tool schemas for a brick
3. `call_brick_tool("memory", "memory_store", {"user_id": "me", "content": "..."})` → invoke

Also available: `get_brick_resources(name)`, `get_brick_prompts(name)`, `read_brick_resource(name, uri)`, `render_brick_prompt(name, prompt, args)`.

## Brick Catalog

| Brick | What it does | Prompts | Resources |
|-------|-------------|---------|-----------|
| memory | Store/retrieve agent memories. Semantic + graph hybrid search. | ✓ | ✓ |
| kb | Knowledge base. Ingest docs, semantic search, collections. | ✓ | ✓ |
| graph | Neo4j graph operations. Entities, relationships, traversal, GDS. | ✓ | ✓ |
| security | Threat models, code analysis, vulnerability scanning. | ✓ | ✓ |
| veritas | Security graph queries. App topology, findings, compliance. | ✓ | ✓ |
| auth | JWT verification, token exchange, principal resolution. | ✓ | ✓ |
| ... (all bricks listed) |
```

### What NOT to put in POWER.md

- Individual tool parameter schemas (use `get_brick_tools`)
- Verbose workflow descriptions (use steering files)
- Installation instructions for the monorepo (this connects to a deployed server)
- Architecture diagrams or internal implementation details

## mcp.json Design

Two connection modes documented:

```json
{
  "mcpServers": {
    "companion-x": {
      "command": "uvx",
      "args": ["companion-x@latest"],
      "env": {
        "NEO4J_URI": "YOUR_NEO4J_URI",
        "NEO4J_PASSWORD": "YOUR_NEO4J_PASSWORD",
        "AWS_PROFILE": "YOUR_AWS_PROFILE",
        "AWS_DEFAULT_REGION": "us-east-1",
        "MEMORY_BACKEND": "neo4j",
        "MEMORY_EMBEDDINGS": "bedrock",
        "GRAPH_BACKEND": "neo4j",
        "KB_BACKEND": "neo4j"
      },
      "autoApprove": [
        "list_bricks", "get_brick_tools", "get_brick_resources",
        "get_brick_prompts", "get_capabilities", "health_check",
        "call_brick_tool", "read_brick_resource", "render_brick_prompt"
      ]
    }
  }
}
```

For remote AgentCore deployment, replace `command`/`args` with:
```json
{
  "url": "https://YOUR_AGENTCORE_ENDPOINT/mcp",
  "headers": { "Authorization": "Bearer YOUR_TOKEN" }
}
```

## Steering Files (v2, optional)

Each under 100 lines. Workflow steps with tool names, not prose.

### security-review.md
Steps: get_app_topology → graph_add_entity → security_analyze(threat_model) → security_analyze(code_analysis) → evals_run_experiment → report

### memory-pipeline.md  
Steps: memory_store → memory_retrieve → memory_hybrid_search → memory_consolidate

### ml-experiments.md
Steps: evals_create_experiment → evals_run_experiment → evals_get_results → evals_compare

## Brick Catalog Generation

The brick catalog table in POWER.md should be generated from live data:

```bash
# Get brick list
call_brick_tool: list_bricks

# For each brick, check primitives
call_brick_tool: get_brick_tools(name)
call_brick_tool: get_brick_resources(name)  
call_brick_tool: get_brick_prompts(name)
```

This ensures the catalog stays accurate as bricks are added/removed.

## Distribution

1. Local: copy `companion-x/` to `~/.kiro/powers/repos/companion-x/`
2. Git: push to public GitHub repo, add via Kiro Powers UI
3. Kiro marketplace: submit when available

## Dependencies

- The Power is config + docs only — no code dependencies
- Requires either: local Neo4j + AWS credentials, OR remote AgentCore endpoint
- `uvx companion-x@latest` requires the package to be published (PyPI or internal registry)

## Open Questions

1. Should `autoApprove` include `call_brick_tool` or just the discovery meta-tools? (Currently: yes, include it — the brick-level tools handle their own authorization)
2. Should the brick catalog include tool counts? (Leaning no — it's noise, and counts change)
3. Remote AgentCore: how does auth work? Bearer token? SigV4? (Depends on python-factory-p7g resolution)
