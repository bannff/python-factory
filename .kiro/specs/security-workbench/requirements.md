# Requirements: Companion X Security Workbench

## Introduction

Companion X is a security workbench — an IDE-like web application for agentic security work. Think Kiro, but purpose-built for security engineers who need to investigate applications, run threat models, scan code, execute pen-tests in sandboxes, and visualize infrastructure topology.

The current state is a single-page chat surface (post-Task 15 cleanup). The IDE layout was previously implemented but abandoned because the chat was hidden and the views were useless placeholders. This spec brings back the IDE layout — done right — with real content, working chat, and purpose-built security tooling.

### What Companion X IS

- A security workbench where agents do the heavy lifting (threat modeling, code scans, pen-tests, recon)
- An IDE-like layout: ActivityBar (left) | Canvas (center) | Chat (right, always visible)
- A real-time window into agent work — chain of thought, tool calls, findings, graphs — streamed via AG-UI/A2UI
- A universal MCP-driven UI — everything flows through the Companion X MCP server's progressive discovery
- A place to do ML work too — trigger evals, fine-tune models, build datasets

### What Companion X is NOT

- A VS Code clone (no file tree, no terminal unless needed)
- A blank chat page (the center canvas shows rich visualizations)
- A static dashboard (everything is agent-driven and real-time)

### Architecture Constraint

Zero Python changes (Requirement 8 from original spec still holds). The frontend consumes existing HTTP endpoints via Next.js Route Handlers that proxy to the API base. The Veritas MCP server is accessed through the Companion X MCP server's `call_brick_tool` progressive discovery pattern.

## Tech Stack (Same as next-dashboard — already installed)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | Next.js 15 (App Router) | Foundation, SSR/SSG, routing |
| Components | shadcn/ui | Accessible, composable UI primitives |
| Animations | Magic UI + Framer Motion | Border beam, number ticker, shimmer, text reveal, fade-in, slide-in |
| Icons | Lucide React | Consistent icon set (superset of Heroicons coverage) |
| Graph Viz | React Force Graph + Three.js | 3D force-directed graph for agent session visualization |
| Agent Chat | Vercel AI SDK (`ai` package) + custom AG-UI SSE hook | `useChat` / `useAGUIChat` consuming AG-UI SSE stream |
| Styling | Tailwind CSS v4 | Utility-first, matches shadcn/ui defaults |
| Code Display | react-syntax-highlighter + Prism | Syntax-highlighted code blocks (already installed) |
| Markdown | react-markdown + remark-gfm | Agent message rendering (to install) |

This is NOT a new project. It reshapes the existing `frontends/next-dashboard/` codebase from a single chat surface into an IDE-like workbench. All existing components (renderer, chat hooks, SSE, API proxy) are reused.

## Glossary

- **Veritas**: Internal app topology graph (Neo4j-backed). Exposes MCP tools for querying app resources, security posture, deployment chains, data flows.
- **AG-UI**: Agent-to-UI SSE protocol. 15 event types streaming agent chain of thought, tool calls, steps, state.
- **A2UI**: Agent-to-UI component protocol. Agents emit component payloads (cards, tables, graphs) that render inline.
- **Progressive Discovery**: MCP pattern where `list_bricks` → `get_brick_tools` → `call_brick_tool` lets clients discover capabilities without knowing all tools upfront.
- **Canvas**: The center panel of the IDE layout. Shows rich visualizations pushed by the agent or selected by the user.
- **ActivityBar**: The left icon rail. Contextual navigation for the current workflow.

## Requirements

### Requirement 1: IDE Layout — Three-Column Workbench

**User Story:** As a security engineer, I want an IDE-like layout with navigation on the left, a rich canvas in the center, and chat on the right — so I can drive agent work while seeing results in real time.

#### Acceptance Criteria

1. THE layout SHALL have three columns: ActivityBar (48px icon rail, left) | Canvas (flex-1, center) | ChatSidebar (380px, right).
2. THE ChatSidebar SHALL be visible by default and collapsible via a toggle button.
3. THE Canvas SHALL fill the remaining horizontal space and display the active view (graph, timeline, findings, etc.).
4. THE ActivityBar SHALL show contextual icons for available views: Investigation (magnifying glass), Graph (network nodes), Timeline (clock), Findings (shield), Evals (beaker), ML (brain), Settings (gear).
5. CLICKING an ActivityBar icon SHALL switch the Canvas to that view without affecting the chat state.
6. THE layout SHALL be responsive: on screens < 1024px, the ActivityBar collapses to a hamburger menu and the ChatSidebar becomes a slide-over panel.
7. ALL layout components SHALL stay under 200 LOC per file.

### Requirement 2: Chat Sidebar — Agent Command Center

**User Story:** As a user, I want a chat interface on the right side (like Kiro) where I talk to the agent and see streaming responses, tool calls, and step progress — so I can drive security work conversationally.

#### Acceptance Criteria

1. THE chat SHALL occupy the right sidebar (380px default width, resizable).
2. THE chat SHALL stream AG-UI events from `POST /ag-ui/run` showing: text messages (streaming), tool call cards (collapsible with args/result), step indicators, and error alerts.
3. THE chat SHALL render `CUSTOM` events with `name: "a2ui"` as inline component views using the existing ComponentTree renderer.
4. THE chat SHALL have a pinned input bar at the bottom with send/cancel/clear actions.
5. THE chat SHALL show an empty state with security-focused suggestion chips: "Scan app topology", "Run threat model", "Check security posture", "Search knowledge base".
6. THE chat SHALL render agent messages with markdown support (code blocks, tables, lists, links).
7. TOOL CALL cards SHALL show the tool name, a spinner while running, and expandable args/result JSON when complete.
8. THE chat SHALL auto-scroll to the latest message but allow the user to scroll up without being yanked back.

### Requirement 3: Canvas — Rich Visualization Surface

**User Story:** As a security engineer, I want the center canvas to show rich visualizations — graphs, timelines, findings tables, code diffs — pushed by the agent or selected from the ActivityBar.

#### Acceptance Criteria

1. THE Canvas SHALL support multiple view types switchable via ActivityBar: Graph, Timeline, Findings, Evals, ML, and a default Welcome view.
2. THE Canvas SHALL accept A2UI payloads pushed by the agent (via `CUSTOM` AG-UI events) and render them as the active view.
3. THE Canvas SHALL have a tab bar at the top showing open views, allowing the user to switch between them (like editor tabs in an IDE).
4. THE default Welcome view SHALL show system health (brick count, tool count, connection status) and quick-action cards for common workflows.
5. EACH Canvas view SHALL be a lazy-loaded component to keep initial bundle size small.
6. THE Canvas SHALL support full-screen mode (hiding ActivityBar and ChatSidebar) via a toggle.

### Requirement 4: Graph Visualization — Topology & Knowledge Graphs

**User Story:** As a security engineer, I want to see application topology (from Veritas) and knowledge graphs rendered as interactive 3D force-directed graphs with bloom effects — so I can visually explore infrastructure and relationships.

#### Acceptance Criteria

1. THE Graph view SHALL use React Force Graph 3D with Three.js for rendering.
2. THE Graph SHALL support bloom post-processing effects (UnrealBloomPass) for a glowing node aesthetic on dark backgrounds.
3. NODES SHALL be color-coded by type (e.g., Lambda=blue, S3=green, DynamoDB=orange, Pipeline=purple, IamRole=red) with labels.
4. EDGES SHALL show directional flow with animated particles.
5. THE Graph SHALL support zoom, pan, rotate, and click-to-focus-node interactions.
6. THE Graph SHALL accept data from two sources: (a) Veritas app topology (via `call_brick_tool` → Veritas MCP tools), (b) KB knowledge graph (via `graph_query` tool).
7. THE Graph SHALL update incrementally when the agent pushes new nodes/edges via A2UI `CUSTOM` events.
8. CLICKING a node SHALL show a detail panel with the node's properties (ARN, owner, account, security posture).

### Requirement 5: Timeline — Agent Workflow Visualization

**User Story:** As a user, I want to see the agent's workflow as a visual timeline — showing steps, tool calls, findings, and decisions — so I can follow what the agent is doing and review its work.

#### Acceptance Criteria

1. THE Timeline view SHALL render agent steps as a vertical timeline with timestamps.
2. EACH timeline entry SHALL show: step name, status (running/completed/failed), duration, and associated tool calls.
3. TOOL CALLS on the timeline SHALL be expandable to show arguments and results.
4. FINDINGS (security issues discovered) SHALL appear as highlighted entries with severity badges (critical/high/medium/low).
5. THE Timeline SHALL update in real-time as AG-UI `STEP_STARTED`/`STEP_FINISHED` and `TOOL_CALL_*` events arrive.
6. THE Timeline SHALL support filtering by event type (steps only, tool calls only, findings only).

### Requirement 6: Findings Panel — Security Results

**User Story:** As a security engineer, I want a dedicated findings panel that aggregates all security issues discovered by the agent — with severity, description, affected resources, and remediation suggestions.

#### Acceptance Criteria

1. THE Findings view SHALL display a sortable/filterable table of security findings.
2. EACH finding SHALL show: severity (critical/high/medium/low), title, affected resource, finding type (vulnerability, misconfiguration, exposure), and timestamp.
3. CLICKING a finding SHALL expand it to show full details: description, evidence, remediation steps, and related Veritas resources.
4. THE Findings view SHALL aggregate findings from the current chat session (extracted from agent tool call results).
5. THE Findings view SHALL support export (copy as JSON or markdown).
6. SEVERITY badges SHALL use consistent colors: critical=red, high=orange, medium=yellow, low=blue.

### Requirement 7: Evals & ML Views

**User Story:** As a user, I want to trigger evaluations, view eval results, and manage ML experiments from the workbench — so I can do benchmarking and fine-tuning work alongside security investigations.

#### Acceptance Criteria

1. THE Evals view SHALL list available eval suites (via `evals_list_suites` tool) and allow triggering runs.
2. THE Evals view SHALL display run results with metrics, pass/fail status, and comparison charts.
3. THE ML view SHALL list experiments (via `ml_list_experiments` tool) and show run metrics.
4. THE ML view SHALL support triggering fine-tuning jobs and displaying job status.
5. BOTH views SHALL render results using the existing ComponentTree renderer when the agent pushes A2UI payloads.

### Requirement 8: No Python Changes (Hard Constraint)

**User Story:** As a maintainer, I want the security workbench to work with zero changes to the Python codebase — so it's purely additive.

#### Acceptance Criteria

1. NO Python files SHALL be created or modified.
2. THE frontend SHALL consume only existing HTTP endpoints: `POST /ag-ui/run`, `POST /api/tools/{tool_name}`, `GET /api/tools`, `GET /api/health`.
3. Veritas MCP tools SHALL be accessed through the existing `call_brick_tool` progressive discovery pattern (the Veritas MCP server is already registered as a brick in the aggregator).
4. ALL new functionality SHALL be implemented in TypeScript/React under `frontends/next-dashboard/`.

### Requirement 9: File Hygiene & Repo Tenets

**User Story:** As a maintainer, I want all files under 200 LOC, clean imports, and updated docs — per repo tenets.

#### Acceptance Criteria

1. ALL TypeScript/TSX files SHALL stay under 200 lines.
2. DEAD code (zombie components from previous iterations) SHALL be removed before new code is added.
3. THE `frontends/next-dashboard/README.md` SHALL be updated to reflect the security workbench architecture.
4. Agent steering docs SHALL be updated after implementation to reflect the new layout and capabilities.
