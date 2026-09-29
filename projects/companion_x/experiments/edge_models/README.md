# Edge-model experiment catalog

This directory contains curated, versioned research records for models intended
to run at phone-class power or less. It complements the ML brick's training-run
view and the Evals brick's scoring records. Neither a live dashboard nor an
agent's report is the sole authority for a model-selection decision.

## Record layout

Each experiment has a stable ID and a directory containing:

- `protocol.md`: task, source data, labels, split, metrics, target hardware,
  and decision gates; timestamp and distinguish pre-run plans from later
  reconstructions;
- `run-index.json`: dataset and split hashes, run identities, headline metrics,
  artifact digests and durable evidence references;
- `results.md`: interpretation, protocol deviations, limitations, and the
  pursue/revise/stop decision.

Retain per-run manifests, prediction arrays, logs, datasets, checkpoints, and
weights in artifact storage. Record their immutable hashes and links in the
index or its evidence bundle. Do not commit raw data or generated model files.
The repository `.gitignore` admits only the three curated record names above
plus this index, so local runtime output in this folder is still ignored.

## Current records

| ID | Task | Status | Results |
| --- | --- | --- | --- |
| [edge-engine-failure-001](edge-engine-failure-001/results.md) | Simulated engine failure warning from sensor windows | Exploratory lab pilot | Logistic baseline leads; iPhone and mesh gates pending |
