# Workflow Engine Adapter Portability — Requirements

> Status: proposed. Reviewed by Meta Architecture and Strands SMEs.
> Scope: make execution **scheduling frameworks** project-selectable without changing callers such as Agent graph launchers.

## Introduction

A brick that asks Workflow to execute work must use one neutral lifecycle. The caller expresses **what capability it needs executed** (for example, a frozen Strands graph); it must never select or understand whether the project dispatches that capability through the in-house durable runner, Celery, Dagster, or a future scheduler.

The current `ExecutionEngineSpec` path proves the durable workflow/Strands route but conflates a semantic provider (`strands_graph`) with its dispatch mechanism and leaves legacy `TaskExecutor` Celery/Dagster/Local paths outside it. This specification completes the port/adapter boundary.

```text
Agent or any capability brick
  → neutral Workflow MCP lifecycle
  → trusted project route selection
  → scheduler adapter: in-house | Celery | Dagster | future
  → private capability provider: Agent executes frozen Strands graph
```

## 1. Non-negotiable caller contract

1. Public and cross-brick callers SHALL use only the neutral Workflow lifecycle: enrollment, run/status retrieval, cancellation, recovery, and evidence views. Agent graph launchers SHALL continue to make exactly one Workflow enrollment call and SHALL not call Celery, Dagster, scheduler-specific MCP tools, or provider submission APIs.
2. A caller MAY identify a typed semantic execution capability it owns, such as `strands_graph`, and provide its opaque frozen descriptor and digest. It SHALL NOT supply a scheduler/framework selector (`inhouse`, `celery`, `dagster`, queue, broker URL, code location, provider-native run ID, or equivalent).
3. The public Workflow result shape—durable run ID, attempt ID/revision, status, terminal reason, cancellation result, and evidence access—SHALL be invariant across selected schedulers. Provider-native IDs and states are diagnostic bounded evidence only.
4. Existing public Agent graph tools (`spawn_graph`, `spawn_registered_graph`, and their public launch paths) SHALL preserve their request/response and Graph-tab behavior. Switching a project scheduler SHALL require configuration only, not an Agent caller change.

## 2. Trusted composition and selection

1. Project/server configuration SHALL select a scheduler route for each allowed semantic capability. The selected route is trusted startup composition, validated before tools are served; no MCP request, envelope, or caller input may select routing.
2. The configuration model SHALL distinguish:
   - **capability provider:** the semantic owner that executes a frozen capability, initially Agent/Strands graph;
   - **scheduler adapter:** the transport/scheduling framework that dispatches, observes, reconciles, and cancels that capability, initially in-house, then Celery and Dagster.
3. Each enrollment SHALL snapshot the complete resolved route: capability ID/version, private provider targets, scheduler adapter ID/version/capabilities, allowed targets, normalized outcome policy, and all registration/request/provider digests. Recovery and cancellation SHALL use only this snapshot, never mutable live configuration.
4. Invalid, duplicate, unavailable, or incompatible capability/scheduler routes SHALL loud-fail at startup. There is no fallback to Local, Celery, Dagster, or the in-house adapter.
5. Provider secrets and deployment configuration (broker URLs, queue names, Dagster code locations, credentials) SHALL remain trusted scheduler configuration or secret-adapter data. They SHALL not appear in caller requests, public responses, frozen artifacts exposed to callers, Graph evidence, or logs.

## 3. Neutral execution adapter port

1. Workflow SHALL define a provider-neutral scheduler port with operations equivalent to `start`, `observe/reconcile`, and `request_cancel`, plus declared capabilities. Implementations are adapters for in-house, Celery, Dagster, and future schedulers.
2. The port SHALL carry the exact durable owner tuple: `workflow_run_id`, `attempt_id`, `revision`, capability ID, route/registration digest, request digest, and provider-request digest. Provider effect keys derive deterministically from this tuple.
3. Start SHALL be crash-safe. Workflow SHALL durably create a pre-dispatch/outbox record keyed by the owner tuple and deterministic provider effect key before native submission. A scheduler SHALL implement idempotent `ensure_started` and lookup/reconciliation by that effect key, so a crash before submit does not create work and a crash after submit but before receipt persistence reattaches the original native handle rather than submitting another job.
4. A scheduler adapter dispatches the **whole frozen capability attempt**. It SHALL not decompose a Strands graph into scheduler-managed node tasks, reinterpret graph topology, prompts, models, tools, sessions, or graph-local state.
5. Provider adapters own translation between the scheduler-neutral contract and their native submission/query/cancel APIs. Workflow core SHALL not import scheduler SDKs, parse native IDs, or branch on scheduler/capability strings.
6. The old `TaskExecutor` Local/Celery/Dagster path remains a temporary explicit compatibility path only. It SHALL not be presented as equivalent to the new route until it conforms to this port and durable contract. New managed execution SHALL use the neutral route.

## 4. Lifecycle, retry, recovery, cancellation, and evidence

1. Workflow owns canonical durable state, global budgets, outer retries, attempt/revision fencing, stopping rules, terminal reason, idempotency, recovery, and the append-only evidence journal.
2. Capability providers retain inner semantics. Agent/Strands owns graph construction, tool/model/node-local retries, graph-local session/checkpoint behavior, node streaming, and result projection. An inner retry SHALL NOT create a new Workflow attempt.
3. Schedulers SHALL not create untracked logical retries. Celery/Dagster automatic retries must be disabled for logical attempts or proven transparent so they cannot duplicate work/evidence or increment logical attempt identity.
4. External/asynchronous schedulers SHALL persist a native handle bound to the exact owner tuple and support generic observation/reconciliation after restart. Workflow may not re-submit a distinct native job merely because its process restarted.
5. Workflow wins the durable cancellation fence before a best-effort scheduler signal. A scheduler acknowledgement (`cancel_requested`, `already_requested`, `not_owner`, `not_found`, transport failure) never reverses Workflow cancellation.
6. Provider and scheduler evidence SHALL be append-only, sequence-monotonic, bounded/redacted, and bound to the exact tuple. Duplicate evidence is accepted only when its digest matches; stale, cross-tenant, tampered, out-of-order, or post-fence events are rejected.
7. Canonical public states SHALL be scheduler-independent. Native states such as Celery `RETRY` or Dagster `CANCELING` are retained only as diagnostic metadata; they do not independently decide a terminal Workflow state.

## 5. Security and tenancy

1. Scheduler/provider handoffs remain private `@service_only` operations protected by exact caller-bound claims and the complete execution binding. Discovery hiding is not authorization.
2. Remote/out-of-process adapters SHALL use a broker- or signed-credential-based trusted adapter. A caller-name string is insufficient authorization outside trusted in-process composition.
3. Idempotency is tenant/principal/session scoped and bound to frozen request material. Same key plus divergent input conflicts without provider invocation; cross-tenant or cross-principal replay is denied.
4. Provider-native callbacks, task IDs, statuses, callback URLs, and envelope fields are untrusted until validated against the persisted attempt snapshot and authorization policy.

## 6. Compatibility, migration, and acceptance

1. Existing Strands managed runs retain durable IDs and Graph/OTel behavior through migration. Historic evidence remains readable through additive migration.
2. Existing legacy executor workflows remain supported during migration but are marked deprecated in capabilities/docs; no project may claim Celery/Dagster managed-engine support until the relevant adapter passes the common contract suite.
3. The implementation SHALL provide test adapters for in-house, Celery, and Dagster and run the same black-box lifecycle suite against each: enrollment, success/failure, status, cancellation races, duplicate/replay, retry, crash/recovery, evidence ordering, and terminal fencing. It SHALL explicitly cover crashes before native submission and after native submission but before native-handle receipt persistence.
4. Acceptance SHALL prove two unrelated capability providers use the identical caller → Workflow → selected scheduler → provider → evidence path without provider/domain branches in Workflow. In addition to Agent/Strands graph, the implementation SHALL add a test-only `probe_compute` capability provider with its own opaque descriptor, private service-only execute/cancel endpoints, and no graph semantics.
5. Completion requires focused and full affected suites, Hypothesis state-machine coverage of lifecycle interleavings, frontend Graph-tab regression tests, `git diff --check`, and `foreman_guardian_check` with no introduced violation.
