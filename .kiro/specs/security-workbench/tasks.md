# Tasks: Companion X Security Workbench

## Track 1: Cleanup & Foundation

### Task 1.1: Remove dead chat-shell.tsx
- [ ] Delete `components/chat/chat-shell.tsx` (replaced by chat-sidebar.tsx in Track 2)
- [ ] Verify no other files import `ChatShell`

### Task 1.2: Install new dependencies
- [ ] Run `npm install react-markdown remark-gfm` in `frontends/next-dashboard/`
- [ ] Verify `package.json` updated

### Task 1.3: Add workbench types
- [ ] Create `lib/types/workbench.ts` with types: `CanvasView`, `CanvasTab`, `Finding`, `FindingSeverity`, `GraphNode`, `GraphLink`, `TimelineEntry`, `TimelineEntryType`
- [ ] Update `lib/types.ts` barrel to re-export workbench types

## Track 2: Layout Shell

### Task 2.1: Create ActivityBar component
- [ ] Create `components/layout/activity-bar.tsx`
- [ ] Vertical icon rail (48px wide) with Lucide icons: Search, Network, Clock, Shield, Beaker, Brain, Settings
- [ ] Active icon has gradient background (violet-to-indigo)
- [ ] Tooltip on hover
- [ ] Props: `activeView`, `onViewChange`
- [ ] Under 200 LOC

### Task 2.2: Create WorkbenchLayout component
- [ ] Create `components/layout/workbench-layout.tsx`
- [ ] Three-column flex: ActivityBar | Canvas | ChatSidebar
- [ ] Props: all AG-UI state from `useAGUIChat`, plus `activeView`, `chatOpen`, `onViewChange`, `onToggleChat`
- [ ] Under 200 LOC

### Task 2.3: Create useWorkbench hook
- [ ] Create `lib/hooks/use-workbench.ts`
- [ ] Manages: `activeView` (string), `chatOpen` (boolean), `canvasTabs` (CanvasTab[])
- [ ] Functions: `setActiveView`, `toggleChat`, `openTab`, `closeTab`, `setActiveTab`
- [ ] Under 200 LOC

### Task 2.4: Update page.tsx to use WorkbenchLayout
- [ ] Modify `app/page.tsx` to render `<WorkbenchLayout>` instead of `<ChatShell>`
- [ ] Wire `useAGUIChat` + `useWorkbench` hooks together
- [ ] Under 200 LOC

## Track 3: Chat Sidebar

### Task 3.1: Create ChatSidebar component
- [ ] Create `components/chat/chat-sidebar.tsx`
- [ ] Fixed width container with header ("Chat" title + collapse toggle)
- [ ] Renders `MessageList` + `ChatInput` inside
- [ ] Props: all chat state + `isOpen` + `onToggle`
- [ ] Under 200 LOC

### Task 3.2: Update MessageList for sidebar width
- [ ] Modify `components/chat/message-list.tsx`
- [ ] Remove `max-w-3xl mx-auto` centering (sidebar is narrow, content fills width)
- [ ] Keep all existing functionality (messages, tool calls, steps, A2UI inline views)

### Task 3.3: Update EmptyState with security suggestions
- [ ] Modify `components/chat/empty-state.tsx`
- [ ] Change suggestions to: "Scan app topology", "Run threat model", "Check security posture", "Search knowledge base", "List available tools", "Run eval suite"
- [ ] Keep the animated orb and Sparkles icon

### Task 3.4: Add markdown rendering to MessageBubble
- [ ] Modify `components/chat/message-bubble.tsx`
- [ ] Render assistant message content with `react-markdown` + `remark-gfm`
- [ ] Style markdown elements (code blocks, tables, links) with Tailwind
- [ ] Keep user messages as plain text
- [ ] Under 200 LOC

## Track 4: Canvas Container

### Task 4.1: Create Canvas component
- [ ] Create `components/canvas/canvas.tsx`
- [ ] Renders `CanvasTabs` at top + active view below
- [ ] Lazy-loads view components with `React.lazy` + `Suspense`
- [ ] Props: `activeView`, `tabs`, `onTabChange`, `onTabClose`, AG-UI state
- [ ] Under 200 LOC

### Task 4.2: Create CanvasTabs component
- [ ] Create `components/canvas/canvas-tabs.tsx`
- [ ] Horizontal tab bar with close buttons
- [ ] "Welcome" tab always present, not closable
- [ ] Active tab has gradient underline
- [ ] Under 200 LOC

### Task 4.3: Create WelcomeView
- [ ] Create `components/canvas/welcome-view.tsx`
- [ ] Shows: Companion X branding, connection status, brick/tool counts
- [ ] Quick-action cards: "Investigate App", "View Graph", "Run Eval"
- [ ] Uses `getHealth` API for status data
- [ ] Under 200 LOC

## Track 5: Graph Visualization

### Task 5.1: Create GraphView component
- [ ] Create `components/canvas/graph-view.tsx`
- [ ] Lazy-load `react-force-graph-3d`
- [ ] Configure Three.js bloom post-processing (UnrealBloomPass)
- [ ] Dark background, glowing nodes, animated edge particles
- [ ] Props: `nodes`, `links`, `onNodeClick`
- [ ] Under 200 LOC

### Task 5.2: Create GraphControls component
- [ ] Create `components/canvas/graph-controls.tsx`
- [ ] Toolbar: zoom in/out, 2D/3D toggle, node type filter checkboxes
- [ ] Search box to find and focus a node
- [ ] Legend showing node type → color mapping
- [ ] Under 200 LOC

### Task 5.3: Create useGraphData hook
- [ ] Create `lib/hooks/use-graph-data.ts`
- [ ] Fetches graph data via `POST /api/tools/{tool_name}`
- [ ] Two modes: Veritas topology (`get_app_topology`) and KB graph (`graph_query`)
- [ ] Transforms API response to `{ nodes: GraphNode[], links: GraphLink[] }` format
- [ ] Supports incremental updates from A2UI pushes
- [ ] Under 200 LOC

## Track 6: Timeline View

### Task 6.1: Create TimelineView component
- [ ] Create `components/canvas/timeline-view.tsx`
- [ ] Vertical timeline with center line
- [ ] Filter chips at top: All, Steps, Tool Calls, Findings
- [ ] Renders `TimelineEntry` components with Framer Motion stagger animation
- [ ] Props: `steps`, `toolCalls`, `findings`
- [ ] Under 200 LOC

### Task 6.2: Create TimelineEntry component
- [ ] Create `components/canvas/timeline-entry.tsx`
- [ ] Single timeline entry: icon, title, timestamp, duration, status badge
- [ ] Expandable on click (show tool args/result or finding details)
- [ ] Color-coded: steps=blue, tools=violet, findings=severity color
- [ ] Under 200 LOC

## Track 7: Findings Panel

### Task 7.1: Create useFindings hook
- [ ] Create `lib/hooks/use-findings.ts`
- [ ] Watches `toolCalls` from `useAGUIChat`
- [ ] Extracts findings from `security_*` tool results and Veritas security posture results
- [ ] Normalizes into `Finding[]` type
- [ ] Under 200 LOC

### Task 7.2: Create FindingsView component
- [ ] Create `components/canvas/findings-view.tsx`
- [ ] Summary bar: severity counts with colored badges
- [ ] Sortable table: Severity, Title, Resource, Type, Time
- [ ] Filter by severity
- [ ] Click row to expand `FindingDetail`
- [ ] Under 200 LOC

### Task 7.3: Create FindingDetail component
- [ ] Create `components/canvas/finding-detail.tsx`
- [ ] Full finding details: description, evidence, remediation, related resources
- [ ] "Copy as Markdown" button
- [ ] Syntax-highlighted code blocks for evidence
- [ ] Under 200 LOC

## Track 8: Evals & ML Views

### Task 8.1: Create EvalsView component
- [ ] Create `components/canvas/evals-view.tsx`
- [ ] Lists eval suites with run counts
- [ ] "Run" button triggers eval via API
- [ ] Results display with metrics and pass/fail badges
- [ ] Under 200 LOC

### Task 8.2: Create MLView component
- [ ] Create `components/canvas/ml-view.tsx`
- [ ] Lists experiments with metrics
- [ ] Fine-tuning job cards with progress
- [ ] Under 200 LOC

## Track 9: A2UI Canvas Routing

### Task 9.1: Update ag-ui-event-processor for canvas targeting
- [ ] Modify `lib/hooks/ag-ui-event-processor.ts`
- [ ] When processing `CUSTOM` events with `name: "a2ui"`, check for `target` field
- [ ] Store targeted payloads in separate state fields: `_a2ui_graph`, `_a2ui_timeline`, `_a2ui_findings`, `_a2ui_canvas`
- [ ] Keep existing `_a2ui` field for untargeted payloads (inline chat rendering)
- [ ] Under 200 LOC

### Task 9.2: Wire canvas views to A2UI state
- [ ] Update `components/canvas/canvas.tsx` to pass A2UI state to child views
- [ ] GraphView reads `agentState._a2ui_graph` for pushed graph data
- [ ] TimelineView reads `agentState._a2ui_timeline` for pushed entries
- [ ] FindingsView reads `agentState._a2ui_findings` for pushed findings
- [ ] Generic canvas tab reads `agentState._a2ui_canvas` for arbitrary A2UI payloads

## Track 10: Polish & Docs

### Task 10.1: Add glass morphism and animations
- [ ] Apply `backdrop-blur-md bg-card/30 border-border/50` to ActivityBar, Canvas tabs, ChatSidebar header
- [ ] Add Framer Motion `layoutId` transitions when switching canvas views
- [ ] Add spring animations to ActivityBar icon hover states

### Task 10.2: Update README.md
- [ ] Rewrite `frontends/next-dashboard/README.md` to describe the security workbench architecture
- [ ] Document the three-column layout, canvas views, and AG-UI/A2UI data flow
- [ ] Update architecture diagram

### Task 10.3: Update agent steering docs
- [ ] Update `.agents/steering/project-overview.md` Companion X section to reflect workbench layout
- [ ] Update `.agents/steering/brick-inventory.md` if needed
- [ ] Ensure docs match the implemented reality

### Task 10.4: Verify build and guardian check
- [ ] Run `npm run build` in `frontends/next-dashboard/` — must succeed with zero errors
- [ ] Run `foreman_guardian_check` — must pass 5/5
- [ ] Verify all new files are under 200 LOC
