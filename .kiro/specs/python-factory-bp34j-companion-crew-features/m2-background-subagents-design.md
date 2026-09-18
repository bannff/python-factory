# M2 Design — Durable Background Subagents

**Epic:** `python-factory-bp34j`  
**Milestone:** M2 — Durable, visible background subagents  
**Research:** upstream contract `d4d00d71`; Factory gap map `81829b20`  
**Pre-implementation review:** `bc51f5d9` — APPROVE_WITH_NOTES

## Goal

A Companion-X turn can launch background Agent work that Workflow durably owns. The work remains observable, cancellable, retryable, restart-reconcilable, steerable with M1 truth guarantees, and reports completion exactly once to its originating Session.

UX polish and final visual acceptance remain M7 work.

## Upstream behavior to preserve

Port behavior, not KiroCrew's process/CLI architecture:

- assign one stable run ID before admission
- persist run identity before announcing launch
- preserve partial output and nested tool/node events
- terminal outcomes are `ok | failed | stopped | interrupted`
- cancellation is neutral and exactly once
- transient retry never blindly duplicates post-tool side effects
- restart reconciles every nonterminal run
- completion reaches the origin session exactly once; failed delivery remains pending
- live steer is consumed only with positive boundary evidence, otherwise requeued once

## Existing Factory rails

- **Workflow** already owns durable runs, attempts, retry, cancel, resume, CAS, and named-MCP execution enrollment.
- **Agent** already launches managed registered graphs and executes attempt-scoped LangGraph work.
- **Session** already owns owner-scoped session identity and exactly-once delivery/CAS patterns.
- **Events/UI** already carry Workflow/node events into AG-UI activity snapshots and existing CopilotKit sub-agent containment.
- **Notification** remains the general alert channel; it does not replace origin-chat delivery.

Inline `spawn_subagent`, `spawn_swarm`, and `spawn_graph` remain valid bounded within-turn composition. The in-memory threaded async tool is not a durable M2 rail and must not back background work.

## Ownership decisions

### Workflow owns background lifecycle

A background subagent is a Workflow run, not an Agent task registry. Workflow owns:

- run/attempt state and terminal reason
- global retries and retryability
- cancellation and resume
- restart reconciliation
- exactly-once terminal transition

### Agent owns attempt execution

Agent owns:

- resolving the registered persona
- building the single-node LangGraph attempt
- model/tool execution and checkpoint state
- emitting nested execution evidence
- model-boundary steer acknowledgement

Agent does not own a second durable run ledger.

### Session owns origin delivery state

Workflow freezes the verified `origin_session_id` with the run input. Session owns a small owner-scoped completion-delivery record keyed by `(session_id, run_id)` with DB uniqueness and revision CAS. Agent projects delivered completion into its transcript; live AG-UI delivery is an optimization, never the sole durable path.

## Minimal MCP surface

All ingress is strict brick-local Pydantic; all egress is typed `ToolResult`.

Agent:

- `agent_spawn_background` — operational; verifies persona and origin context, then enrolls one Workflow run

Workflow existing tools remain authoritative for:

- status/list
- cancel
- resume/retry

Session extension later in M2:

- deterministic list/get completion delivery
- Agent/Workflow service-only write/ack using a closed exact binding

No new background-subagent brick is needed.

## Durable launch contract

1. Resolve verified tenant/owner/session from the ambient invocation.
2. Validate the requested registered persona and bounded task.
3. Mint/freeze one run key before enrollment.
4. Freeze persona ID, task, origin session, capability scope digest, and correlation in Workflow input.
5. Enroll through existing `workflow.enroll_execution`; never create a daemon thread.
6. Return the durable Workflow run identity immediately.
7. Execute a deterministic one-node Agent graph through the existing Workflow→Agent service boundary.
8. Emit nested node/tool events under the Workflow run ID.

Duplicate launch idempotency returns the same authorized run.

## Restart and terminal contract

On API startup, Workflow finds nonterminal managed background runs and revision-fences one reconciliation action per run:

- resumable checkpoint → resume/step
- terminal attempt evidence → finalize
- irrecoverable interruption → `interrupted`

Terminal completion uses one DB-authoritative claim. Session delivery insertion is unique by owner/session/run. A live event may render immediately, but pending delivery survives restart until Agent acknowledgement.

## Steering contract

Reuse M1 semantics and machinery; do not invent a second truth model:

```text
written → consumed | requeued
```

A background run exposes its Agent checkpoint/thread binding through trusted Workflow metadata. `consumed` requires positive Agent model-boundary acknowledgement. Turn/run termination requeues still-written input once through revision CAS.

## Implementation slices

1. **Durable launch spine:** one registered persona → one-node Agent attempt → Workflow enrollment; return/status/cancel tests.
2. **Restart reconciliation:** startup sweep resumes or terminally interrupts every active background run exactly once.
3. **Origin completion:** durable Session delivery keyed by run ID, exactly-once live/pending delivery.
4. **Attempt steering:** M1 mailbox semantics bound to the active background attempt.
5. **Event integration:** bind existing nested AG-UI activity to Workflow run IDs; UX polish remains M7.

## First-slice acceptance

- background launch returns before execution completes
- Workflow is the only durable run ledger
- same idempotency key cannot create two runs
- status observes queued/running/terminal state
- cancel reaches the exact Agent attempt and preserves terminal evidence
- restart-oriented inputs contain verified origin session and persona identity
- no daemon thread, KiroCrew process model, ADK, or `kiro-cli`
- affected tests and Guardian pass; files stay under 200 lines

## Deferred to later M2 slices

Completion injection, startup recovery, attempt steering, and AG-UI rebinding are required for M2 closure but intentionally excluded from slice 1. Final presentation and new-user review remain M7.
