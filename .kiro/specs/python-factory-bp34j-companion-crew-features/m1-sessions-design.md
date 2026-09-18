# M1 Design — Persistent Sessions and Live Steering

**Bead:** `python-factory-bp34j.2`  
**Research:** KiroCrew contract `5796a1f9`; factory gap map `6b4b3ab7`

## Goal

Users can create, list, resume, rename, archive, and switch durable Companion-X sessions. A message sent while a session is working is consumed at the next safe model boundary or visibly requeued exactly once—never lost, duplicated, or overstated.

## Current truth

- `thread_id` already flows CopilotKit → AG-UI → Agent → LangGraph.
- Agent keys checkpoints by `agent_id-thread_id` but uses process-local `InMemorySaver`.
- LangGraph already provides checkpointer, state, interrupt, and resume seams.
- Storage already provides document persistence; Workflow provides CAS/idempotency patterns.
- Companion-X has no durable session ledger, session CRUD MCP tools, explicit thread selector, or steering mailbox.

## Ownership

### New `session` capability brick

Owns product session state, not agent intelligence:

- session metadata and lifecycle
- session → thread identity
- checkpoint pointers and transcript metadata only; the durable LangGraph saver is the single authority for conversation messages
- live-steer mailbox and delivery state
- exactly-once requeue
- lifecycle/audit events

Owns `session` and `steer` tables through Storage's `SQLStore` port; CAS uses `UPDATE … WHERE revision=?`, modeled on Workflow. This creates no new datastore process and does not use DocumentStore's unconditional update for state transitions.

### Agent extension

Owns conversation execution:

- replace `InMemorySaver` with an official durable LangGraph saver
- bind each run to the resolved session/thread
- consume mailbox entries only at safe model boundaries
- positively acknowledge a consumed steer
- leave unconsumed entries for exactly-once requeue

Agent does not own rename/archive/list UI state.

### Companion-X

**Selected visual specification:** [`m1-session-ux.md`](m1-session-ux.md) — owner chose Option B, the collapsible session deck.

- session sidebar using KiroCrew’s proven information hierarchy and compatible icons
- explicit selected session/thread binding
- optimistic message correlation by `send_id`
- visible `written`, `consumed`, and `requeued` states
- agent-controlled navigation through CopilotKit frontend tools

## Models

`SessionRecord`:

- required `owner_id`, `tenant_id` from the authenticated envelope; absent identity denies creation
- `session_id`, `thread_id`, `title`
- `agent_id`, `model`, `mode`
- `workspace`, `project`, `origin`
- `created_at`, `updated_at`, `archived_at`
- `revision`

`SteerMessage`:

- `delivery_id` — server-generated identity
- `send_id` — client correlation id matching `^[A-Za-z0-9_-]{1,128}$` and credential-scan clean
- `tenant_id`, `owner_id`, `session_id`, `content`
- `content` capped at 32 KiB; transition events/logs carry identity/state only, never content
- `state`: `written | consumed | requeued`
- `created_at`, `consumed_at`, `requeued_at`
- `revision`

## Exactly-once contract

1. Authorize `(tenant_id, owner_id, session_id)` before any read, dedup lookup, or mutation; absent principal/tenant fails closed.
2. Persist the steer as `written` with one parameter-bound INSERT before asynchronous delivery.
3. Enforce DB-level UNIQUE `(tenant_id, owner_id, session_id, send_id)`; duplicates return existing state only after owner authorization.
4. Every transition is one named-parameter `UPDATE … WHERE tenant_id=:tenant_id AND owner_id=:owner_id AND session_id=:session_id AND delivery_id=:delivery_id AND revision=:expected_revision`, and succeeds only when `row_count == 1`.
5. Mark `consumed` only after positive Agent acknowledgement.
6. If the active turn ends without acknowledgement, transition once to `requeued`.
7. A requeued message becomes the next user turn exactly once.
8. Every transition emits a correlated event containing identity/state—not message content; no state is inferred from absence.
9. Startup reconciliation uses the same revision-fenced CAS so concurrent restarts cannot double-requeue.
10. Restart recovery leaves a visible interrupted/requeued record, never a silent stop.

A steer is a lightweight, turn-bound delivery record—not a Workflow attempt: it has no leased execution, retry budget, or multi-step lifecycle. Workflow patterns inform its CAS, but Workflow does not own the mailbox.

## MCP surface

All models are brick-local strict Pydantic DTOs (`extra="forbid"`) with typed `ToolResult` egress.

Deterministic Session tools:

- `session_get`
- `session_list`
- `session_get_steer`

Deterministic Agent extension:

- `agent_session_history` — authorizes the ambient owner through `session_get`, then reads the exact Agent-owned checkpoint key and returns strict AG-UI messages

Operational:

- `session_create`
- `session_rename`
- `session_archive`
- `session_reopen`
- `session_steer`
- `session_acknowledge_steer` — service-only operational capability restricted to the trusted Agent runtime; never chat-visible or client-callable

No authoring tools are needed for v1. Switching the selected session is client state, not a durable mutation.

Extend the existing `mcp_utils.service_bindings` closed set with `BindingKind="steer"` and a frozen `SteerBinding(tenant_id, owner_id, session_id, delivery_id, revision)`. `session_acknowledge_steer` uses `@service_only(callers={"agent"}, binding="steer")`; `binding_matches` requires every exact argument before DTO validation or state access. The client cannot mint these internal claims.

## SDK-first decisions

1. Pin latest compatible `langgraph-checkpoint-sqlite==3.1.1`; dry-run resolution keeps current LangChain/LangGraph pins and adds `sqlite-vec==0.1.9` with macOS/Linux artifacts.
2. Agent owns one long-lived `aiosqlite` connection and `AsyncSqliteSaver`, calls idempotent `setup()` once, enables WAL, and closes it on shutdown.
3. Use `AsyncSqliteSaver.alist` for one thread, `aget_tuple` for restore, and `adelete_thread` only for explicit transcript deletion. The session brick remains the all-session index.
4. Bind selected sessions through pinned CopilotKit v2's native mutable `HttpAgent.threadId` field; 1.53.0 exports no `useThreads`/`setThreadId` hook. Add no custom thread wire field.
5. Do not call concurrent `aupdate_state` during `astream`; it races checkpoint writes. Drain steering cooperatively at model/node boundaries and requeue once if the turn ends first.
6. Map client `send_id` to the standard AG-UI user-message `id`; add no custom correlation event.
7. Keep a future Postgres saver behind the same Agent-side checkpointer factory; SQLite is the local/single-node adapter.

## Failure behavior

- Missing envelope principal or tenant → deny before state access.
- Unknown or foreign-owned session → uniform typed not-found; never reveal existence.
- `session_list` and `session_history` are always tenant/owner scoped.
- Archived session rejects steer and new turns; reopen re-authorizes ownership.
- Duplicate `send_id` → return the authorized existing delivery state; no second write.
- Busy session with no safe boundary → remain `written`, then requeue once.
- Process crash → revision-fenced reconciliation of every nonterminal steer to visible requeue/interrupted state.
- Storage unavailable → fail closed; do not claim create/rename/steer succeeded.
- Checkpointer history is reachable only through an authorized session-to-thread binding; never enumerate `_thread_keys` directly.
- Frontend may optimistically create the message id, but only server transitions may assert `written`, `consumed`, or `requeued`.

## Test plan

- Pydantic strict ingress and typed egress for every MCP tool.
- Hypothesis state machine for create/rename/archive/reopen.
- Hypothesis state machine proving every steer is consumed once or requeued once.
- Duplicate `send_id`, crash windows, stale revision, and concurrent-tab tests.
- Durable checkpointer restart test with persona/history continuity.
- AG-UI test for written → consumed and written → requeued updates.
- Frontend session selection, optimistic reconciliation, and accessibility tests.
- Visual proof against KiroCrew’s session-sidebar interaction contract.

## Non-goals

- No kiro-cli/ACP directive markers, replay logs, PID sweeps, or native `/compact` commands.
- No Memory/KB consolidation.
- No remote channels or cross-device sync in M1.
- No session subprocess per chat.
