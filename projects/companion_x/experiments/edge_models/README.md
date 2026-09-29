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
- `run.py` when the pilot used a standalone runner: the source snapshot and
  commands needed to reproduce its lab metrics are recorded in the protocol
  and index.

Retain per-run manifests, prediction arrays, logs, datasets, checkpoints, and
weights in artifact storage. Record their immutable hashes and links in the
index or its evidence bundle. Do not commit raw data or generated model files.
The repository `.gitignore` admits only these curated record names plus this
index, so local runtime output in this folder is still ignored.

For each family, use the Dataset brick to publish the versioned dataset
definition and materialize frozen partitions (train/validation/test, official
folds, or development/evaluation as the task requires). Its generic
recipe is pass-through: family-specific schema checks and group-safe splitting
must happen before submission, with their evidence recorded here. Use the ML
brick's real trainer where supported; the `memory` backend is never result
evidence.

The current Dataset quality checks expect conversation `messages`. They
report `passed=false` for these ML records even though all 11 generic jobs
completed and the separately validated artifacts were resolved and compared
record-for-record with their frozen inputs. Until the brick has native ML schemas
and quality policies, treat the external validation manifest as the ML data
check; keep the brick status visible in each run index.

Dataset job IDs and `file:` artifact URIs refer to this local lab store, so
they are not portable endpoints. The [ENG-173 evidence bundle](https://linear.app/ditto/issue/ENG-173/edge-device-multi-model-family-experimentation)
(attachment `24d3838f-9f91-404b-9b14-b7c847778ac9`, SHA-256
`703ebbebc270784866c1f5fce75cb7d2d84373fcaa2509d2cd9eac17dc227bd6`)
preserves the Dataset definitions, frozen source and materialized JSONL,
manifests, runners, scores, and small derived models. It omits source image
and audio archives and pretrained weights; their source URLs and hashes are
recorded for separate retrieval. Local archive paths in bundled JSONL must
be remapped when reproducing on another machine.

Every candidate has three separate gates: held-out task quality against a
simple baseline, export parity and resource use on the named iPhone, then
correct typed-capability behavior across disconnected Ditto peers. A lab
quality score only addresses the first gate.

## Current records

| ID | Task | Status | Results |
| --- | --- | --- | --- |
| [edge-engine-failure-001](edge-engine-failure-001/results.md) | Simulated engine failure warning from sensor windows | Exploratory lab pilot | Logistic baseline leads; iPhone and mesh gates pending |
| [edge-vision-defect-001](edge-vision-defect-001/results.md) | Local surface-defect triage | Exploratory lab pilot | MobileNetV3 Small AP 0.778 versus 0.717; improvement uncertain |
| [edge-audio-command-001](edge-audio-command-001/results.md) | Offline go/stop voice commands | Exploratory lab pilot | Tiny CNN improves macro F1, but 156/954 other words trigger commands |
| [edge-tool-routing-001](edge-tool-routing-001/results.md) | Local typed-tool selection | Synthetic lab probe | Standalone MiniLM has 6/10 unsafe misroutes; guarded follow-up needs fresh holdout |

## Candidate coverage

These pilots sample four useful model roles, rather than asserting that every
named architecture is interchangeable. The sensor record covers logistic,
LightGBM, and a short TCN run. The vision and audio records cover a compact
pretrained image backbone and a trained keyword network. The language record
covers a frozen small semantic encoder, not a generative agent.

Keep the remaining named candidates explicit: liquid/recurrent time-series
models, Chronos, YAMNet or another audio-event detector, FunctionGemma 270M,
and Gemma 4 E2B/E4B have **no result in this catalog yet**. Chronos and the
Gemma candidates need a separate size, runtime, access, and use-case review
before being called phone-class models. A model is promoted for a job only
after all three gates above are measured for its exact artifact and target
device.
