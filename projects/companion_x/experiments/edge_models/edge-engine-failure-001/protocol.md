# Protocol: edge-engine-failure-001

This versioned record was assembled after the first pilot from its earlier
draft and recorded run configuration. It is not a sealed preregistration;
[results.md](results.md) documents deviations and exploratory comparisons.

## Task

Use a trailing 20-cycle sensor window to warn when a simulated engine has at
most 30 cycles of remaining useful life (RUL). This is a pipeline and
coordination proxy for offline asset-health workflows, not a field-valid
failure predictor. Target device for the later edge benchmark: iPhone.

## Data and split

Source: [NASA C-MAPSS](https://catalog.data.gov/dataset/cmapss-jet-engine-simulated-data),
subset FD001. Each row has an engine ID, cycle, three operating settings, and
21 sensor channels. Fit on the 100 complete training engines. Keep engine IDs
disjoint across five validation folds. Score one frozen censored endpoint per
training engine, with endpoint RUL assigned from `[5, 15, 25, 30, 31, 35, 45,
60]` by a seeded engine-ID ordering. Score one final observed endpoint per
official test engine. Exclude engine ID, future rows, and RUL from features.

## Candidates and metrics

Compare a logistic-regression baseline, LightGBM, and a compact temporal
convolutional network (TCN). For any two-model policy, calibrate and select its
rule using training/validation data only. Primary metric: area under the
precision-recall curve (AUPRC). Also report recall and false-positive counts at
a threshold selected for at most 5% validation false-positive rate, paired
uncertainty for model comparisons, and training configuration.

On an actual iPhone, record the model and iOS version, converted-model parity, cold
start, p50/p95 inference latency, peak memory, artifact size, energy, thermal
behavior, and offline operation. Persist each typed prediction in the local
Ditto SDK store and verify it survives app restart. For mesh coordination,
compare independent models with a deterministic local policy, then test
subscribed observation and task exchange between disconnected Ditto peers,
including loss/rejoin and duplicate claims.

## Record discipline

Record source URL and hash, split hash, seed, code and artifact identity,
backend, evaluation cohort, thresholds, uncertainty, device profile, and
protocol deviations. Keep generated data and weights outside Git. The
[results](results.md) state where this first pilot departed from the intended
evaluation sequence.
