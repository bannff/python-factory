# Upgrade to FastMCP 4 / MCP Spec 2026-07-28 — Design

> Status: **BLOCKED — hard upstream dependency conflict, not fixable from
> this repo.** Corrected once already before this: the original draft
> proposed routing internal events through `subscriptions/listen`; SME
> review (strands-expert + meta-architect, independently) found that
> mechanism scoped to 4 fixed protocol-defined notification kinds and unable
> to carry arbitrary domain events. This design uses FastMCP 4's
> `ServerExtension` framework instead — confirmed real by direct doc read
> (`fastmcp.server.extensions`, SEP-2133). See §0 below for the current
> blocker discovered during Phase 0 implementation.

## 0. BLOCKER — Strands SDK is incompatible with MCP SDK v2 (discovered during Phase 0)

**Status as of this writing: implementation cannot proceed. Not a code
problem on Companion-X's side — a real, disjoint upstream dependency
conflict between two third-party libraries this repo depends on.**

- FastMCP 4.x (every prerelease, `4.0.0a1` through `4.0.0b3`) depends on
  `fastmcp-slim`, which requires `mcp>=2.0.0,<3.0.0` (MCP Python SDK v2 —
  needed for the 2026-07-28 stateless spec revision this whole upgrade is
  for).
- This repo pins `strands-agents[openai]==1.50.2`. Every released version of
  `strands-agents` through the latest (`1.53.0`) requires
  `mcp<2.0.0,>=1.23.0` — confirmed directly against PyPI metadata for
  1.50.2, 1.51.0, 1.52.0, 1.53.0, and back through 1.9.1.
- These two requirement ranges (`mcp>=2.0.0` vs. `mcp<2.0.0`) are disjoint,
  not merely strict — there is no `mcp` version that satisfies both.
  `uv lock` fails outright with an unsatisfiable-resolution error, both at
  the repo root and in `projects/companion_x`.

**Root cause, confirmed by reading the actual open fix upstream**
(`strands-agents/sdk-python#3708`, "feat: mcp v2 compatible changes under a
flag," still open/unmerged as of this writing): MCP v2 renamed and removed
several internal building blocks that Strands' own `MCPClient` imports and
calls directly, not just through public MCP SDK surface:

1. **Exception type renamed and re-shaped.** `McpError` (v1, constructor
   takes an `ErrorData` object) became `MCPError` (v2, constructor takes
   `(code, message, data)` positionally) — different name, different
   constructor signature, not just a rename.
2. **Transport constructor signature changed.** v1's
   `streamable_http_client` accepted loose header kwargs; v2's takes a
   pre-configured `httpx.Client` instance instead — a structural API
   change, not an additive one. v2's version also only closes an HTTPX
   client it created itself, requiring Strands to wrap the client's
   lifetime in its own context manager to avoid a resource leak on the
   old assumption.
3. **`GetSessionIdCallback` removed entirely** in v2, because MCP v2
   removed protocol-level sessions (`Mcp-Session-Id`) as part of the same
   stateless-transport redesign this whole Companion-X spec was chasing.
   Strands' code references this callback type directly.

The upstream PR's own fix is a `_compat` shim module that feature-probes
which MCP major version is installed (via `ClientSession.discover`, not
version-string parsing) and branches internally — a real, principled fix,
but it is **unmerged and unreleased**. No published `strands-agents`
version tolerates `mcp>=2` today.

**Why this blocks Companion-X specifically:** Companion-X's `agent` brick
uses Strands as its core agent runtime (persona registry, `AgentSkills`,
Graph/Swarm primitives — this is not a peripheral dependency, it's
foundational to the whole control plane). Upgrading `fastmcp`/`mcp` without
Strands tolerating the new `mcp` major version would break agent
functionality repo-wide, which Requirement 4's continuity gate explicitly
forbids.

**Options, no fourth exists:**
1. **Wait** for `strands-agents/sdk-python#3708` (or an equivalent fix) to
   merge and ship in a released `strands-agents` version, then resume this
   spec's Phase 0 from where it left off.
2. **Patch around it locally** (vendor a compat shim, or fork/pin an
   MCP-v1-only FastMCP release) — explicitly NOT recommended: this is
   exactly the "bespoke code instead of framework" pattern this entire spec
   exists to eliminate, and it would mean maintaining a local fork of
   upstream compatibility logic that the real fix (option 1) will make
   obsolete anyway.
3. Re-scope this spec to something achievable without the `mcp` v2 jump —
   not recommended either: the whole point of this spec (killing the
   `event_bus` private wire via a real FastMCP 4 `ServerExtension`, and the
   new spec's stateless push model) depends on FastMCP 4, which depends on
   `mcp` v2. There's no meaningful subset of this spec's goals achievable
   without it.

**Decision: Option 1. This spec is parked, not abandoned.** Requirements.md
and this design remain the correct target design — implementation resumes
Phase 0 exactly where it stopped (Phase 0.5's read-ahead work is already
done and confirmed valid: `as_task=True` has zero production call sites
today, so the Workflow-redirect gate checklist has nothing to retrofit)
once `strands-agents` ships `mcp>=2` compatibility. No design rework is
needed when that happens — only the dependency bump itself needs retrying.

## 1. Phased rollout — not one atomic change

Per meta-architect's explicit recommendation: a repo-wide dependency bump
touching ~35+ bricks, plus a transport migration for 3 internal consumers,
does not ship as one PR. Four phases, each independently verified, each
with an explicit go/no-go checkpoint before the next phase starts.

```
Phase 0: FastMCP 4 dependency upgrade only (Requirement 1)
    → verify: full existing test suite, zero behavior change
Phase 0.5: Replace call_brick_tool's as_task/task_ttl_ms with Workflow-backed
           durable attempts (Requirement 6) — this is a Phase 0 BLOCKER, not
           an optional follow-up: FastMCP 4 removed task_meta with no
           drop-in fix, so the dependency bump cannot complete without this.
    → verify: allowlist-gating property tests, compatibility table honored,
      test_native_dispatch_compat.py rewritten and passing
Phase 1: Build the events ServerExtension (Requirement 2, new code only)
    → verify: extension works in isolation, event_bus untouched, nothing switched over
Phase 2: Migrate low-risk consumers (run_stream_routes.py, then dashboard hook)
    → verify: equivalence proof (Requirement 3), parallel operation window
Phase 3: Migrate ag_ui_chat_stream.py (chat — highest risk, last)
    → verify: full multi-turn chat regression, rollback switch tested
Phase 4: Delete event_bus.py / tool_event_stream.py
    → gate: only after Phase 3's rollback window elapses with zero regressions
```

Per Requirement 7, every phase above re-runs the FULL dependent test suite
(not just new tests for that phase) before its gate is signed off — a
regression introduced in an earlier phase must be caught at the next phase
boundary, not discovered only in a final end-to-end pass.

No phase starts until the prior phase's verification is complete and
explicitly signed off. This is the direct implementation of Requirement
4.3's "STOP condition" language in requirements.md.

## 2. Phase 0 — FastMCP 4 dependency upgrade

### 2.1 Version target and floor bumps

- `pyproject.toml`: `fastmcp==3.2.4` → latest FastMCP 4.x (pin exact version
  once selected, not a range — per this repo's dependency-pinning norms).
- Hard floor bumps required by FastMCP 4, resolved in the same change:
  - `pydantic>=2.12` (verify current pin, bump if needed).
  - `fastapi>=0.133.0` if the FastAPI server extra is in use (current pin:
    `fastapi>=0.128.0` — must bump).
- `uv.lock` regenerated; `foreman_sync_brick_deps` run to confirm no brick's
  declared `pip_packages` conflicts with the new floor.

### 2.2 Known gotchas, resolved explicitly (not discovered mid-upgrade)

| Gotcha | Where | Resolution |
|---|---|---|
| `TaskMeta` passed to arbitrary tools via `call_brick_tool`, not the `task=True` decorator | `bases/mcp_server/.../progressive_invocation.py`, `tool_dispatch.py` | **NOT fixed by registering `TasksExtension`** — confirmed by direct testing that `task_meta` is removed from `call_tool()`'s signature with no parameter-level replacement, and `TasksExtension` requires static `task=True` tool declaration + client-side capability negotiation, neither of which fits a dynamically-resolved arbitrary tool name. Real fix is §2.4/Requirement 6 (Workflow-brick-backed durable attempts) — this row exists only as a pointer, not a standalone resolution. |
| `mount()` now always runs child lifespan + middleware | `aggregator.register_brick()`, ~35+ mounted bricks | Audit each brick's `server.py`/lifespan for an assumption of "runs once at brick startup only." Confirmed low-risk by code shape (bricks are already mounted via `aggregator.register_brick()` today, not run standalone) — verify with the full per-brick test suite in 2.3, not by inspection alone. |
| `ToolTransform`/`add_transform` import path | `bases/mcp_server/.../service_policy.py` | Already on the forward-compatible API. Re-verify `fastmcp.server.transforms.tool_transform` resolves post-upgrade; if the module moved, this is a one-line import fix, not a redesign. |

### 2.3 Verification (Phase 0 gate)

- Full test suite across every brick that imports `fastmcp` directly
  (confirmed ~35+ bricks) — not a representative sample.
- `foreman_guardian_check` run with `base_sha` set to the pre-Phase-0 commit
  (this is the tool's actual scoping mechanism, confirmed by direct
  invocation — not a brick-filter argument, which doesn't exist). This
  ratchets the `mcp_contracts`/LOC checks to only what this phase's diff
  touches. The repo's existing 82 pre-existing file-size violations and
  legacy MCP-contract findings are NOT this phase's problem to fix or be
  blocked by; the gate is "no new violations from this diff," confirmed via
  `new_violations: []` in the check's own output.
- Requirement 4.1/4.2's full continuity checklist (every dashboard tab,
  chat streaming, Cmd-K palette, `rl_smoke.py`) smoke-tested against the
  upgraded dependency alone
  — `event_bus` is untouched in this phase, so any regression here is
  attributable to the dependency bump, not the transport migration.
- No code beyond the dependency bump and the three named gotcha fixes lands
  in this phase. Phase 1 does not start until this phase is signed off.

## 2.4 Phase 0.5 — Workflow-backed replacement for `call_brick_tool`'s background-task pattern

This phase is a hard blocker inside Phase 0, not a separate later concern:
the `fastmcp` version bump cannot be considered complete while
`progressive_invocation.py`/`tool_dispatch.py` still construct
`TaskMeta`/pass `task_meta=` into `call_tool()`, since that parameter no
longer exists in FastMCP 4.

**Design (per SME review, strands-expert):**

- `call_brick_tool(as_task=True, task_ttl_ms=...)` resolves
  `(brick_name, tool_name)` against the `workflow` brick's
  `durable_tasks.allowlist` (a pre-registered `ToolTarget`). Not on the
  allowlist → fail closed with `TaskNotAllowlistedError`, using the same
  `transport_failure(...)` pattern `progressive_invocation.py` already uses
  for `InvalidTaskMetadataError`.
- On an allowlisted target: call `factory.workflow.interface`'s
  `Runtime.start_run(workflow_name_or_id=..., input=parsed_args,
  envelope=<server-side authority context>, run_key=<generated idempotency
  key>)`. `task_ttl_ms` threads into Workflow's existing lease/attempt model
  (`lease_seconds`/`max_attempts`) — reuse Workflow's TTL-equivalent
  concept, do not invent a second one.
- Reached through the aggregator/MCP boundary, never a direct cross-brick
  Python import — same Polylith rule every other cross-brick call in this
  codebase follows.
- Return shape: Workflow's `start_run` response, wrapped in the same
  `NativeTransportOutput` envelope `call_brick_tool` returns for synchronous
  calls today — callers get one consistent shape, not "task shape" vs.
  "tool shape" depending on `as_task`.
- Polling/cancellation: `Runtime.get_run(run_id=...)` /
  `Runtime.cancel_run(run_id=...)` — both already exist on Workflow's
  interface, no new surface needed for read/cancel.
- **Envelope authority**: `Runtime.start_run`/`get_run`/`cancel_run` require
  a mandatory `envelope` argument. This design states explicitly: that
  envelope is the aggregator's own server-side authority context, never
  anything derived from caller input — preserving `call_brick_tool`'s
  existing explicit rejection of caller-supplied envelopes
  ("Public call_brick_tool cannot accept caller-supplied authority
  envelope"). This redirect must not become a hole in that boundary.
- **Storage backend**: Workflow's `durable_named_mcp_execution` capability
  is `sqlite-only` per its own `get_capabilities()` today. Any deployment on
  a different storage backend gets `as_task=True` failing closed with a
  clear error — no silent fallback to synchronous execution.

**Compatibility table (old → new), required before implementation:**

| Old (`CreateTaskResult`/`task_meta`) | New (Workflow-backed) |
|---|---|
| Any tool name, resolved dynamically per call | Must be pre-registered on `durable_tasks.allowlist` |
| `TaskMeta(ttl=task_ttl_ms)` | `lease_seconds`/`max_attempts` on the Workflow run |
| Opaque `CreateTaskResult` task handle | Workflow `start_run` response (run id, status) |
| No retry/idempotency semantics | Workflow's existing idempotency-key + retry/terminal classification |
| Client polls FastMCP directly for task status | Client calls `Runtime.get_run(run_id=...)` |

**Known behavior change, stated explicitly, not discovered later:**
background execution becomes a strictly narrower capability than
synchronous execution (allowlist-gated vs. any visible tool). Any existing
caller relying on `as_task=True` working for an arbitrary, non-preregistered
tool name will need its target added to the allowlist — this is tracked as
an explicit compatibility item, not silently patched around.

**Phase 0.5 gate checklist (per meta-architect review — must be literal, not
implied):**
- [ ] Grep every production call site currently passing `as_task=True` to
  `call_brick_tool` and enumerate the exact set of `(brick_name, tool_name)`
  targets in use today.
- [ ] Pre-populate the Workflow `durable_tasks.allowlist` with every target
  from that enumeration BEFORE this phase is signed off — do not discover
  broken callers post-merge via a failing smoke test.
- [ ] Allowlist-gating property tests (Requirement 7.2) written and green.
- [ ] Envelope-authority-boundary test (Requirement 7.2, new bullet) written
  and green.
- [ ] Storage-backend fail-closed test (Requirement 7.2, new bullet) written
  and green.
- [ ] Workflow redirect exercised under `RUN_MODE=agentcore` (Requirement
  7.2, new bullet).
- [ ] `test_native_dispatch_compat.py` rewritten against the new
  Workflow-backed behavior and green (Requirement 6.8).

## 3. Phase 1 — The Companion-X events `ServerExtension`

### 3.1 Why an extension, not `subscriptions/listen`, not a rewritten `event_bus.py`

`subscriptions/listen` (protocol-defined) only carries `toolsListChanged`,
`promptsListChanged`, `resourcesListChanged`, `resourceSubscriptions` — it
cannot express `rl.completed`, `memory.store`, or any other domain event
without disguising them as fake resource changes. That's the wrong tool,
confirmed by direct spec reading, not assumption.

A hand-rolled replacement module (a new `event_bus_v2.py`) would repeat the
exact problem being fixed — bespoke code masquerading as "the MCP way."

FastMCP 4's `ServerExtension` (`fastmcp.server.extensions`, SEP-2133) is the
correct middle path: it's a real, first-class, framework-provided mechanism
(the same one `TasksExtension` uses internally), and unlike
`subscriptions/listen` it is NOT limited to 4 fixed notification kinds —
an extension can define whatever request methods and event vocabulary the
application actually needs.

### 3.2 Extension shape

```python
# components/mcp_utils/src/factory/mcp_utils/events_extension.py
from fastmcp.server.extensions import ServerExtension, MethodBinding

class CompanionXEventsExtension(ServerExtension):
    """io.companion-x/events — internal event fan-out, replacing event_bus.py.

    Not a subscriptions/listen shim: this defines Companion-X's own event
    vocabulary (rl.*, memory.*, game.*, tool-invocation activity) as a
    genuine extension method, since the protocol's built-in
    subscriptions/listen cannot carry arbitrary domain events.
    """
    identifier = "io.companion-x/events"

    def methods(self) -> list[MethodBinding]:
        # One long-lived request method, e.g. "io.companion-x/events.listen",
        # served the same way any other extension request method is served.
        # The handler holds the connection open and yields events as they
        # arrive from the internal broadcaster (see lifespan()).
        ...

    async def lifespan(self):
        # Owns the in-process broadcaster (an asyncio-based fan-out,
        # functionally replacing event_bus.py's module-level _subscribers
        # list, but owned by the extension's lifecycle instead of a
        # standalone importable module). Started/stopped with the server.
        ...
```

- **Publish side**: `components/events/src/factory/events/runtime/bridge.py::bridge_to_event_bus`
  is renamed/redirected to call into this extension's broadcaster instead
  of importing `event_bus`. Same call site, same trigger (`events_publish`
  firing), different destination.
- **Consume side**: each of the 3 internal consumers calls the extension's
  served method instead of `event_bus.subscribe()`. In-process consumers
  (`run_stream_routes.py`, `ag_ui_chat_stream.py`), being `bases/api` code,
  do NOT reach into the extension object directly off the mounted server
  instance — per this repo's Polylith tenets (bases are pure transport
  shells; no cross-imports outside `factory.<brick>.interface`), they go
  through `factory.mcp_utils.interface`'s existing service-registry pattern
  (the same `get_service("tool_invoker")` style indirection already used
  elsewhere in this codebase), which the extension registers itself into at
  `lifespan()` startup. No base introspects `self.server`'s mounted
  extensions directly. The dashboard (`use-live-tool-stream.ts`) reaches it
  through the same `getMcpClient()` singleton from #736, calling the
  extension's served method as a normal MCP request — this specific
  invocation path (a generic TS SDK client calling a non-standard,
  extension-defined method, not `tools/call`) is UNVERIFIED and must be
  smoke-tested in Phase 1 (see §3.4) before Phase 2 is scheduled, since
  Phase 2's dashboard migration depends entirely on this working.
- **Registration is root-only.** Per the `ServerExtension` lifespan
  contract ("entered once per runtime tree, at the root... a mounted
  child's extensions do not propagate upward"), this extension is
  registered exactly once on whichever FastMCP instance is the actual
  transport root for a given `RUN_MODE` (`core.py::create_app()`'s server,
  the `bases/api` mount, or the AgentCore entrypoint) — never on an
  individual brick's own FastMCP instance. Bricks are mounted as children;
  they do not each register their own copy of this extension.
- **Scaling scope, stated explicitly, not left implicit:** this extension's
  in-process broadcaster is single-process/single-replica scoped, the same
  limitation `event_bus` has today. Requirement 1.3 states the 2026-07-28
  spec's stateless transport lets any replica serve any request — this
  extension is a deliberate, documented exception to that property for
  Companion-X's own internal event fan-out, not an oversight or a
  regression against Requirement 1.3's intent. If Companion-X is ever
  deployed with multiple replicas, this extension's internal events would
  need a shared backing store to fan out across replicas — out of scope
  for this spec, called out here so it isn't silently assumed solved.
- **Delivery latency**: the broadcaster inside `lifespan()` is a direct
  `asyncio`-based fan-out (queues per subscriber, `call_soon_threadsafe` or
  equivalent), preserving `event_bus`'s current near-instant, zero-polling
  property. This is not a regression to a slower mechanism — the framework
  wrapper does not change the actual delivery mechanism's performance
  characteristics.

### 3.3 Verification (Phase 1 gate)

- New extension code is fully unit-tested in isolation (publish → fan-out →
  N subscribers, zero-subscriber no-raise behavior, matching
  `event_bus.publish()`'s current defensive behavior).
- `event_bus.py` and `tool_event_stream.py` are UNTOUCHED and still fully
  operational in this phase — nothing is switched over yet. This phase adds
  new code, it does not remove or bypass anything.
- No dashboard, chat, or telemetry consumer is migrated in this phase.
- `components/mcp_utils/src/factory/mcp_utils/events_extension.py` (and any
  companion contract module) stays under 200 LOC with typed Pydantic
  input/output models for its served method — this is a brand-new file and
  must not add to this repo's existing MCP-contract debt (currently 82
  file-size violations, dozens of `missing_input_model`/`raw_container_egress`
  findings repo-wide, all pre-existing/informational today). New code holds
  to the strict standard even where legacy code doesn't yet.

### 3.4 Client-invocation smoke test — REQUIRED before Phase 1 sign-off

Per SME review, this is the single biggest unverified technical assumption
in the whole plan and must be proven now, not discovered mid-Phase-2: does
`frontends/next-dashboard/lib/mcp-client.ts`'s TS SDK client (built on
`@modelcontextprotocol/sdk`'s `Client`/`StreamableHTTPClientTransport`)
expose a way to invoke a non-standard, extension-defined request method —
not just `tools/call`/`resources/*`? Round-trip a call from the actual TS
client in `mcp-client.ts` to a trivial placeholder extension method as part
of this phase, before any real event payload is designed. If the SDK client
cannot invoke arbitrary extension methods, this design's dashboard-consumer
migration path (§4, item 2) needs re-evaluation before Phase 2 is scheduled
— this is a go/no-go finding, not an implementation detail.

## 4. Phase 2 — Migrate low-risk consumers first

1. `bases/api/src/factory/api/runtime/run_stream_routes.py` migrates first
   (background-spawn telemetry, no direct user-facing surface).
2. `frontends/next-dashboard/lib/hooks/use-live-tool-stream.ts` migrates
   second (Timeline tab, Metrics tab's live-stream indicator — user-facing
   but not the highest-risk surface).
3. **Equivalence proof required before either consumer's old code path is
   removed** (Requirement 3): delivery ordering, near-instant latency,
   dropped-client/reconnect behavior (the 2026-07-28 spec removed SSE
   resumability/`Last-Event-ID` entirely — this design states plainly: a
   dropped connection to the extension's served method must be reissued as
   a new request; there is no resume-from-last-event semantics, and the
   client-side code must handle this explicitly, not assume silent
   resumption), and zero-subscriber behavior.
4. Both transports run in parallel during this phase — `event_bus` is not
   touched, the new extension runs alongside it, consumers are switched
   one at a time with the old path available as an instant fallback.

### 4.1 Verification (Phase 2 gate)

- Full Requirement 4.1/4.2 continuity checklist, with explicit focus on:
  Timeline tab (RL/memory events — the exact regression class from the
  #734 investigation must not reopen), Metrics tab's live-stream indicator.
- Real failure-injection testing: kill a subscriber mid-stream, verify
  reconnect behavior matches what item 3 above states, not silent hope.

## 5. Phase 3 — Migrate chat streaming last, with rollback

`ag_ui_chat_stream.py` merges two async generators (chat-turn events +
`event_bus.subscribe()`) into one queue feeding the AG-UI SSE response.
This is the highest-risk migration point in the whole spec — chat is the
most user-visible surface, and a regression here is immediately obvious
and disruptive.

1. Migrate `ag_ui_chat_stream.py`'s bus-drain to the new extension, following
   the exact same pattern proven in Phase 2.
2. Ship with an explicit, tested feature flag/rollback switch that reverts
   this one call site back to `event_bus.subscribe()` without a code
   rollback — a config flip, not a redeploy.
3. Full multi-turn chat regression testing (not a single "probe ok" smoke
   test): streaming token-by-token responses, tool-call cards, reasoning
   panel, persona switching, navigation-via-chat (confirmed working
   end-to-end in prior session testing — must remain so).
4. Hold the rollback switch available for at least one full release cycle
   before Phase 4 proceeds.

## 6. Phase 4 — Delete the old bus

Only after Phase 3's rollback window elapses with zero reported
regressions:

1. Repo-wide import search confirms zero remaining references to
   `event_bus` / `tool_event_stream` outside their own module files.
2. `components/mcp_utils/src/factory/mcp_utils/event_bus.py` and
   `tool_event_stream.py` are deleted.
3. `GET /api/events/tools` (`events_sse.py`) and `GET /api/stream/run/{run_id}`
   (`run_stream_routes.py`'s old route) are deleted alongside their
   superseded implementations.
4. Final `foreman_guardian_check`, full repo test suite, full Requirement 4
   continuity checklist — one last time, end to end.

## 7. Sequencing with #737 (mandatory auth)

Per meta-architect: design this spec's extension method in parallel with
#737's auth design now (both touch the same `_meta`/identity model under
FastMCP 4), but do not ship Phase 2/3's actual migration ahead of #737's
auth enforcement landing on `/mcp`. Unauthenticated push is a strictly
worse posture than unauthenticated pull. If #737 has not landed by the time
Phase 1 completes, Phase 2 waits.

## 8. AgentCore Runtime compatibility (Requirement 5)

The events extension's `lifespan()`-owned broadcaster and served method are
in-process constructs — they do not require `stateless_http=False`. This
design does not change `stateless_http=True` for any `RUN_MODE`, including
`agentcore`. Confirm during Phase 1 implementation that the extension's
served method works correctly under AgentCore's specific request-routing
model (not just the standalone/`RUN_MODE=api` FastAPI-mounted path) before
Phase 1 is signed off as complete for that deployment target.

## Non-goals (unchanged from requirements.md)

- No external MCP client onboarding (oracles, blockchain listeners, etc.) —
  that remains #739, parked, to be revisited once this spec's extension
  pattern is proven and #737's auth lands.
- No adoption of `subscriptions/listen` anywhere in this spec's scope.
