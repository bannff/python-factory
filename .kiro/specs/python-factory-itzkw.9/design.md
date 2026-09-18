# Post-commit Evals projections

## Decision
`evals_record_run` remains the sole authoritative writer. On `created` or `matched`, it returns an immutable pointer (`collection`, `doc_id`, `record_kind`, `schema_version`, `revision`, `content_hash`) and a deterministic projection key. Failed and conflict writes have no projection-eligible pointer.

The Events auto-eval dispatch first commits this record, then independently publishes `eval.completed` and upserts a Graph `EvalRecordPointer` with deterministic identity. Both downstream payloads contain only the pointer, projection key, run/workflow index fields, and scalar score summary. They never contain Evals artifacts, session evidence, cases, evaluator rows, or score arrays.

## Failure and replay
Durable persistence failure stops both projections. Event and Graph failures are separately caught and logged; neither can change the durable result or suppress the other projection. Replays reuse the exact pointer-derived projection key and Graph entity id; event UUIDs remain transport identifiers and are not used for idempotency.

## Verification
Focused fake-backed tests pin ordering, durable-failure suppression, pointer-only projections, independent projection failure handling, and created/matched replay stability.
