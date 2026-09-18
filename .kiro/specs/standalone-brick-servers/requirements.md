# Requirements: Standalone Brick MCP Servers

## Introduction

The Python Software Factory runs most bricks in AgentCore (cloud), but some bricks (Veritas, SIPP) depend on Midway authentication which only works from a developer's local machine. Rather than building complex auth bridges, we add thin standalone entry points so any brick can run as an independent stdio MCP server — same code, same adapters, no duplication.

This enables a split topology: AgentCore hosts the majority of bricks, while Midway-dependent bricks run locally as stdio servers. The Kiro Power's `mcp.json` configures all three servers (companion-x remote, veritas local, sipp local) so agents see a unified tool surface.

## Related

- Aggregator entry point: #[[file:bases/mcp_server/src/factory/mcp_server/core.py]]
- Veritas runtime (adapter selection): #[[file:components/veritas/src/factory/veritas/runtime/runtime.py]]
- SIPP runtime (adapter selection): #[[file:components/sipp/src/factory/sipp/runtime/runtime.py]]
- Kiro Power packaging spec: #[[file:.kiro/specs/kiro-power-packaging/design.md]]
- Current MCP config: #[[file:.kiro/settings/mcp.json]]
- Architecture: #[[file:.agents/steering/project-overview.md]]
- Dev principles: #[[file:.agents/steering/dev-principles.md]]

## Requirements

### Requirement 1: Standalone stdio Entry Point per Brick

**User Story:** As a developer, I want to run any brick as an independent MCP server via `python -m factory.<brick>.mcp.server` so I can use it outside the aggregator.

#### Acceptance Criteria

1. EACH brick with a standalone entry point SHALL have a `mcp/server.py` module that creates a FastMCP server and calls `mcp.run()` (stdio transport).
2. THE entry point SHALL reuse the brick's existing `server.py::create_mcp_server()` factory — no logic duplication.
3. THE entry point SHALL be runnable via `python -m factory.<brick>.mcp.server` (module execution).
4. THE entry point SHALL be under 20 lines — it is a thin shell, not a new server.
5. THE brick SHALL continue to work inside the aggregator exactly as before — standalone is additive, not a replacement.

### Requirement 2: Adapter Selection via Environment Variables

**User Story:** As a developer, I want to control which backend adapter a standalone brick uses via env vars (e.g., `VERITAS_BACKEND=midway`).

#### Acceptance Criteria

1. STANDALONE bricks SHALL select their adapter using the same env var mechanism as the aggregator (e.g., `VERITAS_BACKEND`, `SIPP_BACKEND`).
2. NO new configuration mechanism SHALL be introduced — the existing `runtime.py` adapter selection is sufficient.
3. THE default backend for standalone mode SHALL be the same as aggregator mode (typically `memory`).

### Requirement 3: Split Topology in Kiro Power mcp.json

**User Story:** As a developer using the Kiro Power, I want a single `mcp.json` that configures companion-x (remote/local) plus standalone local servers for Midway-dependent bricks.

#### Acceptance Criteria

1. THE Kiro Power's `mcp.json` SHALL support configuring multiple MCP servers: companion-x (aggregator) plus standalone brick servers.
2. STANDALONE brick servers SHALL be configured as stdio commands: `uv run python -m factory.<brick>.mcp.server`.
3. EACH standalone server entry SHALL include the relevant backend env var (e.g., `VERITAS_BACKEND=midway`).
4. THE `mcp.json` SHALL document which servers are local vs remote with inline comments or a companion section in POWER.md.

### Requirement 4: General Pattern — Any Brick Can Run Standalone

**User Story:** As a platform developer, I want a documented, repeatable pattern so any brick can be made standalone in under 5 minutes.

#### Acceptance Criteria

1. THE standalone entry point pattern SHALL be documented as a recipe or in the brick anatomy steering file.
2. THE pattern SHALL be: create `mcp/server.py` (thin shell) + add `__main__.py` for `python -m` support.
3. THE pattern SHALL NOT require changes to the brick's runtime, adapters, or existing MCP tools.
4. ADDING a standalone entry point to a brick SHALL require fewer than 30 lines of new code total.

### Requirement 5: Future-Proof for Veritas MCP Server Swap

**User Story:** As a tech lead, I want to swap the local Veritas standalone server for the official Veritas MCP Server (ETA 4/17/2026) by changing only the `mcp.json` config.

#### Acceptance Criteria

1. THE split topology SHALL allow replacing a local standalone server with a remote/external MCP server by changing only `mcp.json` — no code changes.
2. THE Kiro Power's POWER.md SHALL document this swap path for Veritas.
