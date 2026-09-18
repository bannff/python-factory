# Tasks: SSE Tool Call Stream

## Task 1: event_bus in mcp_utils component

- [ ] Create `components/mcp_utils/src/factory/mcp_utils/event_bus.py`
- [ ] Module-level `_subscribers: list[asyncio.Queue]` singleton
- [ ] `publish(event: dict)` — sync, uses `put_nowait()`, drops oldest on overflow
- [ ] `subscribe() -> AsyncGenerator` — yields events, removes queue on exit
- [ ] Export via `factory.mcp_utils.interface`
- [ ] Under 50 LOC

## Task 2: Wire instrumentation.py

- [ ] Import `event_bus` in `instrumentation.py`
- [ ] Call `event_bus.publish(...)` in `_emit()` with brick, tool, success, latency_ms, ts
- [ ] No exception propagation — wrap in try/except like graph_sink call

## Task 3: SSE endpoint

- [ ] Create `bases/api/src/factory/api/runtime/events_sse.py` (under 60 LOC)
- [ ] `GET /api/events/tools` → `StreamingResponse(text/event-stream)`
- [ ] Subscribe to event bus, yield `id: {n}\ndata: {json}\n\n`
- [ ] Keepalive `: ping` every 15s
- [ ] `Last-Event-ID` reconnect dedup
- [ ] Cleanup on disconnect
- [ ] Register in `rest.py` same pattern as `ag_ui_routes.py`

## Task 4: Frontend hook

- [ ] Create `frontends/next-dashboard/lib/hooks/use-live-tool-stream.ts`
- [ ] `EventSource("/api/events/tools")` with `Last-Event-ID` on reconnect
- [ ] Map to `TimelineEntry[]` with counter-based IDs and real `ts * 1000` timestamps
- [ ] Rolling 50-entry buffer with freeze-on-expand
- [ ] Close on unmount

## Task 5: Wire timeline-view.tsx

- [ ] Import `useLiveToolStream`
- [ ] Prepend SSE entries to merged list (sorted by timestamp)
- [ ] Rename "Live" filter to "Recent", disable pagination for it
- [ ] Animate new entries with `AnimatePresence` slide-in

## Task 6: Fix timeline-chart.tsx

- [ ] Sort entries by `entry.timestamp` before bucketing

## Task 7: Tests

- [ ] `bases/mcp_server/test/test_event_bus_properties.py` — 3 Hypothesis tests per requirements (note: subscriber must be registered before any publish calls in test setup)
- [ ] E2E: make 5 tool calls, verify SSE stream emits 5 events, timeline shows them
