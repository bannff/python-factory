# Workflow Engine Adapter Portability — Tasks

> Implement in order. Do not claim Celery/Dagster managed-engine support until their adapter passes the common lifecycle contract.

## 0. Baseline and contract freeze

- [ ] 0.1 Claim a dedicated Bead. Record the current managed Strands route and the separate legacy `TaskExecutor` Local/Celery/Dagster path; do not close or alter unrelated Beads.
- [ ] 0.2 Capture strict MCP/API snapshots for Agent graph launchers and Workflow lifecycle results: input/output schemas, durable IDs, Graph/OTel evidence, status/cancellation payloads, and service-only visibility.
- [ ] 0.3 Add a black-box execution lifecycle contract harness parameterized by scheduler adapter. It must cover enrollment/replay conflict, start, status, success/failure, provider evidence, duplicate events, terminal fencing, cancellation, retry, and recovery.
- [ ] 0.4 Add a test-only `probe_compute` capability provider with a distinct opaque descriptor and private service-only execute/cancel endpoints. Run the same caller → Workflow → scheduler → provider → evidence transcript as Agent/Strands graph; it must require no Workflow provider/domain branch.
- [ ] 0.5 Add static tests proving Agent callers and public Workflow schemas contain no scheduler selector/configuration and that Workflow core does not branch on scheduler/provider IDs.

## 1. Separate semantic capabilities from scheduler routes

- [ ] 1.1 Introduce frozen typed `ExecutionCapabilitySpec`, `SchedulerAdapterSpec`, `ExecutionRouteSpec`, and persisted `ExecutionRouteSnapshot` models; split files before exceeding 200 LOC.
- [ ] 1.2 Evolve trusted settings/configuration so a project maps an allowed capability to one scheduler adapter. Validate duplicate/unknown/incompatible routes and fail before tool registration; preserve a compatibility migration for current `strands_graph` registrations.
- [ ] 1.3 Change neutral enrollment so callers submit a capability ID plus opaque descriptor/digest—not a scheduler choice. Resolve and persist the full route snapshot, including route/capability/scheduler digests and allowed targets.
- [ ] 1.4 Preserve run-key replay semantics: same tenant/principal/session/run key and identical frozen inputs returns the same run; any divergent descriptor, capability, route snapshot, or digest conflicts before scheduler invocation.
- [ ] 1.5 Update capabilities/health/config-schema projections to report only trusted configured routes without exposing secrets. Add strict DTO/schema tests.

## 2. Create the generic scheduler port and in-house reference adapter

- [ ] 2.1 Define `ExecutionSchedulerPort` plus typed command, native-handle, observation, cancellation acknowledgement, and bounded evidence models. The command carries the complete owner tuple, frozen route, and deterministic provider effect key; no Strands/Celery/Dagster field belongs in the generic models.
- [ ] 2.2 Add a durable pre-dispatch/outbox record and `ensure_started` / `lookup_by_effect_key` contract. Prove exactly-once native submission/reattachment across crash before submit and crash after submit before native-handle receipt persistence.
- [ ] 2.3 Refactor the current named-MCP managed path into the `inhouse` scheduler adapter without changing existing Strands durable IDs, public results, Agent launch behavior, Graph evidence, or service-only semantics.
- [ ] 2.4 Persist the native handle/receipt and route snapshot durably. Add generic observe/reconcile operations for nonterminal external-style adapters, with lease/revision CAS and no live-registry lookup.
- [ ] 2.5 Route generic cancellation through the frozen scheduler port after the durable fence. Preserve exact binding, idempotency, and the rule that scheduler/provider errors never reverse Workflow cancellation.
- [ ] 2.6 Run the lifecycle contract harness and Hypothesis state machine against in-house; cover process crash between route resolution, pre-dispatch persistence, native dispatch, handle persistence, evidence append, cancellation, and terminal projection.

## 3. Preserve Agent/Strands capability semantics

- [ ] 3.1 Keep Agent graph launchers on one neutral `workflow.enroll_execution` path. Remove any caller-visible infrastructure choice while preserving the typed semantic `strands_graph` capability and manifest binding.
- [ ] 3.2 Keep `execute_strands_graph_attempt` / `cancel_strands_graph_attempt` private provider endpoints. Verify they receive the full frozen command binding from every scheduler and remain inaccessible from public MCP/API routes.
- [ ] 3.3 Add regressions proving conditional graph edges, nested Graph/Swarm, tool scoping, session restoration, per-node streams, graph-local retry, and result projection work unchanged through the in-house adapter.
- [ ] 3.4 Prove inner Strands retries do not create a new Workflow attempt, while an outer retry does. Assert evidence remains ordered and bound to the correct revision.

## 4. Add Celery as a contract-complete scheduler adapter

- [ ] 4.1 Build a fake Celery transport and run the full generic lifecycle suite before adding real broker integration.
- [ ] 4.2 Implement Celery `start`: submit one idempotent whole-command job, persist its native task ID only after durable binding validation, and invoke the frozen capability provider using broker/signed credentials.
- [ ] 4.3 Implement Celery `observe/reconcile` and `request_cancel`; map native facts to canonical Workflow observations, validate callback/status identity against the frozen handle, and reject stale/tampered/cross-tenant events.
- [ ] 4.4 Configure or prove transparent Celery retry behavior so it cannot create untracked logical execution attempts or duplicate terminal evidence.
- [ ] 4.5 Add broker-backed integration tests behind an explicit opt-in environment marker, including worker loss/restart, duplicate delivery, revoke races, and recovery without changing `workflow_run_id`.

## 5. Add Dagster as a contract-complete scheduler adapter

- [ ] 5.1 Build a fake Dagster transport and run the identical generic lifecycle suite.
- [ ] 5.2 Implement Dagster `start`: launch one whole-command run, persist its native run ID after durable validation, and run the frozen capability provider through trusted adapter credentials.
- [ ] 5.3 Implement Dagster `observe/reconcile` and `request_cancel`; distinguish acknowledgement/cancel-in-progress from confirmed terminal cancellation, fence stale responses, and emit normalized evidence.
- [ ] 5.4 Add opt-in real-Dagster integration coverage for launch, restart/reconciliation, terminate races, status mapping, duplicate observations, and stable public Workflow identity.

## 6. Migrate and retire the legacy executor path safely

- [ ] 6.1 Document and instrument `task_mode: executor` / `executor.backend` as legacy compatibility. Do not route new Agent managed graphs through it.
- [ ] 6.2 Add a migration inventory/report for legacy executor workflows and prove legacy runs retain their existing behavior while new managed routes use only the scheduler port.
- [ ] 6.3 Provide explicit configuration migration from legacy selected backends to route selection; do not silently reinterpret legacy settings as a scheduler route.
- [ ] 6.4 Deprecate executor-specific tools/settings only after telemetry and project migrations demonstrate no dependent managed callers. Schedule removal as a separate breaking-change decision.

## 7. Final acceptance

- [ ] 7.1 Run the common contract suite plus Hypothesis state machine against in-house, fake Celery, and fake Dagster.
- [ ] 7.2 Prove Agent/Strands graph and test-only `probe_compute` follow identical caller → Workflow → selected scheduler → provider → evidence behavior without domain/provider branches.
- [ ] 7.3 Run Workflow, Agent, MCP gateway/service-only, Dataset manifest, frontend Graph-tab/Timeline, and relevant API suites; run production scans, `compileall`, `git diff --check`, and `foreman_guardian_check`.
- [ ] 7.4 Obtain Meta Architecture, security, QA, and Strands review after implementation. No commit, push, or Bead closure occurs without explicit user direction.
