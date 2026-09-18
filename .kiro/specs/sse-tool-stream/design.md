# Design: SSE Tool Call Stream

## Architecture

```
instrumentation.py  →  event_bus.py  →  events_sse.py  →  EventSource  →  timeline-view.tsx
```

**Deployment constraint:** MCP server and API base share a process in companion_x. In-process queue is valid. If they split, replace with Redis pub/sub.

## Key Files

| File | Change |
|------|--------|
| `components/mcp_utils/src/factory/mcp_utils/event_bus.py` | NEW — shared event bus |
| `components/mcp_utils/src/factory/mcp_utils/interface.py` | EXPORT `event_bus` |
| `bases/mcp_server/src/factory/mcp_server/runtime/instrumentation.py` | ADD publish in `_emit()` |
| `bases/api/src/factory/api/runtime/events_sse.py` | NEW — SSE endpoint |
| `bases/api/src/factory/api/runtime/adapters/rest.py` | ADD register call |
| `frontends/next-dashboard/lib/hooks/use-live-tool-stream.ts` | NEW |
| `frontends/next-dashboard/components/canvas/timeline-view.tsx` | MERGE + rename filter |
| `frontends/next-dashboard/components/canvas/timeline-chart.tsx` | FIX sort by timestamp |

## Event Shape

```json
{ "brick": "memory", "tool": "memory_store", "success": true, "latency_ms": 97.4, "ts": 1742262000.123 }
```

`ts` is `time.time()` (epoch seconds). Frontend converts: `ts * 1000`.

## Entry ID Scheme

`"live-sse-{Math.round(ts * 1000)}-{counter}"` — counter is a module-level int in the hook. Prevents same-ms collisions and duplicate entries on SSE reconnect (dedup by ID in the merge Set).

## Sync-safe Publish

`publish()` calls `queue.put_nowait()` directly — no `asyncio.create_task`. Safe from both sync and async call paths. Same pattern as `graph_sink.materialize()`.

## Reconnect

Endpoint tracks a monotonic `event_id` per connection, sends `id: {n}` with each event. On reconnect, client sends `Last-Event-ID: {n}`. Endpoint skips already-seen events for the current connection window.

## Frontend Buffer + Freeze

`useLiveToolStream` maintains `entries: TimelineEntry[]` (max 50, drop oldest). When any row is expanded (`frozen=true`), eviction pauses. On collapse, eviction resumes. Hook exposes `{ entries, connected, frozen, setFrozen }`.

## Chart Fix

`timeline-chart.tsx` sorts entries by `entry.timestamp` before bucketing so the x-axis is chronological regardless of merge order.

## "Recent" Filter

Renamed from "Live". Shows SSE buffer only. Pagination disabled for this filter — all 50 entries, newest first, with `AnimatePresence` slide-in. Other filters keep pagination.
