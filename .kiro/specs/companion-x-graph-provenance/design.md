# Companion-X Graph Provenance Surface — Design

> Status: **REVISED DRAFT — final SME approval required before implementation**
>
> Graph is the durable related-things surface. Timeline answers when; Metrics answers how a selected subject measured; Evals answers quality/decision; owner views retain canonical records.

## 1. Identity and ownership

| Identifier | Meaning | Rule |
|---|---|---|
| `run_id` | durable Workflow execution/attempt | primary execution join |
| `workflow_run_id` | legacy ingress form | normalize once to `run_id` |
| `trace_id`, `span_id` | W3C topology | never alias to `correlation_id`/`run_id` |
| `session_id` | conversation/interaction | may relate to many runs/traces |
| `workflow_id`, `graph_id`, `swarm_id` | definitions/topologies | never execution IDs |
| `agent_id` | persona/node | never session/execution ID |

Workflow owns intersystem lifecycle/global policy. Native Strands owns Graph/Swarm scheduling, handoffs, and streaming. Telemetry owns OTLP ingress/evidence/materialization. Graph owns a durable reference projection. Lifecycle hooks only observe; Workflow never schedules/retries native nodes.

One Telemetry provider is initialized before Agent/Graph/Swarm creation, installed globally where OTel requires it, and injected into `StrandsTelemetry(tracer_provider=...)`. Competing provider/export ownership is prohibited.

## 2. Ingress, trust, and propagation

```text
framework SDK / instrumented MCP tool
  → Telemetry OTLP HTTP/gRPC receiver
  → auth bind + W3C validation + redact/sample + normalize + raw retention
  → typed Telemetry runtime/MCP capability
  → immutable allowlisted mapping
  → typed MCP capability of Events / Metrics / Graph / Storage
```

A Collector is optional transport/processing only. Telemetry’s receiver is the HTTP/gRPC adapter; it converts OTLP to runtime/MCP DTOs. Trusted request context binds producer, principal, tenant, visibility, and source namespace. Reads and downstream calls inherit those bindings.

HTTP, queue/event, and negotiated MCP carriers preserve W3C `traceparent`/`tracestate`; scalar IDs stay in immutable envelopes. Version-specific MCP extraction validates the carrier. Malformed, unsupported, or untrusted remote context is rejected or begins a policy-defined trusted root—never becomes `correlation_id`.

## 3. Strict Telemetry contracts

All public DTOs use `ConfigDict(extra="forbid", frozen=True, strict=True)` and bounded fields. `AuthenticatedTelemetryContext` is server-created only; it is neither a tool nor receiver request field.

```python
class AuthenticatedTelemetryContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    tenant_id: str; producer_id: str; principal_id: str
    visibility: VisibilityScope; source_namespace: str

class TelemetryIngestItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    source_id: str; canonical_payload: JsonValue
    trace_id: str | None; span_id: str | None; parent_span_id: str | None
    signal: Literal["span", "log", "metric"]; attributes: dict[str, JsonValue]

class TelemetryIngestBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    batch_id: str; items: list[TelemetryIngestItem] = Field(max_length=MAX_INGEST_ITEMS)

class TelemetryIdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    tenant_id: str; producer_id: str; key_kind: Literal["batch", "source"]
    key: str; fingerprint: str; outcome_ref: str; persisted_at: datetime

class TelemetryItemOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    source_id: str; status: Literal["accepted", "duplicate", "conflict", "rejected", "retained_unmaterialized", "materialized"]
    telemetry_ref: str | None; retryable: bool; reason: str | None

class TelemetryIngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    batch_id: str; status: Literal["accepted", "duplicate", "partial_failure", "conflict", "rejected"]
    outcomes: list[TelemetryItemOutcome]; retryable_source_ids: list[str]

class TelemetryReferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    telemetry_id: str; requested_fields: set[str] = Field(max_length=MAX_READ_FIELDS)

class AuthorizationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    permitted: bool; permitted_fields: set[str]; denial_code: str | None
```

The persistent idempotency scope is `(tenant, verified_producer, batch_id)` and `(tenant, verified_producer, source_id)`. The canonical fingerprint is stored in `TelemetryIdempotencyRecord` across processes. Equal replay is duplicate; changed replay is conflict. `TelemetryReferenceRead` creates `AuthorizationDecision` from the server context before accessing the reference. Redaction/sampling precedes raw retention and records policy/version/outcome.

### Immutable mapping registry

```python
class MaterializationMapping(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    mapping_id: str; version: str; state: Literal["active"]
    accepted_signals: tuple[Literal["span", "log", "metric"], ...]

    @field_validator("accepted_signals")
    @classmethod
    def canonical_signals(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("accepted_signals must be unique")
        return tuple(sorted(value))
    target_brick: str; target_capability: str; target_version: str
    max_fan_out: PositiveInt; output_provenance: Literal["telemetry-materialized"]

class MappingNodeRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    mapping_id: str; version: str

class MappingEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    source: MappingNodeRef; target: MappingNodeRef

class MappingActivationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    registry_version: str; mappings: tuple[MaterializationMapping, ...]
    edges: tuple[MappingEdge, ...]; graph_digest: str = ""; activated_at: datetime

    @model_validator(mode="after")
    def canonicalize_and_verify_digest(self) -> Self:
        mappings = tuple(sorted(self.mappings, key=lambda item: (item.mapping_id, item.version)))
        edges = tuple(sorted(self.edges, key=lambda edge: (
            edge.source.mapping_id, edge.source.version,
            edge.target.mapping_id, edge.target.version,
        )))
        digest = sha256(canonical_json({
            "registry_version": self.registry_version,
            "mappings": mappings,
            "edges": edges,
        })).hexdigest()
        if self.graph_digest not in ("", digest):
            raise ValueError("mapping activation graph_digest does not match canonical registry")
        object.__setattr__(self, "mappings", mappings)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "graph_digest", digest)
        return self

class TelemetryMaterialize(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    telemetry_ids: list[str] = Field(max_length=MAX_MATERIALIZE_REFS)
    mappings: list[tuple[str, str]] = Field(max_length=MAX_MAPPING_REFS)
```

Activation persists `MappingActivationRecord` only after canonical field-order JSON serialization (sorted canonical signal tuples plus sorted immutable node/edge tuples) produces `graph_digest` and its full directed graph is acyclic and all target versions are pinned/allowlisted. Any Telemetry, Agent, Workflow, or return-to-Telemetry target/edge is rejected. A materialize request can select only active `(mapping_id, version)` pairs from that immutable registry; it cannot name arbitrary tools. Bound auth context propagates to each downstream MCP call.

## 4. Strict Graph projection/rebuild contracts

```python
class GraphRelationshipWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    source_system: str; source_identity: str; source_digest: str
    relation_type: str; source_endpoint: str; target_endpoint: str
    source_ref: str; visibility: VisibilityScope; browse_metadata: dict[str, JsonValue]

class GraphWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    relationship_id: str; status: Literal["created", "matched", "conflict", "tombstoned"]
    immutable_digest: str; conflict_ref: str | None

class DurableSourcePage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    snapshot_id: str; snapshot_digest: str; ordinal_start: int
    records: tuple[GraphRelationshipWrite, ...]; next_cursor: str | None

class GraphRebuildCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal["v1"]; snapshot_id: str; snapshot_digest: str
    last_ordinal: int; cursor: str | None; checkpoint_digest: str

class GraphTombstone(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    source_system: str; source_identity: str; source_digest: str; deleted_at: datetime

class GraphRebuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    source_system: str; snapshot_id: str; snapshot_digest: str
    cursor: str | None; checkpoint: GraphRebuildCheckpoint | None

class GraphRebuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    next_cursor: str | None; checkpoint: GraphRebuildCheckpoint
    scanned: int; applied: int; duplicates: int; conflicts: int; tombstones: int
```

Relationship ID is a canonical digest of source system/identity-or-digest/relation/endpoints. Adapter write is one atomic create-or-match/conflict/tombstone operation. A tombstone removes or marks the target projection so no live dangling relationship remains. Rebuild consumes ordered pages from an immutable snapshot; checkpoint snapshot/version/digest must match before resume. Restart/replay converges and reports every outcome.

Graph keeps references/digests/browse metadata, never raw trace payloads. In-memory NetworkX is transient; durable NetworkX requires persistent snapshot/restore plus this rebuild contract.

## 5. Strict Metrics focus, truthfulness, navigation

```python
class BoundedGraphContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    query_ref: str; neighborhood_limit: PositiveInt

class NavigationRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    version: Literal["v1"]; surface: Literal["graph", "timeline", "evals", "owner", "metrics"]
    target_ref: str; label: str; graph_selected_ref: str | None = None
    graph_context: BoundedGraphContext | None = None

class FocusBase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    navigation: NavigationRef; label: str
    requested_availability: Literal["live", "durable", "either"]
    time_range: TimeRange; aggregation: Literal["raw", "summary", "trend"]

class RunFocus(FocusBase): subject_kind: Literal["run"]; run_id: str
class ExecutionFocus(FocusBase):
    subject_kind: Literal["execution"]; run_id: str
    agent_id: str | None = None; graph_id: str | None = None; swarm_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_execution_subject(self) -> Self:
        if sum(value is not None for value in (self.agent_id, self.graph_id, self.swarm_id)) != 1:
            raise ValueError("invalid_focus: execution requires exactly one of agent_id, graph_id, swarm_id")
        return self
class EvalFocus(FocusBase): subject_kind: Literal["eval"]; eval_ref: str; run_id: str | None = None
class TraceFocus(FocusBase): subject_kind: Literal["trace"]; trace_id: str; span_id: str | None = None
class SessionFocus(FocusBase): subject_kind: Literal["session"]; session_id: str
class EntityFocus(FocusBase): subject_kind: Literal["entity"]; entity_ref: str
class LiveFocus(FocusBase): subject_kind: Literal["live"]
class SystemFocus(FocusBase): subject_kind: Literal["system"]
MetricFocus = Annotated[Union[RunFocus, ExecutionFocus, EvalFocus, TraceFocus, SessionFocus, EntityFocus, LiveFocus, SystemFocus], Field(discriminator="subject_kind")]

class MetricResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    measurement_state: Literal["live_not_persisted", "durable_as_of", "still_arriving", "no_durable_measurement", "source_unavailable", "source_deleted", "source_inaccessible"]
    source_class: str; evidence_at: datetime | None; last_updated_at: datetime | None
    completeness: float | None; reason: str | None; next_action: str | None
```

Because variants forbid extras, all incompatible fields fail validation; explicit allowed joins inside a variant use AND semantics. Validation returns typed `invalid_focus` outcomes rather than broadening. `label` exists both on focus (current subject) and navigation (return target) deliberately.

**Open metrics** preserves `NavigationRef`. Return restores surface, selected Graph durable item, and bounded graph context; **Open related graph** restores the same context. Unavailable/unauthorized navigation is disabled and named with explanatory text. Each measurement state is textual, announced in an accessible status region, supports keyboard-reachable actions, and moves focus to the destination heading/selected item.

## 6. Acceptance matrix

| Scenario | Required evidence |
|---|---|
| Chat / native Graph / Swarm | provider before Agent; W3C parentage; observer-only hooks |
| Local + remote MCP | valid carrier preserved; invalid/untrusted carrier rejected/new-rooted |
| Ingest/replay/read | auth-bound batch; cross-process key/fingerprint; typed outcomes; scope/field-authorized read |
| Mapping | persisted immutable graph; pinned allowed target; fan-out; cycle/return rejection |
| Graph | atomic write/conflict; ordered snapshot pages/checkpoint; tombstone; restart convergence |
| Metrics/Graph UX | discriminated focus; truthful state; accessible actions; exact Graph context restoration |
| Domains | same end-to-end flow for two unrelated bricks |

## 7. Non-goals

No global provenance ID, generic outbox, parallel control plane, telemetry loop, security-special default, Graph trace backend, or Workflow Strands-node scheduler.
