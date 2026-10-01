# Edge routing dataset and evaluation contract

**Tracking:** [ENG-204](https://linear.app/ditto/issue/ENG-204/define-outcome-grounded-edge-routing-dataset-and-evaluation-contract), child of [ENG-188](https://linear.app/ditto/issue/ENG-188/heterogeneous-edge-model-coordination-over-offline-ditto-peers).
**Status:** Contract work in progress. No outcome-grounded routing labels or trained router exist.

## Decision boundary

The router may rank peers already declared eligible by the deterministic coordinator. It cannot authorize a task, change membership, resolve claims, or execute an action. The reducer remains the final validator. For a controlled comparison, propose one selected eligible peer at a time under a versioned routing policy; the current reducer's lexical winner among simultaneous claims is not a learned-router decision.

The 24-case ENG-201 fault corpus tests record validity and deterministic replay. Its Results were pre-seeded; neither those rows nor the reducer's lexical winners are observed route outcomes. They are excluded from router training and held-out quality claims.

## Dataset example

Use Dataset's `edge_routing_example` recipe schema and local validation/materialization rails. An example separates:

1. **Predecision features:** source event and episode/group identity, task kind, required capability IDs, UTC snapshot time, pinned scenario/policy/reducer digests, and bounded capability/resource snapshots for eligible candidates. Use an explicit feature allowlist. No Result, claim winner, selected candidate, future timestamp, outcome, reviewer decision, or split marker enters model features.
2. **Attempted route:** the one actually selected candidate, policy identity, selection time, and propensity when later off-policy analysis is intended. An unchosen candidate is censored, not a negative example.
3. **Outcome and review:** a content-addressed, independently inspectable live-run result plus run/SDK provenance; a reviewer/adjudication reference and time; the observed result of the attempted route only. A reviewed label may become trainable after evidence bytes, candidate identity, time order, and policy compatibility are checked.

Freeze train/validation/test at the episode/source-event group boundary. Also reject duplicate IDs with changed content and any snapshot/outcome digest reused across splits. Dataset quality must fail closed on missing evidence bytes, missing reviewed outcomes, leaked groups, or absent splits. Test-only synthetic fixtures exercise these rules; they are not a training cohort.

If no reviewed outcome exists, publish a typed `no_labels` readiness decision and **no training bundle**. Do not create an Evals model run for that state. Even structurally valid claims remain `quality_blocked` until [ENG-205](https://linear.app/ditto/issue/ENG-205/attest-live-ditto-routing-outcomes-before-edge-router-training) binds the routing evidence and reviewer receipt to a sealed SDK run. The writer and public verifier fail closed while that trust gate is absent. Once verified real outcomes exist, publish a content-addressed Dataset definition, recipe, distinct train/validation/test views, manifest, and lineage through the Dataset brick.

## Comparison evidence

Evaluate the deterministic selector and optional tiny ranker on the **same frozen eligible-candidate snapshots** and independent held-out episodes. Keep the reducer's safety and authority checks identical for both. Record a prediction/selection row with model, dataset split, evaluator, policy, scenario, and runtime digests. Require reviewed outcome evidence for task-completion comparisons; chosen-arm observations alone do not establish how unchosen peers would have performed. Use controlled comparable assignments or logged selection propensity before estimating route uplift.

The Evals record must report, or explicitly mark unavailable with a reason: task completion/failover, unsafe route attempts (required zero), abstention and deterministic fallback, p50/p95 route and coordination latency, per-device database growth and mesh bytes, and router CPU/RAM/model size. Record device/runtime fidelity. `EdgeModelEvidence` and the durable `evals_record_run` writer are the native rails; a local run index alone is not a persisted Evals record. With no live peer run, SDK bytes, persistence, radio cost, and task uplift remain unavailable.

## Next gate

Complete ENG-184's licensed N=2 Ditto SDK path, then capture actual task/claim/result attempts under this schema. Review the labels and freeze an untouched test split before training. N=4 heterogeneous mesh and native/physical-device resource claims remain separate ENG-188 gates.
