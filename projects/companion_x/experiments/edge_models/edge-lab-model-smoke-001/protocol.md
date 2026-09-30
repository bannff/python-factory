# Protocol: edge-lab-model-smoke-001

**Status:** Predeclared before the first container run, 30 September 2026.
The per-engine prediction and command-log retention requirements below were
added after independent review of the first two attempts; the functional
gate and frozen inputs were unchanged.

## Question

Can the single `edge-lab` container execute a previously trained small sensor
model with predictions matching its frozen lab artifact, while producing
repeatable latency and memory evidence? This is a container and inference
rehearsal. It does not test Ditto writes, peer sync, or iPhone resources.

## Frozen inputs

Use the logistic baseline from `edge-engine-failure-001`, SHA-256
`6dbb0b9b37e6640322048ecd965cfc72eda00e2564915e2a6f9b1125576a74e8`.
The NASA C-MAPSS source archive SHA-256 is
`74bef434a34db25c7bf72e668ea4cd52afe5f2cf8e44367c55a82bfd91a5a34f`.
Its input is the final 20 chronological cycles for each of the 100 NASA
C-MAPSS FD001 official test engines, with 24 float32 features per cycle.
The warning threshold is `0.7392553708788053`, selected in the prior lab
record. Do not fit, tune, or relabel the model in this run.

Export the fitted `StandardScaler` and `LogisticRegression` parameters from
the trusted joblib artifact into a versioned JSON scorer. Record the source
archive, joblib, exported scorer, and cohort hashes. Compare every container
score with the original scikit-learn `predict_proba` score on the same frozen
cohort. The export is a functional Python scorer, not an iPhone model package.

## Run and gates

Upload the scorer, cohort, and checked-in runner through Companion-X Sandbox.
Run 100 timed passes over the 100 endpoints (10,000 inferences) after one
untimed pass. Record p50/p95 per-inference latency, maximum absolute score
error, decision agreement, process peak RSS, and container memory before and
after. Preserve the raw machine-readable result outside Git and link its hash
from `run-index.json`. Retain per-engine reference and observed probabilities,
absolute errors, warning decisions, and labels in that result. Record exact
export and container commands, transfer paths, exit codes, and digest checks
in the evidence manifest.

The functional gate passes only if the command exits successfully, all 100
scores are finite, maximum absolute error is at most `1e-6`, and all 100
threshold decisions agree with the frozen artifact. Latency and memory are
descriptive for this Docker Desktop host; no phone-class resource gate is
claimed. A failed or incomplete run remains visible in `results.md`.
