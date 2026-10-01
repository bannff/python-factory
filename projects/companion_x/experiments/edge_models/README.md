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

The earlier catalog pilots used Dataset's generic, pass-through recipe. Those
historical jobs completed, but their conversation-oriented quality checks could
report `passed=false`; separately validated artifacts were compared
record-for-record with their frozen inputs. Dataset now has an explicit
`edge_sensor_window` policy for versioned sensor examples. It checks schema,
unique record IDs, required train/validation/test splits, group and input-digest
split isolation, and the bytes behind each input reference. After no-follow
SHA-256 verification, the referenced JSON payload is validated for ordered
channels and timestamped samples, exact channel/sample shape, finite values,
strictly increasing sample times, modality agreement, and an observation
cutoff equal to the final sample timestamp. Labels carry separate provenance
and a future horizon. Symlinked input paths, unsupported URI schemes,
unreadable files, and hash mismatches fail closed. Materialization and
checkpoint resume revalidate payload semantics; a bad payload or cross-split
leak prevents publication. Keep the Dataset quality result visible in each
run index.

ENG-191 and ENG-192 track the new Dataset and Evals contracts. ENG-191's
sample-level payload checks and fresh review are complete; its full Dataset
suite passed (582 passed, 32 skipped). Evals accepts an
`edge_model_evidence` envelope that records SHA-256 digests for the model,
dataset and split, evaluator, and policy, together with the target, runtime,
measured task/resource metrics, and explicitly unavailable measurements. The
durable run-record path validates and preserves this envelope; its hashes are
reproducibility references and do not by themselves prove that external files
were retrieved or executed.

ENG-185 and ENG-186 track iOS Simulator and Android Emulator compatibility.
Current native-runner groundwork defines frozen scenario and result contracts
and a host-toolchain preflight. A preflight reports availability and planned
commands only; it explicitly records that no native run was performed. It is
not evidence of app/SDK compatibility, model packaging, prediction parity, or
device performance. No native app or SDK run is recorded in this catalog yet.

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
simple baseline; packaging/conversion of the **model** into the named iPhone
runtime with prediction parity and resource measurements; then continuous
local result writes through the real Ditto SDK, restart persistence, and
correct observation/typed-capability behavior across disconnected peers.
"Model export" means preparing weights for the device runtime. Inference
results stay in the device's Ditto-backed local database and sync according
to the app's subscriptions; the field workflow does not export result files.
A lab quality score only addresses the first gate.

## Current records

| ID | Task | Status | Results |
| --- | --- | --- | --- |
| [edge-engine-failure-001](edge-engine-failure-001/results.md) | Simulated engine failure warning from sensor windows | Exploratory lab pilot | Logistic baseline leads; iPhone and mesh gates pending |
| [edge-vision-defect-001](edge-vision-defect-001/results.md) | Local surface-defect triage | Exploratory lab pilot | MobileNetV3 Small AP 0.778 versus 0.717; improvement uncertain |
| [edge-audio-command-001](edge-audio-command-001/results.md) | Offline go/stop voice commands | Exploratory lab pilot | Tiny CNN improves macro F1, but 156/954 other words trigger commands |
| [edge-tool-routing-001](edge-tool-routing-001/results.md) | Local typed-tool selection | Synthetic lab probe | Standalone MiniLM has 6/10 unsafe misroutes; guarded follow-up needs fresh holdout |
| [edge-ditto-device-flow-001](edge-ditto-device-flow-001/protocol.md) | N-device model persistence and offline peer sync through the real Ditto SDK | Protocol ready; not run | Python SDK mesh gate, followed by physical iPhone verification |
| [edge-lab-model-smoke-001](edge-lab-model-smoke-001/results.md) | Frozen sensor-model inference inside one `edge-lab` container | Functional gate passed | 100/100 decisions; 3.33e-16 maximum score error; Ditto gate remains separate |
| [edge-maintenance-dispatch-demo-001](edge-maintenance-dispatch-demo-001/results.md) | Offline maintenance dispatch queue from edge sensor inference | Container rehearsal passed | 100 assets, 2 technician proposals, replay-safe task state; Ditto peers and multimodal data remain untested |
| [edge-visual-quality-mesh-001](edge-visual-quality-mesh-001/protocol.md) | Tiny local vision model flags surface defects on an edge device; later coordinate review over Ditto | ARM64 `edge-lab` inference demonstrated; two-peer Ditto mesh pending | 135 held-out images scored, 6.3 KB model, 11.6 ms/image; AP 0.876; FPR 10.26% misses the pre-set 10% gate; [run results](edge-visual-quality-mesh-001/results.md) |
| [edge-audio-device-demo-001](edge-audio-device-demo-001/results.md) | Offline WAV keyword proposals from a tiny trained CNN | ARM64 `edge-lab` inference demonstrated; iPhone and Ditto pending | 12 held-out clips, 12/12 PyTorch decision parity, p95 1.142 ms; 7/12 illustrative clips correct, so no voice-control promotion |

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
