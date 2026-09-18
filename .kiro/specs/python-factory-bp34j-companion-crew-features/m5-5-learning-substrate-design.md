# M5.5 Design — Relationship Projection and Scored Dev Loops

**Epic:** `python-factory-bp34j`  
**Milestone:** M5.5 — learning substrate

## Goal
Make Memory, KB documents, Lessons, Sessions, and Workflow runs queryable as one
bounded relationship neighborhood while each brick remains its own source of
record. Score completed development-loop cycles through the existing
Events → Learning → reward fan-out and prove graph/reward durability across a
restart.

## Existing rails and verified gaps

- Graph already owns typed `Entity`, `Relationship`, and `QueryResult`, plus
  `networkx`, `persistent_networkx`, and `neo4j` adapters. Persistent NetworkX
  writes integrity-checked snapshots through Storage.
- `graph_get_neighbors` returns entities but drops connecting edges and is only
  one hop. M5.5 needs bounded k-hop entities **and** relationships.
- Events already owns typed publication, wildcard subscriptions, history, and
  handler dispatch. Dispatch is asynchronous and startup does not replay
  history automatically, so projections must be idempotent and reconcilable.
- Lessons emits lifecycle events but omits `source_ref`, `superseded_ids`, and
  run/session provenance from the payload.
- Memory emits lifecycle events inconsistently by adapter. The existing
  `reward.computed → memory.learning_stored` path is the reliable M5.5 learning
  projection because it includes a stable `memory_id` and run identity.
- KB emits no lifecycle event after durable ingest. Entity extraction writes a
  separate Neo4j representation and does not return stable entity IDs suitable
  for the generic Graph projection.
- Session emits steering events but no create/archive/completion relationship
  event. Workflow already owns terminal background and loop-cycle truth.
- Workflow emits activity through `event_emitter.emit`, but loop reconciliation
  and background completion do not publish a scoreable domain completion.
- Generic `*.completed` scoring already routes policy-matched events through
  `learning_compute_reward` and then `reward.computed` → Memory/Evals/wallet.
  Learning evaluates every registered source. `games_process_workflow_rl` is
  reached only by the self-gating ground-truth source and correctly abstains
  when a dev loop has no graph ground truth; `llm-judge` or telemetry scores the
  ordinary dev-loop report. Do not call Games directly or add a domain branch.

## Ownership

- **Memory, KB, Lessons, Session, Workflow:** persist domain records and emit
  additive lifecycle facts only after their own successful mutation.
- **Events:** transports, stores history, matches subscriptions, and dispatches;
  it does not define graph semantics or rewards.
- **Graph:** owns projection node/edge identity, idempotent materialization,
  reconciliation, and neighborhood reads across every configured adapter.
- **Agent:** performs bounded hybrid recall: vector hits → node references →
  `graph_neighborhood` → compact context. It never writes projection edges.
- **Learning:** selects and computes reward sources. **Games** remains one
  self-gating evidence source. **Workflow** emits terminal truth only.
- **Storage:** persists existing Graph snapshots, event history, Memory, and
  Evals reward records. No new database or brick is introduced.

## Canonical projection contract

Add a Graph-owned strict event ingress accepted only through an Events
subscription. It carries event/source identity, trusted tenant/principal,
optional session/run, subject type/ID, bounded explicit references, and source
revision. Unknown fields reject. Private types require complete authority.
Content, prompts, lesson/KB text, model output, and secrets never enter Graph;
only stable IDs, bounded labels/status/timestamps, and digests may be projected.

Every node-ID component is length/charset validated then canonical encoded; raw
colon-delimited concatenation is forbidden. IDs are source- and authority-scoped:

- `memory:{tenant_id}:{principal_id}:{memory_id}`
- `kb:{tenant_id}:{principal_id}:{document_id}`
- `lesson:{tenant_id}:{principal_id}:{lesson_id}`
- `session:{tenant_id}:{principal_id}:{session_id}`
- `workflow-run:{tenant_id}:{principal_id}:{run_id}`

Relationships deterministically hash tenant, principal, type, endpoints, and
source revision. Replays update/no-op. Cross-owner references reject before
mutation. `graph_neighborhood` validates the authority prefix of every seed,
visited node, and edge endpoint; foreign edges are neither returned nor traversed.
Graph reads without complete tenant/owner identity fail closed.

Initial relationships are `derived_from`, `mentions`, `learned_in`, `about_run`,
and `supersedes`. Projection never infers them; producers emit explicit typed
references and intelligent extraction first becomes a source-owned record.

## Producer additions

1. **Lessons:** emit `source_ref`, `superseded_ids`, and trusted run/session
   provenance when present.
2. **KB:** after durable ingest emit ID, authority, digest, and explicit typed
   metadata references. Defer extracted-entity events until IDs are stable.
3. **Workflow:** after durable cycle settlement emit one bounded scoreable
   completion with run/cycle authority, summaries, timing, and error rate.
4. **Memory/Session:** initially consume `memory.learning_stored`; derive
   `about_run` from Workflow's authoritative origin-session completion.

Events are additive and backward compatible; ambient MCP authority wins.

## Projection delivery and reconciliation

Public `events_publish` rejects reserved projection/reward types. Add a
service-only Events ingress whose exact caller/type policy and closed binding are
enforced through the existing caller-bound invocation-claims rail. Chat/agent
personas never receive it. The binding is derived from the source's durable
record and covers event type, authority, run/subject, revision, and payload
digest; ambient authority must match. Graph's service-only projector validates
the same attestation before idempotent writes.

Events dispatch is not a durable queue. M5.5 exposes a service-only Graph rebuild
operation and bounded Workflow page driver, exercised with immutable fixture
pages through real service identity. Production scheduling/loaders are deferred
until source bricks expose immutable change feeds; mutable list polling violates
Graph's snapshot/digest fence. No automatic recovery is claimed. Workflow owns
future retry/recovery and Scheduler owns time.

Delete/archive/supersede events tombstone nodes and incident relationships.
Reconciliation removes or tombstones records absent from authoritative sources,
and neighborhood reads exclude tombstoned nodes. Retention follows each source's
policy; Graph cannot retain a recallable private projection after source deletion.

## `graph_neighborhood`

Add one deterministic typed MCP operation:

- ingress: seed node IDs, optional relationship types, direction, `max_depth`
  1–3, node/edge caps, backend
- egress: seed IDs, sorted entities, sorted relationships, truncation flags,
  depth reached, backend/error metadata

Implement the same contract for NetworkX/PersistentNetworkX and Neo4j. Every
adapter selects the first globally sorted `(relationship id, source, target)`
candidates per hop before applying identical node/edge caps; parity tests freeze
that latitude. Traversal is breadth-first, deterministic, authority-scoped,
cycle-safe, and bounded. PersistentNetworkX inherits the read and must return
identical results after snapshot reconstruction. Keep `graph_get_neighbors`
byte-compatible.

## Hybrid recall

A LangChain `AgentMiddleware` before-model hook performs existing Memory/KB
retrieval, maps stable IDs, calls one bounded neighborhood operation, and compacts
summaries within the existing budget. It follows `LangChainLessonsMiddleware`:
unidentified or partial tenant/owner requests inject no graph context. Every seed
is canonicalized for the active tenant, owner, and persona. Neighborhood failure
degrades to existing scoped vector recall, never foreign or unscoped context.

## Dev-loop reward rail

Add policy `dev_loop.cycle.completed → source_tag: dev-loop`, but admit that event
only through the service-only trusted Events ingress. Before scoring, Events
attests `(tenant, owner, loop_id, cycle_id, workflow_run_id, settlement_revision,
report_digest)` against Workflow's durable settled cycle. Fabricated, foreign,
unsettled, or digest-mismatched cycles abstain. Direct public publication of
`dev_loop.cycle.completed`, `reward.computed`, and `memory.learning_stored` is
rejected; internal publishers use exact caller/type claims.

Reuse generic dispatch and `learning_compute_reward`; no scorer is added. The LLM
judge uses the attested bounded report and telemetry may contribute. Games remains
Learning's self-gating source and may abstain without ground truth.

Reward and Memory idempotency keys include tenant, owner, loop ID, durable cycle
ID, settlement revision, and policy/profile version. Distinct cycles therefore
score independently while reconciliation reuses the same key. Event history is
not the dedup ledger. Durable Evals/Memory writes own idempotency, and Workflow
records a reward-dispatch receipt only after required durable writes succeed;
reconciliation retries until that exact receipt exists.

## Acceptance and tests

- Hypothesis: bounded graphs return only reachable same-authority nodes/edges;
  traversal is deterministic, capped, cycle-safe, rejects unsafe ID components,
  and has adapter/restart parity. A planted foreign edge is never traversed.
- Contract tests: strict projector/neighborhood ingress, typed `ToolResult`
  egress, taxonomy, unknown backend, ambient-over-explicit authority, and replay.
- Spoof tests: public/non-service protected events, fabricated/foreign run IDs,
  and >40-character fake reports produce no reward, Memory write, or wallet mint.
- Producer tests: Lesson/KB/Workflow emit content-free references only after
  persistence; delete/supersede tombstones disappear from subsequent recall.
- Cursor tests: out-of-order/duplicate records cannot advance past failed work;
  cursor and projection resume monotonically after restart.
- Restart: lesson → run → cited KB document is returned by one neighborhood call
  before and after PersistentNetworkX reconstruction.
- Reward: N cycles of one loop create N durable reward/Memory records; replay of
  each exact cycle dedupes to one using durable stores, not Event history.
- Recall: unidentified requests inject nothing; failures retain existing scoped
  vector recall and never surface another tenant/persona.
- Regression: every existing Graph, Memory, KB, Lessons, Session, Workflow,
  Events, Learning, Games, and Evals adapter/test path remains available.

## Slices

1. Typed bounded `graph_neighborhood` across Graph adapters with properties and
   restart parity.
2. Graph projector contract, deterministic IDs, service-only Events subscription,
   and idempotent reconciliation seam.
3. Additive Lessons/KB/Workflow lifecycle references; project the acceptance
   lesson → run → KB chain.
4. Agent hybrid-recall middleware composition.
5. Durable dev-loop completion policy, reward acknowledgement/reconcile, and
   restart acceptance; then Gate 0 + Gate B.
