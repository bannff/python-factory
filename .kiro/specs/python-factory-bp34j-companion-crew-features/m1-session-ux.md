# M1 Session UX — Collapsible Session Deck

**Epic:** `python-factory-bp34j`  
**Milestone:** M1 — Persistent multi-session management  
**Selected:** Option B by owner on 2026-09-11

## Product intent

Keep persistent sessions discoverable without permanently reducing Companion-X's 440px minimum chat width. Sessions live in a compact deck above the transcript and collapse to a thin control strip.

## Layout contract

### Collapsed

- One 28px strip below the existing Chat header and above the persona selector.
- Left: `MessageSquare` icon, active session title, optional active-state dot.
- Right: session count, `ChevronDown`, and accessible “Show sessions” label.
- The transcript retains the remaining full sidebar width and height.

### Expanded

- Maximum height: 188px; the transcript remains visible below it.
- Header row: “Recent sessions”, search affordance, and `Plus` “New session”.
- Active session spans the full first row with accent-subtle background.
- Remaining recent sessions use a two-column grid when width permits and one column at narrow width.
- Each row has:
  1. Strong, single-line title.
  2. Muted single-line metadata: agent name plus relative activity/state.
  3. One status marker only.
- Archived sessions are excluded by default and available through an “Archived” affordance.
- Empty state: “No saved sessions yet. Start a chat to create one.”

## Interaction contract

- Use CopilotKit v2's native mutable `HttpAgent.threadId` field; pinned 1.53.0 exports no `useThreads`/`setThreadId` hook. Add no custom thread wire field.
- Selecting a row switches the active thread and collapses the deck.
- `Enter` and `Space` activate a focused row; arrow keys move between rows.
- “New session” selects a fresh CopilotKit thread ID and focuses the composer.
- Rename and archive use the typed Session MCP operations; stale revisions refresh rather than overwrite.
- The current thread remains selected across deck collapse/expand.
- Deck expansion is local presentation state, not Session domain state.

## Delivery-state contract

All three states use Lucide `Target`, keeping one visual family. Only server-authored state may render.

| State | Treatment | Copy |
|---|---|---|
| `written` | Muted, subtle pulse | “Steering…” |
| `consumed` | Accent label; one short entrance ring | “Steered into the running turn” |
| `requeued` | Muted, no celebration | “Turn ended before this applied — runs as its own message” |

Rules:

- An optimistic message without server state never renders consumed styling.
- `written` and `requeued` never use success color or entrance animation.
- Reconciliation targets the existing user message by standard AG-UI `id == send_id`.
- Revision updates are monotonic; stale events cannot move the UI backward.
- Status text occupies one stable slot above the bubble to avoid layout jumps.

## Visual language

- Reuse existing Companion-X tokens: `bg-card/10`, `border-border/50`, `bg-accent/20`, `text-muted-foreground`, and current radius/spacing scale.
- Use the existing Lucide dependency; no emoji icons or copied proprietary assets.
- Preserve the current translucent chat shell and persona strip.
- Motion uses the existing Framer Motion dependency and respects reduced-motion preferences.

## Data path

```text
Session MCP list/create/rename/archive
→ Companion-X session hook
→ CopilotKit `HttpAgent.threadId`
→ Session deck

Agent `agent_session_history`
→ owner-scoped Session MCP authorization
→ Agent-owned LangGraph checkpoint
→ CopilotKit messages before thread switch

session.steer CUSTOM event
→ AgentSubscriber.onCustomEvent
→ reconcile by send_id/revision
→ user-message status slot
```

## Acceptance evidence

- Unit tests: list/empty/archive/selection, keyboard navigation, thread switching, and delivery-state rendering.
- TypeScript check and available frontend lint.
- Screenshot: expanded deck with active and recent sessions.
- Screenshot: collapsed deck.
- Recording or reduced-motion equivalent: consumed transition and deck collapse.
- New-user review: discoverability, plain-language status, and session switching without prior instruction.
- Gate B UX reviewer receives real frames from the standard Companion-X launcher.
