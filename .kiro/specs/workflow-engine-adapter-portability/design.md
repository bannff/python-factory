# Workflow Engine Adapter Portability — Design

> Status: proposed implementation design.
> Decision: **semantic capability and scheduler are separate axes.**

## 1. Decision

The current `strands_graph` value is a semantic capability: it means “Agent executes this frozen Strands graph.” It is not the infrastructure framework choice. Projects select the scheduler beneath that capability through trusted composition.

```text
Agent graph launcher
  └─ workflow.enroll_execution(capability=strands_graph, descriptor, digest, run key)
       └─ frozen ExecutionRouteSnapshot
            ├─ capability provider: agent.execute_strands_graph_attempt
            └─ scheduler adapter: inhouse | celery | dagster
                 └─ invokes/observes/cancels the exact frozen provider attempt
```

This replaces the present accidental model:

```text
caller-provided engine_id=strands_graph → direct named-MCP provider call
legacy executor.backend=celery|dagster → unrelated task-step path
```

The in-house adapter is a scheduler adapter, not a second semantic provider. It keeps the current direct named-MCP dispatch behavior. Celery and Dagster adapters schedule the same private Agent execution capability as a single whole-graph attempt.

## 2. Ownership

| Layer | Owns | Must not own |
|---|---|---|
| Caller brick / Agent | Frozen semantic descriptor, provider-specific intent, capability-owned inner behavior | Scheduler choice, broker/Dagster configuration, scheduler-native IDs/statuses |
| Workflow control plane | Neutral lifecycle, route resolution, durable run/attempt state, outer retry/budget, idempotency, recovery, cancellation fence, evidence ledger | Strands topology or scheduler SDK details |
| Scheduler adapter | Submit, observe/reconcile, and cancel the frozen provider attempt; map native facts to neutral contract | Canonical run/evidence authority or business/graph semantics |
| Capability provider | Execute the exact frozen descriptor and project inner evidence/result | Scheduler selection or public lifecycle ownership |

Agent remains the capability provider for Strands graphs. `execute_strands_graph_attempt` and `cancel_strands_graph_attempt` stay Agent-owned private endpoints. Celery and Dagster must not cause an Agent-visible `execute_celery_graph` / `execute_dagster_graph` surface.

## 3. Models and ports

### 3.1 Composition models

Replace the conflated selection role of `ExecutionEngineSpec` with immutable, typed composition concepts. Exact class names may differ, but their responsibilities must not.

```python
@dataclass(frozen=True)
class ExecutionCapabilitySpec:
    capability_id: str                 # e.g. strands_graph
    execute_target: ToolTarget         # Agent private execution endpoint
    cancel_target: ToolTarget | None   # Agent private cancellation endpoint
    argument_mapping: Mapping[str, str]
    outcome: TaskOutcomePolicy

@dataclass(frozen=True)
class SchedulerAdapterSpec:
    adapter_id: str                    # inhouse | celery | dagster
    adapter_version: str
    start_target: ToolTarget | None    # direct in-process implementation is allowed
    observe_target: ToolTarget | None
    cancel_target: ToolTarget | None
    capabilities: FrozenSet[str]

@dataclass(frozen=True)
class ExecutionRouteSpec:
    capability_id: str
    scheduler_adapter_id: str
    route_version: str

@dataclass(frozen=True)
class ExecutionRouteSnapshot:
    route: ExecutionRouteSpec
    capability: ExecutionCapabilitySpec
    scheduler: SchedulerAdapterSpec
    route_digest: str
```

`Settings` validates an immutable route table at trusted startup. Each project declares routes, e.g. `strands_graph → celery`; no caller-supplied request can override it. The resolved `ExecutionRouteSnapshot`, opaque descriptor, request/provider digests, and tenant/principal identity are persisted in the workflow version/attempt material.

### 3.2 Scheduler port

```python
class ExecutionSchedulerPort(Protocol):
    def ensure_started(self, command: FrozenExecutionCommand) -> SchedulerReceipt: ...
    def observe(self, command: FrozenExecutionCommand, handle: NativeHandle) -> Observation: ...
    def request_cancel(self, command: FrozenExecutionCommand, handle: NativeHandle | None) -> CancelAck: ...
    def lookup_by_effect_key(self, command: FrozenExecutionCommand) -> SchedulerReceipt | None: ...
```

`FrozenExecutionCommand` contains the exact owner tuple, full immutable route snapshot, opaque capability descriptor, and deterministic provider effect key. Workflow writes a durable pre-dispatch outbox row before invoking `ensure_started`. `ensure_started` and `lookup_by_effect_key` must find or create exactly one native submission for that key. Thus, after a crash between native submission and receipt persistence, Workflow recovers the original native handle rather than submitting another job. `NativeHandle` is bounded opaque adapter evidence, persisted only after validation. `Observation` maps native scheduler facts to canonical neutral states and bounded evidence—not a provider-specific result exposed to callers.

Adapters:

- **In-house:** dispatches the frozen capability endpoint through the existing named-MCP service binding. It is the reference adapter and preserves the current managed Strands behavior.
- **Celery:** submits one idempotent worker job for the whole command, persists the Celery task ID, observes terminal state using the frozen handle, and revokes only the matching task. The worker invokes the frozen capability endpoint with signed/broker credentials; it does not reconstruct a graph from mutable config.
- **Dagster:** launches one mapped run for the whole command, persists the Dagster run ID, observes it, and terminates only the matching run. The launched operation invokes the frozen capability endpoint with the same binding.

A remote adapter must have signed/broker credentials and a native worker-side provider client. It cannot claim identity from arbitrary callback fields.

## 4. Neutral lifecycle

### Enrollment

1. Agent freezes the graph manifest and sends the typed capability ID, opaque descriptor, provider digest, run key, and trusted envelope to `workflow.enroll_execution`.
2. Workflow resolves the configured route for the capability; it does not accept a scheduler argument.
3. Workflow canonicalizes input, validates replay/conflict behavior, snapshots the resolved route, and creates the durable run and initial attempt.
4. Workflow durably writes a pre-dispatch/outbox record, then calls `ensure_started`. A synchronous in-house result can settle immediately; an external scheduler returns a persisted native handle and a pending/running observation. If a process dies before the receipt is stored, recovery calls `lookup_by_effect_key` and attaches the original native handle; it never submits a second job.

### Observation/recovery

Workflow owns a generic reconciliation worker/operation. For nonterminal attempts it loads the frozen route and native handle, calls that snapshot’s scheduler `observe`, validates the returned exact owner tuple, appends evidence, and commits state using the current lease/revision CAS. Recovery never consults a live route registry and never creates a second native job unless the durable outer retry policy created a new attempt.

### Retry

Strands model/tool/node retries occur wholly inside the provider execution and are inner evidence only. A declared outer retry creates a new Workflow attempt with a new command identity. Scheduler-native retries are disabled or transparently deduplicated against that one command; they may not create a second logical Workflow attempt or terminal evidence stream.

### Cancellation

Workflow first durably fences active attempts. It then uses the frozen scheduler snapshot to issue a best-effort scheduler cancellation for the exact handle and uses the frozen provider cancellation endpoint when required to stop an in-process graph. Late scheduler/provider completion is rejected by the run/attempt/revision/digest checks. The public result is the Workflow terminal state, not the scheduler acknowledgement.

## 5. Evidence and public state

Workflow retains the one append-only `execution_events` journal. Every scheduler and provider event carries the exact owner tuple and a monotonic sequence. Adapter-specific raw material is private, bounded, and digested; only safe metadata is surfaced broadly.

Canonical states are `pending`, `running`, `retrying`, `succeeded`, `failed`, `cancel_requested`, and `cancelled` (exact existing enum reconciliation is part of implementation). Celery and Dagster state names remain private metadata. A run has at most one terminal result; evidence cannot be appended after its fence.

Graph/OTel consumers read Workflow’s durable run and evidence projections, so their behavior is independent of the selected scheduler. The scheduler’s native handle can be linked as diagnostics but never replaces `workflow_run_id`.

## 6. Legacy migration

`TaskExecutor` is retained temporarily for legacy `task_mode: executor` workflows. It is not registered as an `ExecutionSchedulerPort` merely because it has `submit/get_status/cancel` methods: it lacks frozen route snapshots, durable handle reconciliation, exact binding, evidence, and cancellation fencing.

Migration is additive:

1. Preserve legacy task behavior and expose explicit deprecation telemetry.
2. Add the scheduler port and make the in-house adapter pass the existing managed-engine contract.
3. Implement a contract-complete Celery adapter with a fake test transport before real broker deployment.
4. Implement a contract-complete Dagster adapter with a fake test transport before real deployment.
5. Migrate projects by route configuration; Agent launchers remain unchanged.
6. Deprecate `executor.backend` and executor-specific tools only after migration telemetry shows no managed callers remain.

## 7. Security boundaries

All private handoffs use exact one-shot `@service_only` claims and the full binding. Workflow core only calls allowlisted route targets. Scheduler secret/config data is never part of the opaque descriptor or event projection. Remote callbacks and status replies must be authenticated and validated against the stored handle and snapshot before mutating Workflow state.

## 8. Acceptance architecture canaries

- No scheduler string/SDK import/provider-native parsing in Workflow core lifecycle code.
- No scheduler IDs/configuration in Agent MCP schemas, graph launchers, or other caller contracts.
- No `if capability == ...` or `if scheduler == ...` branch in generic Workflow lifecycle; adapters are selected through the frozen route snapshot.
- One black-box contract suite runs unchanged against in-house, fake Celery, and fake Dagster, including crashes before submission and after submission before receipt persistence.
- Agent/Strands graph and a test-only `probe_compute` capability provider—each with distinct descriptor and private service-only execute/cancel endpoints—follow the identical neutral lifecycle path.
