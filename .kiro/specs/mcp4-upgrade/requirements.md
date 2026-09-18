# Upgrade to FastMCP 4 / MCP Spec 2026-07-28 — Requirements

## Introduction

Companion-X pins `fastmcp==3.2.4` (repo-root `pyproject.toml`), which targets the
handshake-era MCP transport (`Mcp-Session-Id`, SSE resumability via
`Last-Event-ID`). The MCP specification's 2026-07-28 revision removed
protocol-level sessions entirely and replaced server-initiated interaction
with Multi Round-Trip Requests (MRTR) and a new opt-in `subscriptions/listen`
push channel. FastMCP 4 (built on MCP Python SDK v2) negotiates both eras per
connection, so this is an additive upgrade, not a hard cutover — legacy
clients keep working while the server gains the new capabilities.

This spec exists because Companion-X currently has a **third, undocumented
MCP surface gap** discovered during #736/#737/#739: a bespoke, non-MCP,
in-process pub/sub (`event_bus` in `components/mcp_utils/src/factory/mcp_utils/event_bus.py`)
that exists ONLY because the pinned MCP transport had no session-independent
way to push server-to-client. Three internal consumers currently depend on
this private wire instead of MCP:

1. `frontends/next-dashboard/lib/hooks/use-live-tool-stream.ts` (dashboard Timeline/live tool activity)
2. `bases/api/src/factory/api/runtime/run_stream_routes.py` (`GET /api/stream/run/{run_id}`, background-spawn telemetry)
3. `bases/api/src/factory/api/runtime/ag_ui_chat_stream.py` (chat streaming's own internal event drain)

Per explicit user direction: **the goal is not to accept unsolicited external
push right now** (that remains #739, parked pending this upgrade and its own
design). The goal of THIS spec is narrower and more foundational: stop
running a private, bespoke pub/sub wire in parallel with MCP, and make
`subscriptions/listen` (MCP's own opt-in server-to-client notification
channel, stateless, no sessions, no sticky routing) the single mechanism
these three internal consumers use instead — "everything flows through MCP,
frameworks over bespoke code," applied literally.

**This spec is explicitly broad, not narrowly scoped to the bus swap alone**,
per direct user instruction: every dashboard tab and every internal
integration point that works today (Timeline, Metrics, chat streaming,
Findings, Evals, Graph, ML, Games, Blockchain, Sandbox,
`rl_smoke.py`, #736's and #737's completed/in-flight work) must
continue to work after both the FastMCP 4 upgrade and the internal transport
migration. Requirement 4 is the enumerated, non-negotiable continuity gate
for the whole spec — nothing currently working is out of scope for
verification just because it seems unrelated to the bus swap on the surface.

## Requirement 1 — Repo-wide FastMCP 4 / MCP SDK v2 upgrade

1. The pinned `fastmcp` dependency in the repo-root `pyproject.toml` is
   upgraded from `3.2.4` to the latest FastMCP 4.x release compatible with
   this repo's other pinned dependencies (Strands, Pydantic v2, etc.).
2. Every brick that imports `fastmcp` (confirmed: all ~35+ bricks under
   `components/*/src/factory/*/mcp/*.py` and `components/*/src/factory/*/server.py`,
   plus `bases/mcp_server/`, `bases/api/`, `bases/blueprint/`, `bases/openarcade/`)
   continues to register tools/resources/prompts without per-brick code
   changes, per FastMCP 4's stated backward-compatibility guarantee ("most
   FastMCP 3 servers upgrade unchanged"). Known, confirmed gotchas (not
   speculative — found by direct SME code review) are resolved explicitly,
   not discovered mid-upgrade:
   - `bases/mcp_server/.../progressive_invocation.py` and `tool_dispatch.py`
     construct `TaskMeta` and pass it to arbitrary brick tools via the
     `call_brick_tool` meta-tool, not via the `@mcp.tool(task=True)`
     decorator pattern. **Confirmed by direct testing: registering
     `TasksExtension` does NOT fix this** — FastMCP 4 removed
     `task_meta` from `call_tool()`'s signature entirely, and
     `TasksExtension` only routes calls to background execution when the
     *target tool* is statically decorated `task=True` ahead of time AND
     the *calling client* declares extension support in its own request —
     neither holds for `call_brick_tool`'s dynamically-resolved arbitrary
     tool names. The actual fix is Requirement 6 (Workflow-brick-backed
     durable attempts) — see that requirement for the real resolution.
     This bullet exists only to flag that this specific gotcha is NOT
     resolved by the general "upgrade unchanged" guarantee or by a simple
     extension registration.
   - Two hard dependency floor bumps: `pydantic>=2.12` and (if the FastAPI
     server extra is used) `fastapi>=0.133.0`. The repo currently pins
     `fastapi>=0.128.0` — this floor bump is resolved explicitly before the
     `fastmcp` version bump lands, not treated as an implicit side effect.
   - `mount()` semantics changed: a plain `mount()` now always runs the
     child's lifespan and middleware. `aggregator.register_brick()` mounts
     ~35+ bricks this way — confirm no mounted brick's lifespan assumes it
     runs exactly once at brick-level startup rather than being invoked
     through the parent's mount.
   - `ToolTransform`/`add_transform` (already used in `service_policy.py`)
     is confirmed on the correct forward-compatible API already — re-verify
     the exact import path (`fastmcp.server.transforms.tool_transform`)
     against FastMCP 4's actual module layout, since it isn't explicitly
     enumerated in the public migration guide.
   Any additional brick requiring a change beyond these known items is
   enumerated explicitly in the design doc — no silent breakage discovered
   post-merge.
3. `bases/mcp_server/src/factory/mcp_server/core.py::create_app()` and
   `bases/api/src/factory/api/runtime/adapters/rest.py`'s `/mcp` mount
   continue to serve `stateless_http=True` as the default posture for all
   `RUN_MODE`s, preserving AgentCore Runtime compatibility (`RUN_MODE=agentcore`
   requires statelessness per this repo's own steering docs) and the
   horizontal-scaling property (any replica serves any request, no sticky
   routing, no shared session store) that the 2026-07-28 spec revision was
   designed to guarantee.
4. Existing MCP client code (`frontends/next-dashboard/lib/mcp-client.ts`,
   `projects/companion_x/scripts/rl_smoke.py`)
   is upgraded to the modern MCP SDK client
   surface where a browser/Python client library major-version bump is
   required, or confirmed to keep working unchanged where protocol
   negotiation (`Client(url)` auto-probing modern vs. legacy) makes an
   explicit client-side change unnecessary.
5. All existing test suites referencing `fastmcp`/`mcp` APIs directly
   (confirmed: dozens of test files under `bases/mcp_server/test/`,
   `bases/api/test/`, `components/*/test/`) pass unchanged or are updated
   to the FastMCP 4 API surface with each changed call site documented.

## Requirement 2 — Retire the hand-rolled `event_bus` in favor of FastMCP's own extension framework

**Corrected per SME review (strands-expert + meta-architect, both independently
flagged the original mechanism choice as wrong):** MCP's `subscriptions/listen`
is scoped to four fixed, protocol-defined notification kinds
(`toolsListChanged`, `promptsListChanged`, `resourcesListChanged`,
`resourceSubscriptions`) — it cannot carry arbitrary domain events like
`rl.*`/`memory.*`/game-lifecycle activity. Forcing those events through it
would mean disguising them as fake "resource changes," which is not what
this requirement wants. The corrected target is FastMCP 4's own
**extension framework** (`add_extension()` — the same real, first-party
mechanism FastMCP itself uses internally for its background-tasks feature,
`TasksExtension`) — a genuine framework primitive, not a second
hand-rolled module reinvented under a different name.

1. `components/mcp_utils/src/factory/mcp_utils/event_bus.py` and
   `tool_event_stream.py` (the current hand-rolled, in-process pub/sub) are
   replaced by a small MCP extension built on FastMCP 4's `add_extension()`
   API, registered on the MCP server the same way `TasksExtension` is
   registered. This extension defines Companion-X's actual event kinds
   (tool-invocation activity, RL lifecycle events, memory events, game
   lifecycle events, chat-stream-relevant activity) as first-class,
   documented notification types — using the framework's real extension
   mechanism instead of a private Python module other code imports
   directly.
2. `components/events/src/factory/events/runtime/bridge.py::bridge_to_event_bus`
   (the current fan-out point from `events_publish`) is redirected to push
   through this extension instead of the old `event_bus` module, preserving
   the same zero-polling, near-instant delivery property the current bus
   provides — not a coarse polling interval.
3. Each of the three current internal consumers is migrated to receive
   events through this extension instead of importing `event_bus` directly:
   - `frontends/next-dashboard/lib/hooks/use-live-tool-stream.ts` receives
     events through the same `getMcpClient()` singleton already established
     in `lib/mcp-client.ts` (#736) rather than a second, parallel
     bespoke `EventSource` endpoint.
   - `bases/api/src/factory/api/runtime/run_stream_routes.py` and
     `bases/api/src/factory/api/runtime/ag_ui_chat_stream.py` receive
     events through the extension's in-process API, not by importing
     `event_bus` as a Python module.
4. **Sequencing, per explicit SME instruction:** migrate the two lower-risk
   consumers first (`run_stream_routes.py`, then the dashboard hook), prove
   equivalence under real failure conditions (client disconnect mid-stream,
   zero subscribers, high event volume — see Requirement 3), and migrate
   `ag_ui_chat_stream.py` (chat streaming — the most user-visible surface)
   last, with an explicit, tested rollback path back to the old bus for at
   least one release cycle before the old bus is deleted.
5. `GET /api/events/tools` (`bases/api/src/factory/api/runtime/events_sse.py`)
   and `GET /api/stream/run/{run_id}` (`run_stream_routes.py`) are retired
   once their consumers are migrated and equivalence is proven (see
   Requirement 3) — not left running in parallel indefinitely as a silent
   second transport.
6. `event_bus.py` and `tool_event_stream.py` are deleted only once every
   internal consumer no longer imports them, confirmed via a repo-wide
   import search with zero remaining references, AND the chat-streaming
   rollback window from item 4 has elapsed with no regression — not
   deprecated-in-place, and not deleted same-day as the chat migration.
7. This requirement explicitly does NOT adopt `subscriptions/listen` for
   Companion-X's own internal event fan-out. `subscriptions/listen` remains
   available and unused by this spec — it is the correct mechanism for
   #739's separate, future external-push use case (arbitrary third-party
   MCP clients), not for these three known, first-party, same-deployment
   consumers.

## Requirement 3 — Equivalence proof before retirement

1. A defined proving window runs both the existing `event_bus` and the new
   FastMCP extension-based path in parallel before any retirement, per
   explicit SME guidance (strands-expert and meta-architect both required
   this sequencing, independently).
2. Equivalence is proven against, at minimum: delivery ordering, delivery
   latency (near-instant, not polling-interval-bounded, matching the current
   `call_soon_threadsafe` responsiveness), behavior on a dropped/reconnected
   client (the 2026-07-28 MCP spec removed SSE resumability and
   `Last-Event-ID` entirely — the design must state explicitly what a
   dropped connection does on reconnect for whichever transport the
   extension actually uses under the hood), and behavior with zero
   subscribers (must not raise, matching `event_bus.publish()`'s current
   defensive no-subscriber behavior).
3. The three consumers listed in Requirement 2.3 are individually verified
   against the new mechanism, not just the mechanism's existence — each
   consumer's actual rendered behavior (background-spawn telemetry delivery,
   Timeline tab live updates, chat streaming continuity) is confirmed
   unchanged from a user-observable standpoint, migrated and proven in the
   order specified in Requirement 2.4 (chat last, with a tested rollback).

## Requirement 4 — Full-surface continuity: everything working today keeps working

This requirement is the primary acceptance gate for the whole spec, not a
narrow afterthought. The upgrade is worthless if it trades a bespoke wire
for a broken dashboard. Every currently-working user-facing surface and
every currently-working internal integration point is enumerated below and
individually verified — not assumed compatible because "FastMCP 4 upgrades
most 3.x servers unchanged."

### 4.1 — Every dashboard tab/surface

The following tabs (confirmed live in the running dashboard, `localhost:3000`
sidebar) are individually smoke-tested after the FastMCP 4 upgrade AND after
the `event_bus` → `subscriptions/listen` migration, with a real user-facing
verification (not just "the route returns 200"):

- **Welcome** — metric strip, findings/evals summary tiles.
- **Findings** — security findings list, severity/STRIDE classification.
- **Evals** — benchmark/rubric scoring views.
- **Metrics** — live runtime telemetry from the current buffer (this tab's
  "live stream connected" indicator is DIRECTLY the thing this migration
  touches — it currently reads from a mechanism related to the internal
  event bus and MUST be independently re-verified, not inferred from
  Timeline working).
- **Graph** — knowledge graph / entity relationship exploration.
- **Timeline** — agent tool call activity, RL learning-loop events, memory
  events (the exact regression class discovered in #734's investigation —
  this migration must not reopen that; RL/memory events must remain visible
  in Timeline after the transport swap, verified explicitly, not assumed
  because the transport is "the same but MCP now").
- **ML** — fine-tuning pipelines and dataset generation views.
- **Games** — RL game arena / CTF challenge views.
- **Blockchain** — token economy / wallet / bounty views.
- **Sandbox** — Docker container / agent execution views.
- **Chat itself** (AG-UI `/ag-ui/run`) — streaming token-by-token responses,
  tool-call cards, reasoning panel, persona switching, and
  navigation-via-chat (e.g. "switch me to the metrics tab," confirmed
  working in this session's own testing) all continue to function
  unchanged. Chat streaming is explicitly NOT assumed unaffected just
  because #736 already proved AG-UI is independent of the REST bridge —
  Requirement 2 of this spec migrates `ag_ui_chat_stream.py` itself off
  `event_bus`, so chat is now IN SCOPE for this migration's blast radius
  and must be re-verified end to end (a full multi-turn conversation, not
  a single "probe ok" smoke test).
- **Cmd-K tool palette** (client-side catalog/fuzzy-resolve solution from
  #736) continues to list and invoke tools correctly.

### 4.2 — Every internal integration point

- #736's mechanical consolidation (real MCP `tools/call`/`tools/list` via
  `frontends/next-dashboard/lib/mcp-client.ts`, the retired REST bridge,
  the client-side fuzzy-resolve/catalog solution) continues to work
  unchanged after the FastMCP 4 upgrade — verified by re-running #736's
  full test suite (`bases/api/test/`, `bases/mcp_server/test/`,
  `components/ui/test/factory/ui/test_action_dispatch_real.py`,
  `frontends/next-dashboard`'s vitest suite) against the upgraded
  dependency, not assumed compatible.
- #737's design work (making MCP auth mandatory by default, relocating
  `bridge.py`'s preserved-but-inert `_extract_envelope`/
  `auth_verify_access_token` call path onto the `/mcp` transport) is
  coordinated with this upgrade's timing — if #737 lands first, its auth
  design must account for FastMCP 4's request-scoped identity model
  (`_meta.clientInfo`, `UserSession` primitives) rather than being
  redesigned twice. Sequencing between #737 and this spec is an explicit
  design-phase decision, not an accident of whichever lands first.
- `rl_smoke.py` (rewritten in #736 to use the `mcp` Python SDK's
  `streamablehttp_client`/`ClientSession` against the pinned SDK version)
  is re-verified against the upgraded SDK, since its `call_brick_tool`
  meta-tool routing pattern depends on progressive-discovery behavior that
  must not silently change.
- Every brick's own MCP-registered tool suite (`get_capabilities`,
  `health_check`, `describe_config_schema`, and each brick's operational/
  deterministic tools) continues to register and execute correctly —
  proven by running the FULL existing test suite across every brick that
  imports `fastmcp` (confirmed ~35+ bricks), not a representative sample.

### 4.3 — Explicit non-negotiable outcome

If any item in 4.1 or 4.2 cannot be kept working through this migration,
that is a STOP condition requiring an explicit design decision and
sign-off before proceeding — it is not acceptable to ship this upgrade
with a known regression to any currently-working surface, silently
documented as a "known issue" after the fact.

## Requirement 5 — AgentCore Runtime compatibility preserved

1. `RUN_MODE=agentcore` continues to deploy with `stateless_http=True`,
   matching AgentCore's own documented requirement and this repo's existing
   steering docs (`project-overview.md`). This upgrade does not make
   Companion-X's AgentCore deployment path stateful as a side effect of the
   events extension from Requirement 2 — the design must confirm the
   extension's in-process delivery model is compatible with AgentCore
   Runtime specifically (not just Companion-X's own FastAPI-mounted
   `RUN_MODE=api` path), before this is assumed to hold for both deployment
   targets identically.

## Requirement 6 — Replace `call_brick_tool`'s background-task pattern with Workflow-brick-backed durable attempts

FastMCP 4 removed `FastMCP.call_tool()`'s `task_meta` parameter entirely,
replacing background execution with a client-capability-negotiated model
(`TasksExtension`, static `@mcp.tool(task=True)` decoration, client must
declare support in request `_meta`). This repo's `call_brick_tool` meta-tool
(`bases/mcp_server/src/factory/mcp_server/runtime/progressive_invocation.py`)
accepts `as_task: bool` / `task_ttl_ms: int | None` from whatever caller
invokes it, resolves an arbitrary brick tool name at runtime, and — per
confirmed direct source testing against `fastmcp==4.0.0b3` — has no drop-in
equivalent under the new model, because the target tool is chosen
dynamically per call, not statically declared `task=True` ahead of time.

Per SME design review (strands-expert), the corrected replacement routes
through this repo's own `workflow` brick, which already owns exactly this
problem's real shape (durable attempt tracking, named-MCP tool targets,
idempotency keys, retry/terminal-outcome classification) — using an
existing first-party capability instead of fighting FastMCP 4's
client-negotiated model or inventing a second bespoke task system.

1. `call_brick_tool(as_task=True, task_ttl_ms=...)` resolves the target
   `(brick_name, tool_name)` against the Workflow brick's
   `durable_tasks.allowlist` (a `ToolTarget` registration), not against an
   arbitrary runtime-supplied name as it does today. A target not present
   on the allowlist fails closed with an explicit `TaskNotAllowlistedError`
   transport failure — background execution becomes a deliberately
   narrower capability than synchronous execution, and this narrowing is
   documented as an explicit, intentional behavior change, not a silent
   regression.
2. On an allowlisted target, the call routes through the Workflow brick's
   public interface (`factory.workflow.interface`, reached through the
   aggregator/MCP boundary — never a direct cross-brick import) via
   `Runtime.start_run(...)`, threading `task_ttl_ms` into Workflow's
   existing lease/attempt model rather than introducing a parallel TTL
   concept.
3. The returned handle replaces FastMCP's `CreateTaskResult` shape with
   Workflow's own `start_run` response, wrapped in the same
   `NativeTransportOutput` envelope `call_brick_tool` already returns for
   synchronous results — one consistent transport shape for callers, not
   two different shapes depending on `as_task`.
4. Polling and cancellation use Workflow's existing `Runtime.get_run(...)`/
   `Runtime.cancel_run(...)` — no new Workflow surface required for the
   read/cancel side.
5. The envelope/authority boundary `call_brick_tool` already enforces
   ("Public call_brick_tool cannot accept caller-supplied authority
   envelope") is preserved through this redirect — the design states
   explicitly where `Runtime.start_run`'s mandatory `envelope` argument
   comes from (the aggregator's server-side authority context), so this
   redirect cannot become a hole where a caller-controlled path bypasses
   the existing envelope restriction.
6. Storage-backend divergence is handled explicitly, not left implicit:
   Workflow's `durable_named_mcp_execution` capability is
   `sqlite-only`-documented today. Any deployment running Workflow on a
   different storage backend fails `as_task=True` closed with a clear
   error, rather than silently falling back to synchronous execution.
7. A compatibility table (old `CreateTaskResult`-based field/semantics →
   new Workflow-based field/semantics, including differing retry/idempotency
   behavior) is written into the design doc so this is discovered in
   design review, not at implementation time.
8. The single existing test exercising this pattern
   (`bases/mcp_server/test/factory/mcp_server/test_native_dispatch_compat.py`)
   is rewritten against the new Workflow-backed behavior, not left
   asserting the retired `CreateTaskResult`/`task_meta` shape.

## Requirement 7 — Full test coverage for every consuming surface, not just the transport swap

Per explicit user instruction: this spec covers everything that consumes
the upgraded surfaces, including test infrastructure — not just the
production code paths.

1. **Pydantic v2 ingress/egress contracts.** Every brick's typed
   `input_model`/`output_model` boundary (the `@operational`/`@deterministic`
   decorator pattern already standard across this repo's MCP tools) is
   re-verified against FastMCP 4's tool-registration surface — confirm
   FastMCP 4 does not change how it introspects/validates Pydantic v2
   models passed to `@mcp.tool()`, since this repo's entire typed-contract
   discipline (the same discipline the user applied repo-wide before this
   spec even started) depends on that introspection behavior staying
   intact. Any brick whose contract validation behavior changes under
   FastMCP 4 is named explicitly, not discovered via a failing test with no
   root-cause explanation.
2. **Hypothesis property tests.** Existing property-based tests exercising
   FastMCP-adjacent behavior (confirmed present: `bases/mcp_server/test/factory/mcp_server/test_core.py`,
   `test_core_brick_selection.py`, `test_instrumentation_properties.py`,
   `test_flat_view.py`, `test_graph_sink.py`, and others under
   `bases/mcp_server/test/`) are re-run against the upgraded dependency and
   pass unchanged. New Hypothesis property tests are written for the two
   pieces of genuinely new logic this spec introduces:
   - The Requirement 2 events extension's fan-out (publish → N subscribers,
     zero-subscriber no-raise behavior, ordering under concurrent publish)
     — mirroring the existing property-test style already used for
     `event_bus`'s own current behavior (`components/mcp_utils/test/factory/mcp_utils/test_event_bus_properties.py`
     is the existing precedent to extend, not abandon).
   - The Requirement 6 Workflow-redirect's allowlist-gating logic (allowlisted
     targets succeed, non-allowlisted targets fail closed, `task_ttl_ms`
     correctly threads into Workflow's lease model across a range of
     generated inputs).
   - A named test proving the Workflow redirect cannot become a hole in
     `call_brick_tool`'s existing envelope-authority boundary — mirroring
     the existing `UntrustedEnvelopeError` test for synchronous
     `call_brick_tool` calls, applied to the `as_task=True` path
     specifically, not just implied by the general allowlist-gating tests.
   - A named test proving the storage-backend fail-closed behavior
     (Requirement 6.6): `as_task=True` against a non-sqlite Workflow storage
     backend fails closed with a clear error, with no silent fallback to
     synchronous execution.
   - The Workflow redirect (Phase 0.5) is exercised at least once under
     `RUN_MODE=agentcore` specifically, not only under the default/API run
     mode — Requirement 5 already requires this for the events extension;
     this bullet extends the same AgentCore-mode verification to the
     Workflow redirect, since it also runs under every `RUN_MODE`.
3. **Every dependent test suite named in Requirement 4.2 and elsewhere in
   this document** (`bases/api/test/`, `bases/mcp_server/test/`,
   `components/ui/test/factory/ui/test_action_dispatch_real.py`,
   `frontends/next-dashboard`'s vitest suite, `components/mcp_utils/test/`,
   `components/events/test/`, `components/workflow/test/`) is run in full
   against the final state of every phase in the design doc's phased
   rollout — not just once at the very end. A regression introduced in
   Phase 1 and only caught in a final Phase 4 test run is exactly the
   failure mode this requirement exists to prevent.
4. `foreman_guardian_check`'s `mcp_contracts` check (informational today,
   `base_sha`-ratcheted per the design doc) is run at each phase boundary
   with the pre-phase commit as `base_sha`, so new contract violations
   introduced by this spec's own new code (the events extension, the
   Workflow-redirect code) are caught immediately — this repo's existing 82
   file-size violations and legacy contract findings remain explicitly not
   this spec's problem to fix, but new code written for this spec holds to
   the strict standard from day one, per Requirement 3.3 (Phase 1 gate)'s
   existing 200-LOC/typed-model commitment.

## Constraints

- No implementation proceeds until final design/architecture review
  (meta-architect) and Strands/MCP-ecosystem review (strands-expert)
  approve the design doc — same gate #736/#737/#739 went through.
- No implementation begins on the `subscriptions/listen` migration (Requirement 2)
  until the FastMCP 4 dependency upgrade itself (Requirement 1) is
  independently verified — do not conflate "upgrade the dependency" and
  "migrate the internal transport" into one unreviewable change.
- Do not remove `event_bus`/`tool_event_stream.py` until Requirement 3's
  equivalence proof is complete and explicitly signed off — not on a
  timeline, on evidence.
- This spec explicitly excludes onboarding external MCP clients or
  enabling unsolicited push from outside Companion-X (that is #739,
  parked pending this spec landing).
