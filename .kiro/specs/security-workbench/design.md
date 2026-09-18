# Design: Companion X Security Workbench

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         Browser (localhost:3001)                  │
│                                                                  │
│  ┌──────────┐  ┌──────────────────────────┐  ┌───────────────┐  │
│  │ActivityBar│  │        Canvas            │  │  ChatSidebar  │  │
│  │  48px     │  │    (flex-1)              │  │   380px       │  │
│  │           │  │                          │  │               │  │
│  │ 🔍 Invest │  │  ┌─────────────────────┐ │  │  Messages     │  │
│  │ 🕸 Graph  │  │  │  Tab Bar            │ │  │  Tool Cards   │  │
│  │ ⏱ Timeline│  │  ├─────────────────────┤ │  │  Steps        │  │
│  │ 🛡 Findings│  │  │                     │ │  │  A2UI Views   │  │
│  │ 🧪 Evals  │  │  │  Active View        │ │  │               │  │
│  │ 🧠 ML     │  │  │  (Graph/Timeline/   │ │  │               │  │
│  │ ⚙ Settings│  │  │   Findings/Welcome) │ │  │  ┌─────────┐ │  │
│  │           │  │  │                     │ │  │  │  Input  │ │  │
│  └──────────┘  │  └─────────────────────┘ │  │  └─────────┘ │  │
│                 └──────────────────────────┘  └───────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                        Topbar (48px)                         ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
         │                                          │
         │  Route Handlers (proxy)                  │  AG-UI SSE
         ▼                                          ▼
┌──────────────────────────────────────────────────────────────────┐
│                    API Base (port 8001)                           │
│  POST /api/tools/{name}  GET /api/tools  GET /api/health         │
│  POST /ag-ui/run (SSE)                                           │
└──────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    MCP Aggregator                                 │
│  list_bricks → get_brick_tools → call_brick_tool                 │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐        │
│  │security│ │veritas │ │ graph  │ │sandbox │ │ evals  │ ...     │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘        │
└──────────────────────────────────────────────────────────────────┘
```

## Component Design

### Design 1: Workbench Layout Shell

Replaces the current single-page chat layout with a three-column IDE layout.

**File:** `app/page.tsx`
- Renders `<WorkbenchLayout>` instead of `<ChatShell>` directly
- `useAGUIChat` hook stays at this level, passes state down to both ChatSidebar and Canvas

**File:** `components/layout/workbench-layout.tsx` (NEW)
- Three-column flex layout: `<ActivityBar>` | `<Canvas>` | `<ChatSidebar>`
- Manages `activeView` state (which Canvas view is shown)
- Manages `chatOpen` state (sidebar visibility toggle)
- Manages `canvasTabs` state (open tabs in the canvas)

**File:** `components/layout/activity-bar.tsx` (NEW)
- Vertical icon rail, 48px wide
- Icons: Search, Network, Clock, Shield, Beaker, Brain, Settings
- Active icon highlighted with gradient background
- Tooltip on hover showing view name

**Reuses:** `components/layout/topbar.tsx` (existing, no changes needed)

### Design 2: Chat Sidebar

Refactors the existing `ChatShell` into a sidebar-shaped component.

**File:** `components/chat/chat-sidebar.tsx` (NEW)
- Wraps existing `MessageList` + `ChatInput` in a sidebar container
- Fixed width (380px), full height, border-left separator
- Header with "Chat" title and collapse toggle button
- Passes all AG-UI state through from parent

**Modifications to existing files:**
- `chat-shell.tsx` — DELETE (replaced by chat-sidebar.tsx)
- `message-list.tsx` — Remove `max-w-3xl mx-auto` centering (sidebar is narrow, content fills width)
- `empty-state.tsx` — Update suggestions to security-focused prompts
- `message-bubble.tsx` — Add markdown rendering support (react-markdown + remark-gfm)

### Design 3: Canvas Container

The center panel that hosts switchable views.

**File:** `components/canvas/canvas.tsx` (NEW)
- Tab bar at top showing open views
- Renders the active view component below the tab bar
- Accepts A2UI payloads from AG-UI events and can open them as new tabs

**File:** `components/canvas/canvas-tabs.tsx` (NEW)
- Horizontal tab bar with close buttons
- "Welcome" tab is always present and cannot be closed
- Active tab has a gradient underline indicator

**File:** `components/canvas/welcome-view.tsx` (NEW)
- Default canvas view when no specific view is active
- Shows: connection status card, brick count, tool count, quick-action cards
- Quick actions: "Investigate App" (opens chat with prompt), "View Graph" (switches to graph), "Run Eval" (switches to evals)
- Uses existing `getHealth` API call for status data

### Design 4: Graph Visualization

3D force-directed graph with bloom effects for Veritas topology and KB graphs.

**File:** `components/canvas/graph-view.tsx` (NEW)
- Wrapper that lazy-loads React Force Graph 3D (heavy dep, code-split)
- Accepts `nodes` and `edges` arrays as props
- Configures Three.js bloom post-processing (UnrealBloomPass)
- Dark background, glowing nodes, animated edge particles

**File:** `components/canvas/graph-controls.tsx` (NEW)
- Toolbar above the graph: zoom controls, layout toggle (3D/2D), node filter by type
- Search box to find and focus a specific node
- Legend showing node type → color mapping

**File:** `lib/hooks/use-graph-data.ts` (NEW)
- Hook that fetches graph data from the API
- Two modes: (a) Veritas topology via `call_brick_tool` → `get_app_topology`, (b) KB graph via `graph_query`
- Transforms API response into React Force Graph format: `{ nodes: [{id, name, type, color, val}], links: [{source, target}] }`
- Supports incremental updates when agent pushes new data

**Node color scheme:**
| Type | Color | Hex |
|------|-------|-----|
| Lambda | Blue | #3b82f6 |
| S3 | Green | #22c55e |
| DynamoDB | Orange | #f97316 |
| Pipeline | Purple | #a855f7 |
| IamRole | Red | #ef4444 |
| EC2 | Cyan | #06b6d4 |
| RDS | Yellow | #eab308 |
| SNS/SQS | Pink | #ec4899 |
| Default | Gray | #6b7280 |

### Design 5: Timeline View

Vertical timeline showing agent workflow steps, tool calls, and findings.

**File:** `components/canvas/timeline-view.tsx` (NEW)
- Vertical timeline with a center line and alternating left/right entries
- Each entry: icon (step/tool/finding), title, timestamp, duration badge, status indicator
- Entries animate in with Framer Motion stagger
- Filterable by type via chips at the top

**File:** `components/canvas/timeline-entry.tsx` (NEW)
- Single timeline entry component
- Expandable: click to show tool call args/result or finding details
- Color-coded by type: steps=blue, tool calls=violet, findings=red/orange/yellow

**Data source:** Reads from the same `steps` and `toolCalls` arrays from `useAGUIChat` hook. Findings are extracted from tool call results that match security tool patterns (e.g., `security_*` tool results).

### Design 6: Findings Panel

Aggregated security findings from the current session.

**File:** `components/canvas/findings-view.tsx` (NEW)
- Table view with columns: Severity, Title, Resource, Type, Time
- Sortable by severity (default) or time
- Filterable by severity level
- Summary bar at top: counts by severity with colored badges

**File:** `components/canvas/finding-detail.tsx` (NEW)
- Expanded view when a finding row is clicked
- Shows: full description, evidence (code snippets, config excerpts), remediation steps, related Veritas resources
- "Copy as Markdown" button for export

**File:** `lib/hooks/use-findings.ts` (NEW)
- Hook that extracts findings from tool call results
- Watches `toolCalls` array from `useAGUIChat`
- Parses results from `security_*` tools, `get_security_posture`, `get_app_security_profile`
- Normalizes into `Finding` type: `{ id, severity, title, resource, type, description, evidence, remediation, timestamp }`

### Design 7: Evals View

Evaluation suite management and results display.

**File:** `components/canvas/evals-view.tsx` (NEW)
- Lists eval suites with run counts and last run status
- "Run" button triggers eval via `call_brick_tool` → `evals_evaluate`
- Results display: metrics table, pass/fail badges, comparison sparklines
- Uses existing ComponentTree renderer for A2UI payloads from eval results

### Design 8: ML View

Machine learning experiment tracking and fine-tuning.

**File:** `components/canvas/ml-view.tsx` (NEW)
- Lists experiments with run counts and metrics
- "New Fine-tune" button opens a form (model, dataset, hyperparams)
- Job status cards with progress bars
- Uses existing ComponentTree renderer for A2UI payloads

### Design 9: State Management & Data Flow

How AG-UI events flow through the workbench.

```
page.tsx (useAGUIChat)
  ├── ChatSidebar (messages, toolCalls, steps, agentState)
  ├── Canvas
  │   ├── GraphView (reads agentState._a2ui for graph pushes)
  │   ├── TimelineView (reads steps, toolCalls)
  │   ├── FindingsView (reads toolCalls, extracts findings)
  │   ├── EvalsView (reads toolCalls for eval results)
  │   └── MLView (reads toolCalls for ML results)
  └── ActivityBar (activeView setter)
```

**Key principle:** `useAGUIChat` remains the single source of truth. All canvas views read from the same state. No duplicate SSE connections. The agent pushes data via AG-UI events, and each view interprets the relevant subset.

**A2UI Canvas Push:** When the agent emits a `CUSTOM` event with `name: "a2ui"`, the workbench checks the payload's `target` field:
- `target: "graph"` → Opens/updates the Graph view with new nodes/edges
- `target: "timeline"` → Adds entries to the Timeline
- `target: "findings"` → Adds findings to the Findings panel
- `target: "canvas"` → Opens a new generic tab with ComponentTree rendering
- No target → Renders inline in the chat (existing behavior)

## File Structure (New/Modified)

```
frontends/next-dashboard/
├── app/
│   ├── page.tsx                          # MODIFY — render WorkbenchLayout
│   └── layout.tsx                        # KEEP (no changes)
├── components/
│   ├── layout/
│   │   ├── topbar.tsx                    # KEEP
│   │   ├── theme-toggle.tsx              # KEEP
│   │   ├── workbench-layout.tsx          # NEW
│   │   └── activity-bar.tsx              # NEW
│   ├── chat/
│   │   ├── chat-sidebar.tsx              # NEW (replaces chat-shell.tsx)
│   │   ├── chat-shell.tsx                # DELETE
│   │   ├── chat-input.tsx                # KEEP
│   │   ├── message-list.tsx              # MODIFY (remove centering)
│   │   ├── message-bubble.tsx            # MODIFY (add markdown)
│   │   ├── empty-state.tsx               # MODIFY (security suggestions)
│   │   ├── tool-call-card.tsx            # KEEP
│   │   ├── inline-view.tsx               # KEEP
│   │   ├── thinking-indicator.tsx        # KEEP
│   │   └── step-indicator.tsx            # KEEP
│   ├── canvas/
│   │   ├── canvas.tsx                    # NEW
│   │   ├── canvas-tabs.tsx               # NEW
│   │   ├── welcome-view.tsx              # NEW
│   │   ├── graph-view.tsx                # NEW
│   │   ├── graph-controls.tsx            # NEW
│   │   ├── timeline-view.tsx             # NEW
│   │   ├── timeline-entry.tsx            # NEW
│   │   ├── findings-view.tsx             # NEW
│   │   ├── finding-detail.tsx            # NEW
│   │   ├── evals-view.tsx                # NEW
│   │   └── ml-view.tsx                   # NEW
│   ├── renderer/                         # KEEP (all existing files)
│   └── ui/                               # KEEP (all existing shadcn components)
├── lib/
│   ├── hooks/
│   │   ├── use-ag-ui-chat.ts             # KEEP
│   │   ├── ag-ui-event-processor.ts      # MODIFY (add target routing for A2UI)
│   │   ├── use-graph-data.ts             # NEW
│   │   ├── use-findings.ts               # NEW
│   │   └── use-workbench.ts              # NEW (activeView, tabs, sidebar state)
│   ├── types/
│   │   ├── ag-ui.ts                      # KEEP
│   │   ├── chat.ts                       # KEEP
│   │   └── workbench.ts                  # NEW (Finding, GraphNode, TimelineEntry types)
│   ├── api.ts                            # KEEP
│   ├── proxy.ts                          # KEEP
│   ├── sse.ts                            # KEEP
│   ├── types.ts                          # MODIFY (re-export workbench types)
│   └── utils.ts                          # KEEP
└── README.md                             # MODIFY
```

## Dependencies

Everything from the original next-dashboard spec is already installed: Next.js 15, shadcn/ui, Magic UI, Framer Motion, Lucide React, React Force Graph 3D, Three.js, Vercel AI SDK, react-syntax-highlighter, Tailwind CSS v4.

Only 2 new packages needed:

| Package | Purpose |
|---------|---------|
| `react-markdown` | Markdown rendering in agent messages |
| `remark-gfm` | GitHub-flavored markdown (tables, strikethrough) |
