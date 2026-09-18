# Durable Evals writer convergence

## Scope

`evals_record_run` is the only Evals artifact writer. It produces versioned, terminal records and delegates create-or-match semantics to Storage through `tool_invoker`; it never imports Storage internals.

## Immutable document contract

Full artifacts use the version-isolated document ID `eval-v2-{run_id}` with `schema_version: 2`, `record_kind: "evaluation_run"`, `terminal_state: "completed"`, and `content_hash: "sha256:<hex>"`. The hash covers every persisted JSON-safe field except the hash itself, in deterministic JSON order. An omitted timestamp is stored as the stable empty string; an explicit timestamp is authenticated. Equal same-run retries return `matched`; divergent retries return `conflict` without mutation. Existing v1 rows remain untouched in the `eval-{run_id}` namespace.

Legacy P/R/F1 writes remain available through `evals_persist_score`, but they invoke `evals_record_run` as an `evaluation_score_projection` at `eval-score-v2-{run_id}`. They cannot overwrite full artifact documents.

## Storage boundary

Storage adds `doc_create_or_match`, backed by an atomic SQLite transaction. Other callers retain mutable `doc_insert`; Evals never uses it for canonical records. The operation returns `created`, `matched`, or `conflict` with hashes for diagnosis.

## Producer convergence

Simulation keeps its stable retry request. Experiments allocate their run ID before execution and expose retry material. Auto-eval writes durably before graph/event projections; conflict and failure suppress projections. Backfill and legacy scoring route through `evals_record_run`.

## Verification

Focused tests cover deterministic hashes, equal retry match, divergent conflict preserving first bytes, score projection isolation, canonical reader filtering, simulation no-rerun retry, producer ordering, and SQLite concurrency/stateful retry invariants.
