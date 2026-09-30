# Protocol: edge-ditto-device-flow-001

**Status:** Planned, 29 September 2026. No SDK integration result has been
measured. This protocol tests the field path: local input → model inference →
typed observation → Ditto SDK local store → subscribed peer. It does not
export inference records as files or require cloud connectivity.

## Functional N-device stage

Run **N separate macOS processes**, each with its own Python interpreter and
real Ditto Python SDK instance. Spawn each process independently; do not fork
an open SDK handle. Give peers the same test database ID but unique device IDs,
persistence directories, and `127.0.0.1` TCP listen ports. Use
`DittoConfigConnect.small_peers_only()`, an authorized offline-only license,
set with `peer.set_offline_only_license_token(...)`, and explicit static TCP
neighbors for a declared topology. Register receiving
subscriptions and call `peer.sync.start()` for connected phases; stop sync for
the separate whole-node-offline case. For a selective network partition, cut
only the declared TCP edges and leave unaffected peers syncing; record the edge
schedule. No cloud route is part of this experiment.

Start with N=2 to validate the harness, then run N=4 and N=8 in line and
full-mesh topologies. Pin the SDK wheel version/hash, model artifact, replay
cohort, node-to-model assignment, topology, random seed, and run duration.
Each process consumes its own fixed, timestamped local input stream, runs a
frozen model (begin with the FD001 sensor comparator), and writes an observation
to its own Ditto store for each inference. Later, assign different frozen model
families to different nodes and test typed task/result coordination. If model
inference initially runs in another process, record that boundary and do not
call it an iPhone-runtime result.

Each observation should have a stable ID derived from device ID, input
identity, and model artifact hash so that a replay is idempotent while a new
model revision creates a distinct observation. Record source timestamp, model
name/version and artifact hash, schema version, bounded prediction/score, and
creation time. Keep raw payloads out of result records unless their retention
and sync scope are intentional. Use the SDK's DQL write API with an explicit
`ON ID CONFLICT DO NOTHING` policy for exact replays; flag a same-ID,
different-content record as an integrity error by reading back the stored
document and comparing its immutable fields with the proposed observation.
Measure complete inference-to-committed-write latency at several input cadences
and payload sizes to expose write backpressure, database growth, and sync cost.
Define a retention rule for raw inputs and observations before the run. Include
a long disconnected interval at the expected field write cadence and a higher-rate
stress interval; measure database bytes over time, not only the final file size.

Predeclare acceptance thresholds before the run. At minimum, verify:

1. Writes succeed with peer and cloud links absent; queries return the
   expected count and typed fields locally.
2. After closing and reopening each peer on its own database directory,
   observations remain and replaying an input does not duplicate its record.
3. After reconnecting the declared topology, every subscribed peer converges
   to one stored observation per eligible stable ID, including offline backlogs
   from all nodes. Record per-peer convergence time and transferred bytes.
4. A selective link partition/rejoin and concurrent update do not produce an
   ambiguous final observation. Record conflict and schema-version behavior
   explicitly, including multi-hop delivery in a line.
5. In the later mixed-model coordination run, a typed task reaches an eligible
   model node, its result returns to the requester, and duplicate or stale
   claims cannot trigger an unapproved command. Record completion and failover
   outcomes separately from observation replication.

Set an explicit per-device storage ceiling and maximum disconnected duration
for each run. Fail the storage gate if growth under the declared retention rule
exceeds that ceiling, or if the backlog cannot converge after rejoin within the
declared time limit. Record p50/p95 inference, local-write, and end-to-end
latency separately; write failures/retries, backlog size, peak database size,
database growth rate, and peer delivery lag for each node and the whole mesh.
The N-device stage can establish SDK persistence/replication and, after the
separate typed-task run, application coordination semantics on a development
host. It does not prove iPhone memory, battery, thermal behavior, BLE/AWDL
transport, or the converted model's prediction parity.

The Ditto repository's `topology-runner` can launch custom peer commands under
declarative N-node line or full-mesh graphs and collect per-node logs. Use it
for repeatable larger runs once the Python peer program accepts its assigned
listen/neighbor settings. Its built-in event scheduler handles node shutdown;
its proxy supports static latency, jitter, and bandwidth settings. Selective
link cut/rejoin needs a separate proxy controller or harness extension before
gate 4 runs. The first N=2 run can follow the existing Python SDK loopback
fixture directly.

## iPhone stage

Run the same typed observation contract in a thin Swift iPhone app with the
actual packaged model and Ditto SDK. Replay the frozen inputs on a specified
iPhone model and iOS version; compare predictions with the lab reference and
measure full pipeline p95 latency, peak RAM, storage growth, energy, and
offline/rejoin behavior with a second peer. Only this stage can clear the
phone-class resource gate.

## SDK source and prerequisites

The local `getditto/ditto` checkout at `d89fb3480838` includes
`sdks/python/tests/sync/conftest.py`, which connects two real SDK peers with
separate stores and explicit loopback TCP ports. The public `dittolive-ditto`
preview wheel for Apple Silicon bundles `libdittoffi`, so this macOS stage can
run without full Xcode. Python 3.12 and `uv` are available on this host; the
wheel is not installed. Pin and verify its version/hash before use. SDK sync
requires an authorized offline license supplied outside the experiment record;
none is configured in the current shell. The iPhone stage requires an iOS build;
a simulator can rehearse functional behavior, while a physical iPhone is
required to clear the phone-class resource and radio gate.
