# Protocol: edge-ditto-device-flow-001

**Status:** N=2 runner implemented, 30 September 2026. No licensed SDK integration
result has been measured. The `edge-lab` Linux base image imports Ditto
Python SDK `5.2.0.dev0` but has not produced a peer run. This protocol tests the
field path: local input → model inference → typed observation → Ditto SDK local
store → subscribed peer. It does not export inference records as files or
require cloud connectivity.

## Single-container Linux rehearsal

Build a sealed derivative of the [edge-lab base image](../../../edge-lab/README.md)
as described below. Its reviewed entrypoint starts two separate peer processes
inside one container, each opening its own SDK handle and using a separate
persistence directory and loopback TCP port. This stage establishes that the
SDK wheel loads in Linux and rehearses local writes, restart persistence, and
explicit TCP peer sync with one shared test database ID. Its topology and run
outputs must be recorded using the same manifest and artifact rules below.
An authorized offline license is supplied through a protected mount at run time,
never baked into the image or profile. N=4/N=8 runs follow only after the
two-peer path is measured.

Peers inside one container share a network namespace. Record that limitation
and do not use this stage as evidence of independent device networking,
selective physical-link failure, iPhone runtime behavior, or radio transport.

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

## Companion-X execution and evidence

The checked-in N=2 harness is `run.py`, with a strict manifest in
`scenario-n2.json` (schema version 2). It pins both the file and embedded payload hashes for the
cataloged FD001 logistic scorer and cohort, plus the approved installed
`dittolive-ditto` distribution digest
`d7dfdea1ba6c0a02fd772e923a5cc46362b036e49d4c05371622d63a21bb3990`.
That SDK digest was measured from the current `edge-lab` container's 38
hashable installed distribution files on 30 September 2026. A changed image
or SDK build requires a reviewed scenario revision before a run can pass.
Supply the cataloged model and cohort files by path to `sealed_image.py`; they
are not copied into Git. Build only after review freezes `run.py`, `peer.py`,
`contracts.py`, this protocol, `scenario-n2.json`, and the fixed entrypoint.
The [sealed image guide](sealed_image.md) describes the allowlisted build
context, source/SDK pins, license-free preflight, and generated host-local
`edge-n2-sdk` Sandbox profile. Its image has a fixed entrypoint and `run`
command. No upload, interactive execute, arbitrary file download, or raw
Docker copy is available through the secret-enabled Sandbox environment.

Provide the authorized offline license as the named `ditto-offline-license`
secret reference, whose protected host file is mounted at
`/run/secrets/ditto-offline-license`. Never place its bytes in a command,
environment variable, profile, repository file, or evidence artifact. Provision
the generated profile through Companion-X Sandbox on the current code; confirm
its exact image ID, internal network, ARM64 platform, one CPU, 512 MiB limit,
secret marker, and no setup commands before launch. The entrypoint runs the
frozen loopback scenario and writes only `/evidence/run-001`.

After the container exits, a trusted host-side collector validates its build
pin and Docker provenance, copies only the declared manifest/index/peer
projections, verifies their hashes and schema, and removes the container even
when collection fails. This collector is a host operation outside Sandbox MCP.
Invoke `collect_sealed.py` with the full 64-hex `--container-id`, generated
`--build-evidence`, frozen `--scenario`, cataloged `--model` and `--cohort`,
and a new `--output` directory. It validates model/cohort bytes against the
build and recomputes predictions before publishing four evidence files. Keep
the caller's host model/cohort files available until collection finishes.
Do not read container logs or copy the entire evidence directory. A passing
license-free preflight and copied files alone do not establish SDK sync; the
validated run manifest must show both real peers passed persistence, exact
replay, and convergence. The container must be explicitly removed if a trusted
collector cannot run. The Sandbox orphan sweep has no automatic production
scheduler; its ten-minute evidence hold applies only when a sweep is invoked.

The runner verifies the complete cohort's prediction parity before starting
either child process. Each child opens the fixed offline-license secret at run
time, writes and queries its local observation, closes and reopens its own
store, replays the same stable ID, then subscribes and syncs over its declared
static TCP neighbor. Peer stores are isolated temporary directories and are
removed after the run; only per-peer content digests are retained so
SDK-private state or credentials cannot enter the artifact directory. The
runner writes sanitized prediction projections, environment/version details,
and a machine-readable result manifest, captures but discards raw process
output, and links artifact hashes from `run-index.json`. The FD001 cohort has
no source-event timestamp, so the runner records that omission rather than
inventing one. Its ground-truth RUL label is evaluation data and is not synced
in the production-shaped Ditto observation. A run is not evidence until both
real SDK child processes pass
persistence, exact replay, and two-peer convergence. Pure contract tests do
not set that status. Record the pursue/revise/stop decision in `results.md`;
do not treat a live dashboard or in-memory tracker as the only evidence.

The N=2 scenario is checked against an independent, reviewed content digest,
so replacing the model and cohort together with self-consistent hashes fails
preflight. The parent snapshots the scenario and both artifacts into a private
temporary directory before validation and passes those snapshots to both peer
processes. Peer IDs are constrained to safe lowercase path components. Each
peer reports a digest of its installed Ditto distribution files; the parent
independently computes the same digest and requires it and both peer reports to
match the approved scenario pin. The parent also stages read-only copies of
`run.py`, `peer.py`, and `contracts.py`; children execute the staged peer and
contracts code. Source and staged code hashes must still match their prelaunch
values after the children finish, and those prelaunch values are written to the
index. A code change during execution produces `integrity_failed`, without a
passing manifest. The manifest records the SDK digest alongside the artifact
pins. Worker output must
contain exactly one strict JSON result marker with no duplicate keys. These
checks establish provenance of the local inputs and installed SDK bits, while
the live run remains necessary to establish actual SDK sync behavior.

The frozen N=2 policy requires at least 20 observations per latency metric,
zero write failures, no more than 10 MiB peak measured database growth per
peer, and no more than 10 MiB SDK raw stream bytes sent or received per peer.
Its exploratory p95 ceilings are 100 ms selected-row inference, 500 ms first
local write/query, 10 s peer delivery, and 15 s end to end. Two selected rows
cannot satisfy the 20-sample floor, even if both functional peers pass.
The end-to-end interval includes the deliberate close/reopen, exact replay,
subscription, and convergence cycle; peer delivery includes process startup
skew and polling. These are rehearsal-cycle measurements, not steady-state
field inference-to-delivery or phone battery/thermal evidence. Report the
functional result, each performance gate, metric availability, and the
`eng184_closure_ready` decision separately.

Expose new, narrow start/status/cancel/result MCP tools through Companion-X at
run boundaries. Its Workflow brick can coordinate dataset, training, peer-run,
and evaluation steps after the peer-run target is allowed and a workflow
definition is registered. Named MCP runs also need durable SQLite state and a
nonempty run key. Keep prediction writes and peer sync inside the runner's SDK
processes, not as one MCP call per observation. Use the Dataset
brick for frozen input definitions and partitions, the ML brick for supported
training and model references, and the Evals brick for terminal gate outcomes
with artifact hashes.

Companion-X Sandbox has a separate device-preset catalog. Restart its MCP
process on the current Sandbox code with `SANDBOX_ADAPTER=docker` and
`SANDBOX_PROFILES_DIR` pointing to the profile directory. Select the generated
`edge-n2-sdk` profile for this first licensed rehearsal; its fixed resource
budget is a Linux ARM64 proxy, not an iOS simulator. The checked-in runner owns
peer processes, SDK stores, topology, and evidence. For separate containers,
use a shared internal Sandbox peer network with a unique alias per device; the
distributed peer mode below connects those aliases. The single-container
loopback gate is not evidence of distinct device networking.

## Separate Sandbox-container N=2 mode

`peer.py` accepts explicit `--mode distributed` for one peer process in each
of two distinct Sandbox containers. This is configuration support, not
evidence that the containers have run or synced. Keep `run.py`'s default
loopback rehearsal unchanged. Provision both containers with the same Sandbox
`peer_network.network_id`, distinct `peer_network.alias` values, and the same
declared internal port; set the Sandbox peer network's `internal: true` to
remove its default external route. Before calling the run offline-only, verify
that the two aliases resolve and reach each other while an external endpoint
is unreachable. Bind each Ditto listener to `0.0.0.0`; connect to the other
container's Sandbox DNS alias and internal port. Configure each process with
that peer's own ID and `--listen-port`, plus the counterpart's
`--neighbor-host` and `--neighbor-port`:

```sh
python peer.py \
  --scenario /tmp/edge-ditto-device-flow-001/scenario-n2.json \
  --model /tmp/edge-ditto-device-flow-001/model.json \
  --cohort /tmp/edge-ditto-device-flow-001/cohort.json \
  --stores /var/lib/edge-ditto-device-flow-001 \
  --peer-id sensor-peer-a \
  --mode distributed \
  --listen-interface 0.0.0.0 \
  --listen-port 24225 \
  --neighbor-host edge-peer-b \
  --neighbor-port 24225
```

Run the counterpart with `--peer-id sensor-peer-b` and `--neighbor-host
edge-peer-a`. Supply the offline license only through the protected secret
mount. Each peer emits a strict result projection whose topology records mode,
listen interface/port, and neighbor hostname/port. Hostnames and ports are
topology metadata; token contents and secret paths are excluded. Collect one
sanitized `EDGE_DITTO_RESULT` record per container and combine it with the
Sandbox peer-network metadata when preparing a reviewed run manifest. This mode
does not add cloud connectivity, host-published ports, or device-radio
emulation.

## iPhone stage

Run the same typed observation contract in a thin Swift iPhone app with the
actual packaged model and Ditto SDK. Replay the frozen inputs on a specified
iPhone model and iOS version; compare predictions with the lab reference and
measure full pipeline p95 latency, peak RAM, storage growth, energy, and
offline/rejoin behavior with a second peer. Only this stage can clear the
phone-class resource gate.

## SDK source and prerequisites

The Ditto Python SDK test suite's loopback fixture connects two real SDK peers
with separate stores and explicit TCP ports. The current `edge-lab` image
imports version `5.2.0.dev0`; this runner has not exercised that SDK yet. The
authorized offline license token is the remaining prerequisite for the first
peer run and must stay outside experiment records. The iPhone stage requires
an iOS build; a simulator can rehearse functional behavior, while a physical
iPhone is required to clear the phone-class resource and radio gate.

For Ditto employees, `Projects/ditto/crates/ditto-dev-licenser/README.md`
documents the production Portal path: sign in with a `ditto.com` account,
create a database, request addition to the Ditto admin group in `#it-helpdesk`
if the offline-token section is not available, then generate the token in the
Portal's **Offline license token** section. The internal
[Ditto discussion notes](https://app.notion.com/p/35f9d9829a328029b21dffd0a49f92b8?pvs=204)
also identify that Portal section and confirm offline mode needs the database
ID plus the offline token. Use Portal issuance for this run; do not invoke the
local `ditto-dev-licenser generate` signer or `keygen` flow. Save the token
only to the protected host-side file configured by the Sandbox secret mount;
never put it in the profile, command line, environment dump, repository, or
run artifacts.
