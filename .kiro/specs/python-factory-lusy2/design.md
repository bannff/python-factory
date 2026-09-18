# Design — Live tool-call visibility inside spawned sub-agents

**bd:** `python-factory-lusy2` (P2 parent) → children `python-factory-ntyz7` (core, P1), `python-factory-a60nq` (concurrency verify, P2)
**Phase:** Design verdict (Opus planning). Implementer runs on Sonnet.
**Verdicts:** strands-expert `78d4128f` APPROVE_WITH_NOTES · meta-architect `4748fec9` APPROVE_WITH_AMENDMENTS (ratifies `78d4128f`, extends czpw.1 `dbae0646`)
**Governing tenet:** SDK-First — no bespoke event bus, no new FE framework code, extend the G2 dispatch, cite SDK/dispatcher source.

## Overview

The chat agent has four native async-generator `@tool`s that spawn sub-agents — `spawn_subagent`, `spawn_swarm`, `spawn_graph`, `spawn_registered_graph` (`components/agent/src/factory/agent/runtime/adapters/strands_*_spawn.py`). All four build their specialist `Agent`s through **one chokepoint**: `_build_specialist(cfg)` in `strands_subagent_spawn.py` (`spawn_registered_graph` routes `_build_node_agent → _build_specialist`).

A live `spawn_swarm(security-analyst, code-scanner)` was driven on the running dashboard (`:3000` UI / `:8000` API). Evidence in `.agents/.issues/lusy2-0{0..3}-*.png`:

- Sub-agent **text + reasoning** stream inline correctly (the existing G2 branch works).
- Sub-agent **tool-call STARTS** surface as pills (`graph_query`, `graph_get_recent_findings`, `graph_list_recent_tool_invocations`, `graph_get_entity_context`, `kb_search`, `handoff_to_agent`).
- **Every pill is stuck on "Running" forever.** The `TOOL_CALL_END` + `TOOL_CALL_RESULT` half of the canonical AG-UI pair never fires from inside a sub-agent.

That spinning pill is the whole bug. The user can't see what the specialist actually did, tool by tool. The goal: when any spawned agent (single, swarm node, or graph node) calls a tool, the parent chat surfaces the full tool-call lifecycle so the pill resolves Running → Done with a result — Kiro-style transparency.

### What Strands actually emits (SDK source, not assumptions)

Verified against installed `strands-agents 1.40` (`.venv/lib/python3.13/site-packages/strands`):

| Fact | Source | Consequence |
|---|---|---|
| `Agent.stream_async` yields `event.as_dict()` **only** for `is_callback_event=True` | `agent/agent.py:861` | The spawn `@tool`'s `async for` only sees callback events |
| `ToolUseStreamEvent` is a callback (`len(keys)>0`) | `types/_events.py:135,145` | Sub-agent tool **STARTS + ARGS already reach the wire** via the existing G2 recursion → `tool_use_stream` branch → `ToolCallDeltaEvent` |
| `ToolResultEvent.is_callback_event = False` | `types/_events.py:305` | **The result body is filtered before the spawn tool's loop sees it** — this is the gap |
| Spawned specialists have **no `AGUIBridgePlugin`** | `strands_subagent_spawn.py::_build_specialist` (parent-only attach in `strands_mcp_chat.py::_attach_plugins`) | Nothing pushes the sub-agent's END+RESULT |
| `swarm.py:865` / `graph.py:913` call `node.executor.stream_async()` which filters `is_callback_event` **before** wrapping as `MultiAgentNodeStreamEvent` | `multiagent/swarm.py:865-867`, `multiagent/graph.py:913-915` | The result never rides `multiagent_node_stream` either |
| `@tool` `agent` param is injected from `invocation_state["agent"]` = the **parent** chat agent (outer depth), and is **excluded from the LLM JSON schema** | `tools/decorator.py:~209` (`_is_special_parameter` → `{self,cls,agent}`), `:~186` (`_create_input_model` skips it), `:410-412` (`_inject_agent`) | The spawn tool can reach the parent's queue via `agent._chat_stream_queue` with zero schema pollution |

**Conclusion:** the only missing signal is the END+RESULT pair, and the only SDK-idiomatic way to produce it is a HookProvider on the **sub-agent's own registry** (`AfterToolCallEvent` fires there during `node.executor.stream_async`). A Swarm/Graph-level HookProvider does **not** see inner tool events — it owns its own registry (`swarm.py:296` / `graph.py:465`) that fires only `Before/AfterNodeCallEvent`.

## Architecture

**Chosen delivery channel: inline `TOOL_CALL_START` / `TOOL_CALL_END` / `TOOL_CALL_RESULT` on the existing chat-stream rail. NOT carrier #3 ACTIVITY.**

Why this carrier:
- The sub-agent tool STARTS already flow on this rail (G2). The fix completes the pair on the same rail — pills flip Running → Done. Zero new wire vocabulary.
- The mapper `ag_ui_mapper_chat.py::_on_tool_result` already converts `ToolResultEvent → TOOL_CALL_END + TOOL_CALL_RESULT` (the canonical pair, `_emit_end_result`). FE renders via the existing `useDefaultRenderTool` wildcard (`tool-renderers.tsx`) — no new hook.

What it rejects (carrier #3 ACTIVITY via `useRenderActivityMessage`):
- `ag_ui_mapper_activity.py` keys on outer MCP tool names (`agent_launch_swarm`/`agent_invoke_graph`) and correlates by the executor-envelope `run_id` from `swarm.launched`/`graph.launched` `events_publish`. The `spawn_*` `@tool`s emit **none** of those — they ride `tool_stream`, not the events brick. Carrier #3 is structurally unreachable here.

FE dispatcher pins (per SDK-First dispatcher-source rule):
- Tool-call pairing is **tcid-only**: `ag_ui_mapper_chat.py::_on_tool_result` and `_on_tool_call_delta` key on `tool_call_id`; `messageId` is never used for tool pairing.
- FE render: `@copilotkitnext/[email protected]/dist/hooks/use-render-tool-call.mjs:58` (`renderToolCalls.find(rc => rc.name === "*")` first-wildcard) → `WildcardRender` in `frontends/next-dashboard/lib/copilotkit/tool-renderers.tsx`. The pill's InProgress→Complete flip is driven by the `role:"tool"` message synthesized from `TOOL_CALL_RESULT` (this repo's `a2ui-protocol.md` "endless spinner" note, bd-3uhr).
- `TOOL_CALL_START` carries optional `parentMessageId` (`@ag-ui/[email protected]/dist/index.d.ts:1368`) — **out of scope** here (see Error Handling / follow-ups).

### Flow

```
parent chat Agent (has AGUIBridgePlugin; AGUIBridgePlugin.attach sets
  agent._chat_stream_queue / _chat_stream_loop for the turn)
   │
   └─ LLM calls spawn_swarm(agent_ids, task, agent=<parent, injected>)
        │  resolves (queue, loop) from agent._chat_stream_queue/_loop
        ▼
      _build_specialist(cfg, parent_queue=queue, parent_loop=loop)
        │  Agent(plugins=[skills, offloader, SubAgentToolBridgePlugin(queue, loop)])
        ▼
      specialist runs a tool → BeforeToolCallEvent + AfterToolCallEvent
        fire on the SPECIALIST's own registry
        │  plugin push_threadsafe(...) onto the PARENT's queue
        ▼
      parent stream drains queue → ag_ui_mapper_chat →
        TOOL_CALL_START / END / RESULT → FE pill flips Running→Done
```

## Components and Interfaces

### NEW `components/agent/src/factory/agent/plugins/_bridge_common.py`
Extract two free functions currently inline in `ag_ui_bridge.py`:
- `normalize_payload(result) -> tuple[Any, bool]` (the `_normalize_payload` body — unwrap Strands `{content:[{text|json}]}` shapes, return `(payload, is_error)`).
- `push_threadsafe(queue, loop, event)` (the `_push` body — `loop.call_soon_threadsafe(queue.put_nowait, event)` with the closed-loop `RuntimeError` guard).

In-brick import (same `plugins/` dir) — **not** a cross-brick violation.

### REFACTOR `components/agent/src/factory/agent/plugins/ag_ui_bridge.py`
Import `normalize_payload` + `push_threadsafe` from `_bridge_common`; delete the local copies. **Shrinks** the file from 181 LOC. Behavior byte-identical.

### NEW `components/agent/src/factory/agent/plugins/sub_agent_tool_bridge.py`
`SubAgentToolBridgePlugin(HookProvider)` — stateless, per-spawn, sessionless. Constructed with the **parent's** `queue` + `loop` (a queue it does not own).

```python
class SubAgentToolBridgePlugin:
    def __init__(self, queue, loop) -> None:
        self._queue, self._loop = queue, loop
        self._seen: set[str] = set()          # per-spawn dedupe on raw inner tcid

    def register_hooks(self, registry, **_):
        registry.add_callback(BeforeToolCallEvent, self._on_before)   # A1
        registry.add_callback(AfterToolCallEvent,  self._on_after)

    def _on_before(self, event):              # START — race guard (A1)
        tcid = str((event.tool_use or {}).get("toolUseId", ""))
        if not tcid or tcid in self._seen: return
        self._seen.add(tcid)
        push_threadsafe(self._queue, self._loop, ToolCallDeltaEvent(
            tool_call_id=tcid, tool_name=str((event.tool_use or {}).get("name","")), args_delta=""))

    def _on_after(self, event):               # END + RESULT
        tcid = str((event.tool_use or {}).get("toolUseId", ""))
        if not tcid: return
        payload, is_error = normalize_payload(event.result)
        if event.exception is not None:
            payload, is_error = str(event.exception), True
        push_threadsafe(self._queue, self._loop,
            ToolResultEvent(tool_call_id=tcid, payload=payload, is_error=is_error))
```

**AMENDMENT A1 (load-bearing — do NOT ship After-only):** wire **both** `BeforeToolCallEvent` and `AfterToolCallEvent`. Both fire inline on the sub-agent's own registry and self-order on the shared parent queue (START before RESULT per tcid), making the design race-immune for parallel graph nodes (`graph.py:715`). The G2-emitted START becomes a harmless dedup'd duplicate (the mapper's `seen_tool_call_ids` already de-dups by tcid).

### TOUCH `components/agent/src/factory/agent/runtime/adapters/strands_subagent_spawn.py`
- `_build_specialist(cfg, parent_queue=None, parent_loop=None)`: when `parent_queue` is present, append `SubAgentToolBridgePlugin(parent_queue, parent_loop)` to `all_plugins` (passed via `Agent(plugins=[...])` at ctor — the only correct `Plugin`/`HookProvider` attach path, same as the existing `skills_plugin`/`offloader`).
- Add a one-line helper `attach_subagent_bridge(agent) -> tuple[queue, loop]` reading `agent._chat_stream_queue` / `agent._chat_stream_loop` (LOC budget — keeps the file <200; currently 172).
- Add a **schema-invisible** `agent` param to `spawn_subagent(agent_id, task, agent=None)`; resolve `(queue, loop)` from it and pass into `_build_specialist`.

### TOUCH the three sibling spawn tools
`strands_swarm_spawn.py`, `strands_graph_spawn.py`, `strands_registered_graph_spawn.py`: add the schema-invisible `agent` param, resolve `(queue, loop)`, thread into their `_build_specialist(...)` / `_build_node_agent(...)` calls.

**`translate_strands_event` is UNCHANGED, `runtime/models.py` is UNCHANGED.** The plugin pushes already-typed `ChatStreamEvent`s straight onto the queue, bypassing the translator exactly as `AGUIBridgePlugin` does today. No new ChatStreamEvent variant; existing `ToolCallDeltaEvent` + `ToolResultEvent` suffice.

### FE contract — what the frontend receives, which hook renders it
No FE code change. The sub-agent's tool call now produces the **same three AG-UI events** the parent's own tool calls already produce:

```
TOOL_CALL_START   {toolCallId: <raw inner tcid>, toolCallName: <tool>}   # already arriving (G2)
TOOL_CALL_END     {toolCallId: <same tcid>}                              # NEW — from plugin
TOOL_CALL_RESULT  {messageId: <uuid4>, toolCallId: <same tcid>,
                   content: <json payload>, role: "tool"}                # NEW — from plugin
```

Rendered by the existing wildcard `useDefaultRenderTool` → `WildcardRender` (`tool-renderers.tsx`). The pill flips InProgress → Complete when CopilotKit sees the `role:"tool"` message from `TOOL_CALL_RESULT`. Pairing is by `toolCallId` only — START and END/RESULT **must share the same raw inner `toolUseId`** (strands-expert N2/N3); no namespacing on END/RESULT.

## Data Models

**No new Pydantic contract.** The plugin reuses two existing `ChatStreamEvent` variants from `components/agent/src/factory/agent/runtime/models.py`, both with `extra="forbid"`:

- `ToolCallDeltaEvent` — `{type:"tool_call_delta", tool_call_id: str, tool_name: str|None, args_delta: str=""}`. First emission per `tool_call_id` → `TOOL_CALL_START`. Used for the Before-hook START.
- `ToolResultEvent` — `{type:"tool_result", tool_call_id: str, payload: Any=None, is_error: bool=False}`. Mapper turns it into the canonical `TOOL_CALL_END` + `TOOL_CALL_RESULT` pair. Used for the After-hook RESULT.

Neither variant carries a `message_id`/provenance field, and none is added — tool-call pairing is `tool_call_id`-only at the mapper. (`TextDeltaEvent` carries `message_id` for bubble routing; tool events do not need it.)

`parentMessageId` visual-grouping (nesting sub-agent tool pills under the sub-agent's text bubble) would require a NEW provenance field on `ToolCallDeltaEvent` plus FE work — explicitly **out of scope**; tracked as a P3 follow-up.

## Correctness Properties

> Requirements map to the `lusy2` acceptance criteria: **R1** = sub-agent tool calls surface their full lifecycle in the parent chat (pills resolve, not spin); **R2** = additive, no regression to existing chat/spawn behavior.

### Property 1: pair completeness
For every sub-agent tool call across all four spawn paths, the parent stream receives exactly one `TOOL_CALL_START`, one `TOOL_CALL_END`, and one `TOOL_CALL_RESULT`, all keyed on the same raw inner `toolUseId`. Pills flip Running → Done.

**Validates: Requirements 1.1**

### Property 2: tcid fidelity
The plugin's START and RESULT use the identical raw inner `toolUseId` Strands assigned the sub-agent tool call; no synthetic or namespaced id.

**Validates: Requirements 1.1**

### Property 3: ordering
`TOOL_CALL_START` (Before-hook) is enqueued before `TOOL_CALL_RESULT` (After-hook) for the same tcid, so `ag_ui_mapper_chat._on_tool_result` never drops the result for a tcid absent from `seen_tool_call_ids`.

**Validates: Requirements 1.1**

### Property 4: dedupe
The G2-emitted START for the same tcid is de-duplicated by the mapper's `seen_tool_call_ids`; the plugin's per-spawn `_seen` set prevents a double START from the plugin itself.

**Validates: Requirements 2.1**

### Property 5: isolation
Concurrent graph nodes (`graph.py:715`) do not bleed tcids across nodes; each specialist has its own plugin instance and dedupe set.

**Validates: Requirements 1.1**

### Property 6: additivity
With no spawn in a turn, byte-identical behavior to today (the plugin is only attached when `parent_queue` is present).

**Validates: Requirements 2.1**

## Error Handling

- **Closed loop / unwound invocation.** `push_threadsafe` swallows `RuntimeError` (loop closed mid-flight) exactly as `ag_ui_bridge._push` does — a late sub-agent result after the parent turn unwinds is a silent no-op, never a crash.
- **Tool exception.** When `AfterToolCallEvent.exception` is set, the plugin emits `ToolResultEvent(payload=str(exception), is_error=True)` so the pill resolves as an error rather than spinning.
- **Missing tcid.** Events without a `toolUseId` are ignored (guard in both hooks) — defensive, never raises into the sub-agent loop.
- **Parallel-node race (verification gate `a60nq`).** Amendment A1 makes the design race-immune by construction (Before+After both inline on the specialist registry, self-ordered). If `a60nq` empirically disproves this (RESULT can beat START on the shared queue), the mitigation is a P3 reorder-buffer in `ag_ui_mapper_chat` (hold an orphan RESULT briefly for its START) — NOT a redesign.
- **`parentMessageId` grouping** — out of scope; follow-up P3.

## Testing Strategy

- **`python-factory-ntyz7` (core):** unit + property tests that each of the four spawn paths (`spawn_subagent`, `spawn_swarm`, `spawn_graph`, `spawn_registered_graph`) emits START+END+RESULT with the same raw inner tcid onto a stub parent queue; pill-flip assertion through `ag_ui_mapper_chat`; payload normalization preserved (reuse `_bridge_common.normalize_payload` cases from the existing `ag_ui_bridge` tests so the refactor is pinned). Confirm `agent` param is absent from each spawn tool's generated JSON schema (decorator special-param exclusion).
- **`python-factory-a60nq` (concurrency verify):** spawn a multi-node graph whose nodes call tools concurrently (`graph.py:715` parallel path); assert every pill resolves, no END/RESULT dropped by `_on_tool_result`, no cross-node tcid bleed. If A1 is disproven, file the P3 reorder-buffer follow-up.
- **Regression:** existing `ag_ui_bridge` tests must stay green after the free-function extraction (behavior byte-identical).
- **Pre-ship gate:** `foreman_guardian_check` (implementer's duty — not exposed on the companion-x MCP server). Baseline 25 pre-existing grandfather `file_size` violations; zero new if `strands_subagent_spawn.py` stays <200 via the attach helper.

## Child bd issues (sequencing order)

1. **`python-factory-ntyz7`** (P1, feature) — core fix. New `_bridge_common.py` + `sub_agent_tool_bridge.py`; refactor `ag_ui_bridge.py`; thread parent queue/loop through `_build_specialist` + 4 spawn tools (Before+After hooks per A1).
2. **`python-factory-a60nq`** (P2, task, depends-on `ntyz7`) — concurrency verification (graph parallel nodes).

Non-blocking follow-ups (file only if pursued): `parentMessageId` visual grouping (P3, contract + FE); mapper reorder-buffer (P3, only if `a60nq` disproves A1).

## What NOT to do — the three most tempting wrong paths

- **W1 — Attach the bridge to the Swarm/Graph (`Swarm(hooks=[...])` / `GraphBuilder.set_hook_providers`).** That registry (`swarm.py:296` / `graph.py:465`) fires only `Before/AfterNodeCallEvent`; it **never** sees the inner agents' `AfterToolCallEvent`. You'd get node start/stop, never the tool result. Inner tool events fire on the **member agent's** registry during `node.executor.stream_async` — which is exactly why the attach point is `_build_specialist`.

- **W2 — Catch `ToolResultEvent` inside the spawn `@tool`'s `async for`.** Impossible: `agent.py:861` filters non-callback events before the tool's loop runs; the tool only ever sees `ToolStreamEvent` / `tool_use_stream` (`decorator.py:621`). Re-confirmed from czpw.1 verdict `209fb838`.

- **W3 — Reuse carrier #3 ACTIVITY (`SwarmLifecyclePlugin` / `ag_ui_mapper_activity.py`).** Wrong twice: those lifecycle plugins hook node-level events (can't see inner tool calls), and the activity mapper correlates by the executor-envelope `run_id` from `events_publish`, which `spawn_*` never emit. Bonus failure mode: minting a synthetic RESULT tcid unrelated to the START tcid → END/RESULT won't pair in the mapper and the pill stays stuck.

Architecture-level wrong paths (meta-architect): **WA1** extend `AGUIBridgePlugin` into a dual-mode parent/child class "for DRY" (SRP violation + breaches 200 LOC — correct DRY is the `_bridge_common.py` free functions); **WA2** thread the queue via a module global or contextvar (not concurrency-safe across simultaneous turns / fragile across the parallel-node boundary — and the "don't pollute the signature" objection is empty because `agent` is schema-invisible); **WA3** introduce a new ChatStreamEvent variant (existing variants pair by tcid; net-new contract for zero benefit).

## Appendix — LOC budget (current → risk)

| File | Now | After | Note |
|---|---|---|---|
| `plugins/ag_ui_bridge.py` | 181 | **shrinks** | extract free funcs to `_bridge_common.py` |
| `plugins/_bridge_common.py` | — | new (~40) | shared `normalize_payload` + `push_threadsafe` |
| `plugins/sub_agent_tool_bridge.py` | — | new (~70) | the plugin |
| `runtime/adapters/strands_subagent_spawn.py` | 172 | **MEDIUM risk ~185-190** | +params +attach helper; mitigate with 1-line `attach_subagent_bridge()` |
| `strands_swarm_spawn.py` | 81 | ~88 | +`agent` param + resolve |
| `strands_graph_spawn.py` | 88 | ~95 | +`agent` param + resolve |
| `strands_registered_graph_spawn.py` | 136 | ~143 | +`agent` param + resolve |
| `runtime/models.py` | — | unchanged | no new contract |
| `runtime/adapters/strands_mcp_chat_stream.py` | 143 | unchanged | translator untouched |
