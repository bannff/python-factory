# M4 Design — Durable Goal and Monitor Loops

**Epic:** `python-factory-bp34j`  
**Milestone:** M4 — goal and monitor loops  
**Upstream research:** `b0933580`  
**Factory gap map:** `2e4f8585`

## Goal

A user starts a bounded goal or monitor loop. Each cycle is one durable Agent→Workflow attempt admitted by a Scheduler one-shot. Workflow persists the aggregate, decides whether another cycle may run, survives restart, reports one blocker once, and halts deliberately.

Dashboard timelines and final visual acceptance remain M7 work.

## Ownership

- **Workflow owns the loop aggregate:** cycle ledger, bounds, dispositions, blocker deduplication, recovery, and terminal reason.
- **Scheduler owns time:** it persists and fires exactly one one-shot schedule for each admitted cycle.
- **Agent owns intelligence:** it performs one cycle and returns a strict cycle report.
- **API BackgroundTaskOwner owns polling task lifetime:** no daemon thread or second runtime.
- **Events/Notification project evidence:** they never determine loop truth.

No `goal`, `monitor`, or KiroCrew mega-brick is added. Scheduler does not gain stopping logic.

## Why one-shot schedules

A recurring schedule can race a stop condition or launch overlapping work. Workflow instead creates one deterministic one-shot schedule only after it decides the next cycle is admissible. The chain is:

1. Workflow persists loop and pending cycle N.
2. Workflow asks Scheduler to add one-shot `loop_<loop-id>_<N>`.
3. Scheduler fires through existing Agent background launch.
4. Agent/Workflow execute one durable child run.
5. Workflow reconciles Scheduler fire → child run → strict cycle report.
6. Workflow settles cycle N exactly once.
7. If allowed, Workflow persists cycle N+1 before scheduling its one-shot.

A crash at any edge replays deterministic IDs and revision-CAS state.

## Why a Workflow-local aggregate is still required

Existing Workflow run/step/task-journal CAS remains the sole ledger for executable attempts. Its graph is frozen at enrollment and the runner is deliberately capped at 25 transitions; `wait_for_event` waits inside that immutable graph and cannot append an unbounded or dynamically stopped next cycle. `LoopRecord` and `LoopCycleRecord` therefore store only aggregate policy and child-run linkage—not provider attempts, retries, task outputs, or a second execution ledger. Every executable cycle remains an ordinary child Workflow run using the existing run/step/task journal. The loop tables reuse Workflow's SQL/CAS conventions because cyclic policy state is not representable in a frozen child graph.

## Models

`LoopRecord`:

- tenant, owner, loop ID, origin Session/thread, agent ID
- kind: `goal | monitor`
- bounded objective and cycle instructions
- interval seconds, max cycles, optional runtime deadline
- full frozen originating RuntimeInvocation envelope; never a synthetic service identity
- server-computed stop sentinel and trusted project-root digest
- state: `active | paused | succeeded | blocked | stopped | exhausted | failed`
- terminal reason, next cycle, last settled cycle, blocker digest
- revision and timestamps

`LoopCycleRecord`:

- owner/loop/cycle identity
- deterministic schedule ID and one-shot timestamp
- state: `pending | scheduled | running | settled`
- Scheduler fire sequence, Workflow child run ID
- disposition: `continue | success | blocked | failed`
- bounded summary/evidence and blocker digest
- revision and timestamps

DB uniqueness covers `(tenant, owner, loop, cycle)`, schedule ID, and child run ID.

## Strict Agent cycle report

Agent adds `loop-cycle-report-v1` to its existing closed `graph_output_models` registry. Loop-created Scheduler records carry two closed launch options: `output_schema="loop-cycle-report-v1"` and `delivery_mode="workflow_loop"`. Scheduler persists and forwards them without interpreting loop semantics. Agent's one-node `persona_graph` assigns the registered schema to `AgentNodeRef.output_schema`; the existing durable graph executor validates and stores `structured_outputs`. Workflow settles only from that authoritative child-run result path—never from caller-supplied report data.

```json
{
  "disposition": "continue|success|blocked",
  "summary": "bounded evidence summary",
  "blocker": "optional bounded blocker",
  "evidence": ["bounded references"]
}
```

The cycle prompt always includes the north-star, roadmap, and task-ledger references plus the cycle number and objective. Goal loops advance one highest-leverage item. Monitor loops observe first and act only when required; uncertain observation may spend a cycle rather than silently stall.

Malformed, absent, or schema-invalid output fails the child attempt and cannot settle a disposition. `delivery_mode="workflow_loop"` makes Agent freeze `launch_metadata.kind="workflow_loop_cycle"`; M2 Session completion projection continues to select only `background_subagent`, so internal cycles do not inject N completion messages into the origin chat. The loop reconciler is the sole aggregate completion projector and distinguishes children by immutable `(loop_id, cycle, kind)` launch metadata.

## Admission and settlement protocol

1. `workflow_start_loop` validates ambient owner identity and persists cycle 1.
2. Reconciler claims pending cycle N by revision CAS.
3. It calls caller-bound `scheduler_add` with deterministic one-shot schedule ID.
4. Replays get the same schedule; conflicts are re-read and verified.
5. Reconciler reads `scheduler_get_fire`; once enrolled it stores child run ID by CAS.
6. It reads the authoritative child Workflow state and schema-validated `structured_outputs`; no public tool accepts a disposition.
7. Settlement requires exact stored tenant, owner, origin envelope, loop ID, cycle, schedule ID, child run ID, and expected revision. Sequence gaps, cross-owner runs, mutable metadata, and duplicate-but-different reports fail closed.
8. Settlement CAS records one disposition and increments the loop counter once.
9. Success/blocked/bound/stop-file terminalizes the aggregate; otherwise N+1 is persisted.

The reconciler never executes a model and Scheduler never evaluates a disposition.

## Stopping rules

Evaluated before initial admission and before scheduling a pending cycle as: stop file, max cycles, runtime deadline. After a child settles, stop file remains first, then the authoritative success/blocked/failed disposition, then cycle/runtime bounds. This preserves a real success on the final allowed cycle while still preventing one extra admission.

Bounds never buy one extra cycle. `max_cycles=0` may mean unlimited only when explicitly requested; defaults remain bounded.

## Stop-file security

The stop path is server-computed as `.companion-loop-stop-<loop_id>`; ingress accepts no path, project root, or filename. The root comes only from trusted deployment configuration, must resolve beneath an allowlisted workspace root, and is frozen with the loop. At each admission boundary runtime resolves the parent exactly and uses `lstat` on the deterministic child: any directory entry—including a symlink—is treated as a stop, and content is never opened or followed. Missing/invalid root, escaped parent, or I/O ambiguity fails closed. A sentinel appearing after admission stops the loop at the next boundary; already-admitted Workflow work follows ordinary cancellation policy.

ARCC must be queried before implementation. If unavailable, use the established exact-binding/fail-closed approach and record the outage.

## Blocker once

On first blocked settlement, Workflow stores a canonical digest and terminalizes in the same transaction. Event and notification idempotency keys derive from `(loop_id, blocker_digest)`. Recovery may retry projection, but repeated reconciliation cannot create a second blocker record or distinct key.

## MCP surface

Add strict Workflow-local Pydantic v2 contracts and typed `ToolResult` egress.

Deterministic:

- `workflow_get_loop`
- `workflow_list_loops`
- `workflow_get_loop_cycle`

Operational:

- `workflow_start_loop`
- `workflow_pause_loop`
- `workflow_resume_loop`
- `workflow_stop_loop`

Cycle settlement is Workflow-internal after authoritative child output; no public caller may assert success.

## Runtime activation

API lifespan starts one bounded Workflow loop reconciler through `BackgroundTaskOwner`, alongside existing Workflow recovery and Scheduler ticking. Startup scans active loops and resumes pending/scheduled/running cycles through durable claims. Shutdown cancels deterministically.

## Acceptance

- Three admitted cycles produce three deterministic Scheduler one-shots and three distinct child Workflow runs.
- Replaying any reconciliation edge produces no duplicate schedule, fire, child run, settlement, blocker, or notification.
- Fresh runtimes over the same SQLite databases continue from cycle N.
- Stop file present before a due cycle prevents that cycle from being scheduled.
- Max cycles and runtime deadline halt without one extra attempt.
- Success and blocked reports terminalize with distinct reasons.
- Repeated blocker observation emits one durable blocker and one idempotency key.
- Monitor no-change continues without false success; uncertainty cannot silently stop it.
- Owner/tenant crossing and arbitrary stop paths fail closed.
- Hypothesis proves cycle monotonicity, CAS fencing, and no-cycle-after-terminal.

## Slices

1. Workflow loop/cycle models, SQL persistence, stopping evaluator, Hypothesis properties.
2. Deterministic Scheduler one-shot admission and restart reconciliation.
3. Child Workflow output settlement, success/bounds, blocker-once projection.
4. Typed MCP and API task-owner activation; acceptance restart proof.
5. Minimal chat-operable integration; final visual/page UX deferred to M7.
