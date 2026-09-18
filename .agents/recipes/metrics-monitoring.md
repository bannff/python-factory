# Recipe: Metrics & Monitoring

Metrics is the measurement/trend surface for a selected subject. It uses the Metrics brick’s existing series/snapshot/drift primitives; live dashboard activity is one focus, not the product definition.

## Subject focus

`MetricFocus` is a strict discriminated Pydantic-v2 request. `run` requires `run_id`; `execution` requires `run_id` and exactly one agent/graph/swarm ID; `eval` requires `eval_ref`; `trace` requires `trace_id` and may add `span_id`; `session` requires `session_id`; `entity` requires `entity_ref`; `live`/`system` accept no durable subject identity. Allowed extra fields narrow with AND semantics. Invalid/contradictory focus returns `invalid_focus`, never broadens.

`requested_availability` is only a preference. Result truth is `measurement_state`: live-not-persisted, durable-as-of, still-arriving, no-durable-measurement, source-unavailable, source-deleted, or source-inaccessible, with source class, timestamp/completeness, and next action. Never label live browser activity as durable run evidence.

Every Graph, Timeline, Evals, or owner **Open metrics** action carries the same versioned `NavigationRef`: source surface, stable accessible target, label, selected Graph item, and bounded graph context. Return and **Open related graph** restore that exact context; unavailable/inaccessible targets use a disabled named action with a reason.

## Evidence ownership

Telemetry provides authenticated OTLP-derived bounded metric summaries through typed MCP materialization. Metrics owns durable metric series/snapshots/trends; Graph owns durable references; raw traces remain Telemetry evidence. The established `metrics_define_metric`, `metrics_record`, `metrics_record_batch`, `metrics_get_snapshot`, `metrics_get_trend`, `metrics_compute_aggregation`, and `metrics_detect_drift` interfaces remain the base. Add subject-aware queries only where they cannot express the validated focus.

## Verification

1. Verify each focus kind, AND constraints, and `invalid_focus` result.
2. Verify live, durable, arriving, no-evidence, unavailable, deleted, and inaccessible render states/accessibility.
3. Verify Graph entry, Metrics return, and related-Graph restoration preserve selected bounded context.
4. Verify a Telemetry-materialized measurement and its Graph reference resolve to the same authorized subject.
