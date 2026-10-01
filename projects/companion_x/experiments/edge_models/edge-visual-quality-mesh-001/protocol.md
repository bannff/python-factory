# Protocol: edge-visual-quality-mesh-001

**Status:** Host preparation, peer process, replay guard, and review command are
implemented; no live Ditto or Sandbox run has been executed. **Question:** Can two separate, resource-
bounded edge proxies each run a small local image model, keep images on their
own device, and coordinate one inspection round through Ditto peer sync while
both have no WAN/cloud access?

This first run is an offline industrial surface-quality review, not a vehicle,
automotive, can, or container-inspection scenario. It uses two Sandbox device
containers as Linux edge proxies, not as native phones. The model classifies
images locally. Ditto carries round membership, task ownership, results, and
human-review state between the peers. There is no central/cloud coordinator.

The first run is intentionally small: one 6.3 KB grayscale-
statistics logistic head, Pillow for image decode/resize, and Python standard
library feature extraction/scoring. Do not put MobileNet, PyTorch, TorchVision,
NumPy, scikit-learn, or ONNX in the peer runtime. MobileNetV3-Small and an
ONNX/Core ML export are a later runtime and quality comparison.

## Demo storyboard and implementation boundary

The storyboard below is the target experience, not a report of an existing
dashboard or successful run. The host preparation command and one-peer process
flow are implemented. Peer processes can emit append-only JSONL snapshots from
actual Ditto store reads; no dashboard or Sandbox/MCP launcher consumes them
yet. Never animate a connection, task, or sync completion that did not happen.

| Time | Viewer sees |
| --- | --- |
| 00:00–00:20 | **Implemented preparation:** `prepare.py` validates the pinned source archives, freezes official fold 0 by whole item, writes the label-free assignment and host-only labels, then stages separate peer bundles with only each peer's assigned original images. **Pending:** provision two device proxies and establish the internal mesh/egress checks. |
| 00:20–00:40 | **Implemented peer behavior:** each independently invoked peer can publish a typed round and join record and emit JSONL snapshots from its own Ditto reads. **Pending:** host/MCP orchestration, concurrent container launch, and measured peer visibility. A join record is not TCP connectivity evidence. |
| 00:40–01:10 | **Implemented peer behavior:** each process verifies local image bytes, confirms its task claim in Ditto, runs inference locally, writes the result, and creates a typed review-open record for flagged results. **Pending:** actually stage/run the bundles in separate Sandbox containers and show a dashboard; no run is yet evidenced. |
| 01:10–01:30 | **Implemented replay guard:** a fresh process can use `--restart-replay` with its persistent store; it requires prior results and fails if new records or logical results appear. It reports new/duplicate write counters. **Pending:** restart an actual container process while the second peer remains connected and capture persistence/sync evidence. |
| 01:30–01:55 | **Implemented evidence:** the peer runner checks the frozen task IDs, record ownership, privacy schema, and converged result projection. **Pending:** demonstrate both running peers, reconcile real SDK snapshots, and measure convergence/egress outcomes. |
| 01:55–02:15 | **Implemented command:** `review.py` writes a real-SDK review/dismiss event with stable reviewer/task/revision identity, exact replay, contiguous revision checks, and same-revision conflict detection. **Pending:** exercise and observe decisions propagating between peers. |
| 02:15–02:35 | **Pending:** build the live view and collect full fold-0 model metrics, resource use, network evidence, replay evidence, and review propagation. The end card must state **Linux proxy run; native iPhone validation pending** and **CC BY-NC-SA 4.0 research only** only after those facts are collected. |

Host bundle preparation:

```sh
python prepare.py --source-dir /host-only/kolektor-sources \
  --round-id visual-quality-fold0-001 --out /host-only/edge-visual-quality-inputs
```

When the Dataset workflow has already produced the host-only inventory JSON,
consume that inventory and its local source-image tree instead:

```sh
python prepare.py --inventory /host-only/fold0-inventory.json \
  --images-root /host-only/fold0-images \
  --source-dir /host-only/kolektor-sources \
  --round-id visual-quality-fold0-001 \
  --out /host-only/edge-visual-quality-inputs
```

The inventory schema is version 1 with `dataset: "KolektorSDD"`, `fold: 0`,
the pinned source and split archive SHA-256 values, and rows containing only
`path`, `item_id`, `image_sha256`, and host-only `label`. The command reopens
the pinned archives, validates exact official fold-0 paths, items, image hashes,
and labels against the supplied inventory, then verifies every local image byte
stream before creating bundles. Direct ZIP preparation uses that same official
fold loader.

The output has `host/host-labels.json` (including host-only paths), a host assignment record, and
`peers/inspection-a` plus `peers/inspection-b`. Each peer bundle contains its
redacted manifest with paths only for its own assigned images, a pathless
label-free full assignment, the pinned model, and only its assigned images.
The shared assignment does not disclose another peer's source path. Keep the entire output on the host until bundles
are uploaded separately to their intended Sandbox peers. The prepared bundle
is input material, not run evidence.

After Sandbox has provisioned both containers, invoke one peer process per
container with that peer's bundle, its persistent store mount, the other
peer's stable DNS alias, the Ditto database UUID, TCP port, and a writable
JSONL event path. Inspection A uses its `manifest.json`, `images/`, and
`assignment-manifest.json`; Inspection B uses the matching B paths. Both pass
the frozen total with `--task-count 135`. The host/MCP launcher that uploads
these bundles, starts both commands, and mounts the protected license is still
pending.

After an initial converged run, start a fresh peer process with the same
persistent store path and inputs plus `--restart-replay`. This requires the
expected result IDs to exist before processing, then reports new and duplicate
writes and logical result counts. The guard is implemented but has not been
observed against the Ditto SDK.

An operator decision is a separate command inside either peer environment:

```sh
python review.py --database-id "$DITTO_DATABASE_ID" --stores /data/ditto \
  --peer-id inspection-a --port 22001 --neighbor-host inspection-b \
  --neighbor-port 22001 --round-id visual-quality-fold0-001 \
  --task-id "$TASK_ID" --observation-id "$RESULT_ID" \
  --decision review --revision 1
```

Use `--decision dismiss` for the alternate disposition. Replaying the same
reviewer/task/revision/content is idempotent; stale, skipped, or competing
revisions fail validation. Review commands use the real Ditto SDK and fixed
offline-license mount. The command reports `incomplete` after a local write;
one peer cannot verify replication. A host-side observer must read and compare
the immutable decision from both persistent stores before propagation passes.

Keep the peer link up for the entire run. WAN/cloud access is absent, but there
is no peer-link partition in this first demonstration. Network partition and
rejoin are a later experiment after Sandbox supports controlled link cuts.

## Dataset, split, and model

Use the existing KolektorSDD source and the Dataset brick's versioned image
definition and frozen official folds. The source has 399 images, 52 image-level
positives, 50 production items, and is licensed **CC BY-NC-SA 4.0**. This is
noncommercial research only; it does not authorize product or customer-data
use. Every item contains at least one defect, so the label is image-level and
does not support an item-level defect-free decision. Keep the story as generic
surface quality review; do not claim vehicle or can applicability.

Reserve all **135 images in official fold 0** as the held-out evaluation set.
Train the first-run grayscale-statistics logistic model on folds 1 and 2 only
(264 images). Fit its feature scaler and balanced logistic head on the host,
then export only the preprocessing/scaler parameters, coefficients, intercept,
threshold, and metadata needed by the small scorer. Use seed 41 and fixed
threshold 0.5. Freeze the code, parameters, artifact digest, and scenario
before any fold-0 inference. Do not use the existing all-data head: it has
seen fold 0. The existing pilot's approximately 4.1 KB serialized head is a
size reference; record the exact fold-1/2 artifact byte count and hash.

The peer's image runtime is Pillow plus Python standard library. Reject image
payloads larger than 16 MiB and decoded images wider or taller than 8192 pixels
or larger than 16 million pixels before pixel conversion or resize. Resize each
accepted grayscale image to 64x160 and split its height into three bands using
the same array-split boundaries as the host reference. For each band, compute
the 16-bin histogram density over [0, 1], grayscale quantiles at
[0, .01, .1, .25, .5, .75, .9, .99, 1], and absolute horizontal/vertical
difference quantiles at [.5, .9, .99, 1]. This yields 99 deterministic
features. Implement quantiles with the host's linear interpolation rule, round
feature outputs to float32 to match the deployed host baseline, and implement
the standardized logistic score and sigmoid using standard-library arithmetic.
Pin/hash the Pillow wheel and record feature-code version. Compare feature
values and scores with the host reference before sealing the run manifest. Do
not import a training framework or general numerical package in either peer.
The current `edge-lab` image contains Ditto and CBOR2 but not Pillow, so the
first run requires an image build that adds one hash-pinned Pillow wheel; it
does not require installing the host training stack in the peer image.
Before freezing the run manifest, require exact feature parity on the fixed
feature-check cohort and maximum absolute score difference <= 1e-6 between the
host reference scorer and peer scorer.

Use all 135 fold-0 images, assigning entire production items to peers. Before
inference, sort item groups by descending image count with item ID as the stable
tie-break; assign each next group to the peer with fewer assigned images,
breaking count ties in favor of **Inspection A**. Freeze the resulting item-
to-device and image-to-task mapping in the scenario, hash its canonical bytes,
and stage the same manifest on both peers. No item may be split. The manifest
contains no labels. It must list all 135 unique image IDs exactly once, and
the two assignment counts must sum to 135; show the exact counts it produces.
The labels stay on the host and are joined to the 135 returned prediction
records only after peer execution. Do not send labels to a peer.

Compute aggregate fold-0 image average precision, AUROC, recall, precision,
false-positive rate, confusion counts, and item-resampled confidence intervals
from all 135 peer predictions against the host-held labels. Report class counts,
per-peer counts, invalid/missing/duplicate predictions, inference latency, and
the exact model package size. Historical three-fold out-of-fold grayscale
baseline results (AP 0.717, 39/52 positives found, 30 false alerts) are context
only; they are not fold-0 results. Do not use a fold-0 label or metric to alter
the model, features, assignment, or threshold.

The first run demonstrates model utility only if fold-0 recall is at least
0.70, false-positive rate is at most 0.10, average precision is greater than
0.50, and every metric is computed from exactly 135 unique valid predictions.
These are exploratory thresholds for deciding whether to continue, not product
acceptance criteria. A pass does not establish generalization beyond this small
research dataset. If the quality gate fails, report the mesh behavior separately
and label model utility **not demonstrated**. Later compare with the frozen
MobileNetV3-Small pipeline, including conversion to ONNX/Core ML only after
measuring the small baseline on this same item-disjoint fold.

The Dataset brick's generic quality status for the historical image records is
`passed=false`; preserve that status. Independently validate image decoding,
source and fold hashes, labels, all 135 fold-0 IDs, and item-level isolation.
Record Dataset quality and external validation as separate results.

## Topology, mesh coordination, and records

Provision two different Sandbox environments using device presets, with unique
device IDs, separate Ditto persistence directories, and recorded CPU/memory
budgets. Use Sandbox's shared-network capability tracked by **ENG-197**. Its
network must be user-defined and report `peer_network.internal=true`. Attach
both peers to that network with stable DNS aliases and the Ditto TCP port.
Record network ID, aliases, ports, container/preset IDs, SDK/image versions,
and resource settings.

Before and during inference, run and record these connectivity checks from
**each** peer:

- **Egress negative:** from each peer, TCP connections to predeclared public-IP
  canaries and ports fail within the fixed timeout. Record the canary IPs,
  ports, timeout, timestamps, and connection outcomes. Separately record
  public-name DNS lookup behavior: Docker's embedded DNS may forward queries
  even on an internal network, so successful name resolution alone is not
  evidence of Internet connectivity or a failed isolation check. An absent
  WAN label alone is not proof of isolation.
- **Peer positive:** each peer resolves the other peer's Sandbox DNS alias and
  successfully opens a TCP connection to the declared Ditto port. Record the
  resolved peer alias/address and connection outcome. Keep the peer TCP path
  available throughout inference, restart, replay, review, and sync.

The database is configured for offline-only use with one authorized database
ID and two stable unique device IDs. Both peers execute the real Ditto SDK,
subscribe to round/task/result/review documents, and call SDK local writes and
sync directly. The SDK mesh stays connected peer-to-peer for the whole run;
cloud sync/relay is not used. There is no central coordinator. The frozen
manifest assigns work before the run, while Ditto replicates the live state.

Use versioned typed records. Exact retries use stable IDs; differing content at
an existing ID is a conflict. Implemented records are:

```text
round                 round_id, peer_ids, task_ids, task_count, model_sha256,
                      assignment_sha256
join                  round_id, peer_id
task_claim            round_id, task_id, owner_peer
result                round_id, task_id, item_id, image_id, image_sha256,
                      source_peer, model_sha256, finite score, decision,
                      write_started_at_utc
review_open           round_id, task_id, observation_id, open status
review_decision       round_id, task_id, observation_id, reviewer_id,
                      review | dismiss, positive revision
```

The projected lifecycle is `assigned → claimed → inferred → synced →
review_open → review | dismiss`. `synced` is a derived delivery state, not a
remote lock. A peer can claim only its manifest-owned task. Any off-owner claim
is retained as a conflict event and fails the round gate. A task with duplicate
events reduces to one canonical task/observation; identical replay is counted
as a duplicate delivery, not a second task. An ID reused with different
immutable contents is an integrity failure. Review revisions are monotonic;
same-revision disagreement is reported as a conflict and not resolved by
wall-clock last-write-wins.

`--restart-replay` is an explicit fresh-process replay check against the same
persistent Ditto directory. It requires the frozen result IDs to exist before
processing, reports new versus duplicate writes, and fails if it creates any
new record or logical result. A first-run sync measurement requires zero
persisted results for that round; replay reports `not_measured_replay` for
latency because old write timestamps cannot evidence a fresh delivery.
`review.py` accepts only the next contiguous
revision; reusing the same reviewer/revision with different content conflicts,
and competing events for one revision fail history validation.

Compute a canonical projection/digest from the frozen manifest and replicated
events so both peer queues can be compared. The two models do the same image
job; Ditto task state makes their coordination explicit. This first run tests
shared round membership, non-overlapping ownership, live result exchange,
restart persistence, replay safety, and review sync. It does not test a second
coordinator model or a peer-link partition.

## Privacy and offline license

Each image and any decoded pixels remain only on its assigned peer. Never
sync raw images, crops, embeddings, image paths, training labels, or license
material. The other peer sees task metadata and scores with an **image stays on
source device** placeholder, not a thumbnail. Host-held labels are joined to
predictions after execution for aggregate evaluation. Keep run artifacts
aggregate-only and sanitized.

Execution requires an authorized offline license token supplied through a
protected host-side Sandbox secret mount. For Ditto employees, sign in to the
production Ditto Portal with a `ditto.com` account, create a database, then
use its **Offline license token** section. If it is unavailable, request Ditto
admin-group access in `#it-helpdesk`. The local Ditto repository's
`crates/ditto-dev-licenser/README.md` documents the Portal flow. Use the
Portal-issued offline token; do not use local `ditto-dev-licenser generate`
or `keygen` flows.

The peer process reads the token only from the fixed protected secret mount.
Never place its value in the repository, profile, command line, environment
dump, MCP output, logs, or result bundle; do not copy or download the mount.
The database ID is configuration, not a substitute for the protected token.

## Exact gates and scope

**Mesh/field-flow pass** requires all of the following:

1. Two independent device-preset containers use unique device IDs and stores;
   `peer_network.internal=true`; TCP to every predeclared public-IP egress
   canary fails from each peer, public DNS behavior is recorded separately,
   and peer DNS/TCP-positive checks pass.
2. One pre-inference, hashed assignment manifest covers exactly 135 unique
   fold-0 images, assigns each item wholly to one peer, and has balanced
   peer counts whose sum is exactly 135. Both peers report the same manifest
   and model digests.
3. Both peers join the same round and produce exact same-round join, claim,
   result, and review-open ID sets from the frozen assignment; extra IDs fail.
   All 135 observations sync to both peer stores within 60 seconds. Review
   history and revisions are included in both deterministic queue digests.
4. Restart one peer while the peer mesh stays connected and WAN/cloud remains
   absent. Expected local records persist; replay creates zero extra claims or
   observations and no same-ID/different-content conflict. Both peers retain
   matching queue digests after restart and replay.
5. A review and a dismiss event written on one peer reach the other peer and
   survive restart/replay with the same canonical revisions. No automated
   rejection or machine actuation occurs.
6. No image, path, embedding, host label, or license material appears in the
   peer-to-peer synced documents or evidence. Record every error and retry;
   do not silently omit failed predictions, writes, or sync events.

Each result carries a UTC write-start time. A receiving peer records when a
live SDK store read first sees each remote result and computes an observed
delay. The runner enforces the 60-second result visibility gate and fails
closed when records or timestamps are missing. This is a poll-time upper bound;
a host observer must combine both peers' measurements to report aggregate
p50, p95, and maximum. Review propagation stays incomplete until both stores
are read. Any missing ID, count mismatch, failed egress-negative check, failed peer-positive check, cloud route, inability to
write without WAN, non-idempotent replay, digest divergence, privacy leak, or
sync beyond 60 seconds fails the mesh gate. Missing license, Sandbox network,
model artifact, or source inputs means **blocked/not run**, never pass.

**Model-utility pass** requires all four predeclared fold-0 criteria above.
Report the measured statistics and item-resampled intervals whether they pass
or fail. Compute them only after joining all 135 unique peer predictions with
the host-held labels.

**Network partition is deferred.** Do not claim a peer link was cut or later
rejoined in this run. That gate requires an explicit, tested Sandbox link
controller and will be added to a later protocol.

**Native-device compatibility is deferred.** Sandbox presets bound Linux
container CPU/memory/storage; names such as `iphone-*` do not run iOS or emulate
native APIs. This run cannot establish iPhone model latency, memory, battery,
thermals, radio behavior, Core ML parity, or app compatibility. MobileNet and
ONNX/Core ML are later comparisons, followed by simulator and physical iPhone
gates.

## Run record

The runner records a digest of the SDK's actual local
`presence.graph.local_peer.peer_key` as device identity evidence. A configured
peer alias alone is not identity evidence.

Before execution, freeze the scenario and record source/fold hashes, host-held
label digest, model/scorer package digest and bytes, feature parity evidence,
135-image assignment manifest and hash, per-peer expected counts, network
configuration/checks, container resource presets, Ditto/Pillow/Python versions,
and gate definitions. Use the Dataset brick for versioned/frozen partitions,
the ML brick where it supports host training (otherwise document the trainer),
Ditto SDK processes for peer state, and Evals for terminal gate outcomes.

After execution, record run ID, code revision, actual peer and task counts,
prediction IDs/digests, all metric values, p50/p95 inference/write/sync times,
restart/replay results, review revisions, resource use, egress/DNS/TCP check
outcomes, errors/retries, deviations, and separate mesh/model pass/fail/block
statuses. Do not collect source image bytes or secret contents.

There is no run result yet. No storyboard event or acceptance gate is passed
until supported by collected evidence.
