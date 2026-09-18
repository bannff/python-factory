# Companion-X Graph Provenance Surface — Requirements

## Introduction

Graph is Companion-X’s durable answer to **“what is related to this?”** It links workflow runs, agent/framework activity, events, evaluations, measurements, artifacts, and domain objects without owning their payloads or lifecycle. Telemetry owns OTLP ingress, raw evidence, and bounded downstream MCP materialization; Graph owns a durable related-things projection.

## Requirement 1 — Typed, non-interchangeable identity

1. `run_id` is the durable execution/attempt join. `workflow_run_id` is ingress-only compatibility vocabulary and normalizes to `run_id`.
2. W3C `trace_id`/`span_id`, `session_id`, definition IDs (`workflow_id`, `graph_id`, `swarm_id`), and `agent_id` retain their distinct meaning. They are never derived from, overwritten by, or substituted for another.
3. Trusted ingress binds producer, principal, tenant, visibility, and source ownership; untrusted signal attributes cannot assert them. `trace_id → correlation_id` conflation is corrected at normalization without a new provenance ID.

## Requirement 2 — Durable, domain-agnostic Graph projection

1. Graph persists source-reference relationships and selected browse metadata, restores after restart, and reconciles deterministically from enumerated durable source records.
2. A strict `GraphRelationshipWrite` includes source system, stable source identity/digest, relation type, normalized endpoints, source reference, visibility, and projection metadata. Its deterministic ID derives from those identity-bearing fields.
3. Graph atomically create-or-matches an equal write, returns an explicit conflict for a same identity with different immutable content, and records a source tombstone/delete without leaving a dangling relationship.
4. A strict rebuild accepts an immutable source-enumeration snapshot/cursor and checkpoint. It reports scanned/applied/duplicate/conflict/tombstone counts and resume cursor; replay/restart converges to the same projection.
5. NetworkX is durable only with configured persistent snapshot/restore plus this reconciliation path. In-memory NetworkX is transient.
6. Graph does not own Workflow/Strands state, evaluation documents, measurement payloads, artifact bytes, or domain payloads. No domain is special.

## Requirement 3 — Workflow and framework boundary

1. Workflow owns intersystem run/attempt lifecycle, dispatch, global budget/retry/cancellation policy, evidence references, and terminal state.
2. Agent/Strands owns native Graph/Swarm scheduling, traversal, handoffs, nested composition, and streaming.
3. Native Strands lifecycle hooks are observer-only: they emit bounded observations and neither schedule/retry native nodes nor change Workflow state.
4. Each Agent process initializes one configured Telemetry tracer provider before Agent/Graph/Swarm construction and injects the same provider into `StrandsTelemetry`. Competing provider/export ownership is prohibited.

## Requirement 4 — Telemetry-owned OTLP ingress and materialization

1. Telemetry owns authenticated OTLP HTTP/gRPC ingress. An optional Collector only transports/processes and forwards OTLP. The receiver translates OTLP to ordinary Pydantic-v2 Telemetry runtime/MCP DTOs; an MCP tool is not a network listener.
2. Strict DTOs cover `TelemetryIngestBatch`, `TelemetryReferenceRead`, and `TelemetryMaterialize`. Each operation authorizes the authenticated envelope’s producer/principal/tenant/visibility; raw-reference reads and every downstream call inherit that bound context.
3. The durable cross-process idempotency scope is `(tenant, verified_producer, batch_id)` and `(tenant, verified_producer, source_id)`, with a canonical payload fingerprint. Same key/fingerprint is duplicate; same key/different fingerprint is conflict; partial item outcomes and retry eligibility are explicit.
4. Batches are bounded. Redaction/sampling occurs before raw retention and records policy/version/outcome. The durable response includes accepted/duplicate/rejected/retained-unmaterialized/materialized/partial-failure evidence references.
5. A materialization mapping is an immutable, versioned allowlist record naming accepted signal/reference types, exact target brick/capability version, max fan-out, and output provenance. Activation validates that its mapping graph is acyclic and rejects Telemetry targets, Agent/Workflow targets, and direct/transitive return paths to Telemetry.
6. Telemetry preserves W3C `traceparent`/`tracestate` across HTTP, event/queue, and version-negotiated MCP carriers. Scalar IDs remain envelope attributes. Malformed, unsupported, or untrusted context is rejected or starts a policy-defined new trusted root.

## Requirement 5 — Typed subject-focused Metrics and navigation

1. Metrics answers “how did this selected thing behave?” and does not equate live UI activity with durable evidence.
2. A strict Pydantic-v2 discriminated `MetricFocus` defines `subject_kind`, required/allowed identity fields, AND/cardinality rules, label, time range, aggregation, and `requested_availability`. Invalid or contradictory focus returns actionable `invalid_focus`, never a broadened query.
3. `execution` means one native execution scoped by `run_id` plus exactly one of `agent_id`, `graph_id`, or `swarm_id`; `trace` means `trace_id` and optional `span_id`; `session` means `session_id`. They are separate focus kinds.
4. A versioned `NavigationRef`—surface, stable accessible target/reference, display label, selected durable Graph item, and bounded graph query/context—travels unchanged through **Open metrics**, return breadcrumb, and **Open related graph**. Inaccessible/unavailable navigation renders a disabled named action and explanatory status.
5. A result returns `measurement_state`, source class, evidence timestamp or last-updated/completeness, and safe reason/next action. States are: live-not-persisted; durable-as-of; still-arriving; no-durable-measurement; source-unavailable; source-deleted; source-inaccessible.
6. State changes have text, accessible status announcement, keyboard-reachable named actions, and focus management after cross-surface navigation.

## Requirement 6 — Graph experience and proof

1. Graph opens a bounded accessible neighborhood from a durable item, identifies omitted/arriving/unavailable relations, supports intentional expansion, and links to owner views.
2. Acceptance proves separately queryable run/trace/session IDs; W3C parentage; durable raw telemetry; replay-safe Telemetry→Graph/Metrics projection; deterministic Graph rebuild/tombstones; observer-only native lifecycle; exact return restoration of selected Graph item/context; and truthful state rendering.
3. Coverage includes chat, native Graph, Swarm, in-process and remote MCP, provider-before-Agent, live/no-measurement/arriving/inaccessible cases, and two unrelated domains.

## Constraints

- MCP-first Pydantic-v2 capabilities are the only cross-brick API boundary.
- No domain switch/security default, global provenance ID, generic outbox, or source-of-truth Graph database.
- No implementation proceeds until final architecture, Strands, and UX approval.
