# Requirements: SSE Tool Call Stream

## Introduction

Every MCP tool call through the companion-x gateway should appear in the Timeline UI in real-time — whether the caller is the in-app agent, Kiro IDE, or any external MCP client. Today the timeline only shows historical data (graph ToolInvocation nodes). This spec adds a live SSE stream so any caller's tool invocations appear within milliseconds.

**Deployment assumption:** The MCP server base and API base run in the same process (companion_x project). The in-process event bus is valid for this deployment. If they ever split, replace the bus with Redis pub/sub.

## Related

- Bead: `python-factory-grl`
- Instrumentation hook: `bases/mcp_server/src/factory/mcp_server/runtime/instrumentation.py`
- API routes pattern: `bases/api/src/factory/api/runtime/adapters/rest.py` → `ag_ui_routes.py`
- Timeline hook: `frontends/next-dashboard/lib/hooks/use-timeline-data.ts`
- Timeline view: `frontends/next-dashboard/components/canvas/timeline-view.tsx`

## Requirements

### Requirement 1: In-process event bus in the MCP server base

**User Story:** As the gateway, I want to publish a tool call event after every dispatch so any subscriber can consume it.

#### Acceptance Criteria

1. A module `components/mcp_utils/src/factory/mcp_utils/event_bus.py` SHALL expose `publish(event: dict)` (sync) and `subscribe() -> AsyncGenerator`. It SHALL be exported via `factory.mcp_utils.interface` so both the MCP server base and API base can import it without cross-base imports.
2. `publish()` SHALL use `put_nowait()` directly — NOT `asyncio.create_task` — so it is safe to call from both sync and async contexts.
3. The bus SHALL use an `asyncio.Queue` per subscriber with a max size of 100 (drop oldest on overflow).
4. `instrumentation.py` SHALL call `event_bus.publish({"brick": ..., "tool": ..., "success": ..., "latency_ms": ..., "ts": time.time()})` in `_emit()`, same fire-and-forget pattern as `graph_sink.materialize()`.
5. The bus SHALL be a module-level singleton.
6. Each file SHALL be under 200 LOC.

### Requirement 2: SSE endpoint in the API base

**User Story:** As the frontend, I want a `/api/events/tools` SSE endpoint that streams tool call events.

#### Acceptance Criteria

1. The endpoint SHALL live at `bases/api/src/factory/api/runtime/events_sse.py` and be registered via `rest.py` using the same pattern as `ag_ui_routes.py`.
2. `GET /api/events/tools` SHALL return `Content-Type: text/event-stream`.
3. Each event SHALL be yielded verbatim from the bus as `data: {json}\n\n` — zero transformation in the base.
4. The endpoint SHALL send a keepalive comment (`: ping`) every 15 seconds.
5. On client disconnect, the subscription SHALL be cleaned up (no leaked queues).
6. The endpoint SHALL support `Last-Event-ID` header for reconnect deduplication.
7. The endpoint SHALL be under 60 LOC.

### Requirement 3: Frontend SSE hook

**User Story:** As the Timeline view, I want live tool call events prepended to the entry list in real-time.

#### Acceptance Criteria

1. A hook `use-live-tool-stream.ts` SHALL connect to `/api/events/tools` via `EventSource`.
2. Each received event SHALL be mapped to a `TimelineEntry` with `id: "live-sse-{Math.round(ts * 1000)}-{counter}"` (counter prevents same-ms collisions), `type: "tool_call"`, `status: success ? "completed" : "failed"`, `timestamp: ts * 1000` (real epoch ms from server).
3. The hook SHALL maintain a rolling buffer of the last 50 live entries (drop oldest).
4. The hook SHALL expose a `frozen` state: when a row is expanded, the buffer SHALL stop evicting entries until the row is collapsed.
5. On unmount, the `EventSource` SHALL be closed.
6. On reconnect, the hook SHALL send `Last-Event-ID` to avoid duplicate entries.

### Requirement 4: Timeline "Recent" filter and live-safe list

**User Story:** As a user watching the Timeline, I want to see recent tool calls without the list shifting under me.

#### Acceptance Criteria

1. The "Live" filter SHALL be renamed "Recent" — it shows the rolling SSE buffer (last 50 entries).
2. When "Recent" is selected, pagination SHALL be disabled — the list shows all 50 entries, newest first, with smooth scroll.
3. New entries SHALL animate in at the top (framer-motion `AnimatePresence` with `initial={{ opacity: 0, y: -8 }}`).
4. Animation SHALL only fire for entries with IDs not previously seen (stable identity via the counter-based ID).
5. The live count in the header SHALL update in real-time and show a pulsing green dot when SSE is connected.
6. The chart SHALL sort entries by `timestamp` before bucketing so the time axis is correct.

## QA Tests

### Hypothesis property tests (`bases/mcp_server/test/test_event_bus_properties.py`)

```python
@given(st.lists(st.fixed_dictionaries({
    "brick": st.text(min_size=1, max_size=50),
    "tool": st.text(min_size=1, max_size=50),
    "success": st.booleans(),
    "latency_ms": st.floats(min_value=0, max_value=1e6),
    "ts": st.floats(min_value=0),
}), min_size=1, max_size=100))
def test_bus_delivers_all_events_under_capacity(events):
    # Invariant: all events published to a fresh bus are received by subscriber

@given(st.integers(min_value=101, max_value=500))
def test_bus_drops_oldest_on_overflow(n_events):
    # Invariant: subscriber receives exactly 100 events when n > 100 published

@given(st.booleans())
def test_publish_safe_from_sync_context(in_async):
    # Invariant: publish() never raises regardless of event loop state
```

### Recipe E2E scenario

```
GIVEN the companion-x MCP server is running
WHEN 5 tool calls are made via call_brick_tool (any brick)
THEN GET /api/events/tools SSE stream emits 5 events within 2 seconds
AND each event contains brick, tool, success, latency_ms, ts fields
AND the Timeline UI "Recent" filter shows 5 new entries with real timestamps
AND no duplicate entries appear on SSE reconnect
```
