# Requirements: Companion-X Kiro Power

## Introduction

Companion-X is a progressive-discovery MCP server with 28+ bricks, each exposing full MCP primitives (tools, resources, prompts). Packaging it as a Kiro Power solves the discoverability problem: without keyword-triggered activation, agents don't know the bricks exist behind the 9 meta-tools.

The Power is NOT security-specific. It's the general-purpose Companion-X platform — memory, knowledge base, graph, security, auth, events, workflow, and everything else.

## Related

- Existing MCP config: #[[file:.kiro/settings/mcp.json]]
- Architecture: #[[file:.agents/steering/project-overview.md]]
- Power Builder docs: Kiro Power `power-builder` (activate for structure/format guidance)
- Discussion context: comp-x v2 replaces a-mem as agent memory; Power solves progressive discovery gap

## Requirements

### Requirement 1: Single Guided MCP Power

**User Story:** As a developer installing Companion-X, I want a single Kiro Power that gives me access to all bricks with keyword-triggered discovery.

#### Acceptance Criteria

1. THE Power SHALL be a Guided MCP Power with `POWER.md` + `mcp.json`.
2. THE Power SHALL declare broad keywords covering all brick domains: `memory`, `knowledge`, `graph`, `security`, `auth`, `cache`, `events`, `workflow`, `agent`, `evals`, `ml`, `companion-x`, `mcp`.
3. THE Power SHALL support both local (stdio) and remote (AgentCore URL) MCP server configurations.
4. THE `POWER.md` SHALL be under 200 lines — crisp, not verbose.

### Requirement 2: Crisp Brick Catalog in POWER.md

**User Story:** As an agent activating this Power, I want to immediately see what each brick does so I know which one to drill into.

#### Acceptance Criteria

1. THE `POWER.md` SHALL contain a brick catalog table: brick name | one-line description | has prompts | has resources.
2. EACH brick description SHALL be one sentence max (e.g., "Store and retrieve agent memories with semantic search and graph traversal").
3. THE `POWER.md` SHALL explain the progressive discovery flow: `list_bricks` → `get_brick_tools(name)` → `call_brick_tool(name, tool, args)`.
4. THE `POWER.md` SHALL NOT list individual tool schemas — that's what `get_brick_tools` is for.

### Requirement 3: MCP Server Configuration

**User Story:** As a developer, I want sensible defaults so the server works immediately after install.

#### Acceptance Criteria

1. THE `mcp.json` SHALL configure the companion-x MCP server via `uvx` or `uv run`.
2. THE `mcp.json` SHALL include placeholder env vars for Neo4j, AWS region, and backend selectors.
3. THE `autoApprove` list SHALL include all 9 progressive discovery meta-tools plus brick health checks.
4. THE `mcp.json` SHALL document both local and remote (AgentCore URL) connection options.

### Requirement 4: Optional Steering Files for Deep Workflows

**User Story:** As an agent working on a specific domain (security review, memory pipeline, ML experiment), I want deeper workflow guidance loaded on demand.

#### Acceptance Criteria

1. THE Power MAY include `steering/` files for high-value brick workflows (security review, memory, knowledge base, evals).
2. EACH steering file SHALL be under 100 lines — workflow steps with tool names, not prose.
3. THE `POWER.md` SHALL list available steering files with one-line descriptions.
4. Steering files are optional for v1 — the brick catalog in POWER.md is the MVP.

### Requirement 5: Distribution

**User Story:** As a platform team, I want the Power installable from a local directory or git repo.

#### Acceptance Criteria

1. THE Power SHALL be a directory installable via `~/.kiro/powers/` or Kiro Powers UI.
2. THE Power SHALL work without the python-factory monorepo — it connects to a deployed MCP server.
3. THE Power SHALL include a `MCP Config Placeholders` section documenting every env var that needs replacing.
