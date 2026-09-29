# Protocol: edge-ditto-device-flow-001

**Status:** Planned, 29 September 2026. No SDK integration result has been
measured. This protocol tests the field path: local input → model inference →
typed observation → Ditto SDK local store → subscribed peer. It does not
export inference records as files or require cloud connectivity.

## Functional mock-device stage

Use two isolated macOS processes as stand-ins for devices, each opening a
**real Ditto Swift SDK instance**. Give them the same test database ID and
separate persistence directories. Use the SDK's `.smallPeersOnly` connect mode
and an authorized offline-only license. Configure paired TCP transports on
`127.0.0.1` with explicit ports; disable every cloud route. Pin the SDK source
revision, model artifact, inference adapter, and replay cohort. Register the
receiving peer's subscription and call `ditto.sync.start()` on both instances
before the connected run; stop sync on both for the offline interval.

The first process consumes a fixed, timestamped stream of local inputs, runs
one frozen model (begin with the simple FD001 sensor comparator), and writes
an observation to its Ditto store for each inference. If inference initially
runs in a separate process, record that boundary and do not call it an
iPhone-runtime result.

Each observation should have a stable ID derived from device ID, input
identity, and model artifact hash so that a replay is idempotent while a new
model revision creates a distinct observation. Record source timestamp, model
name/version and artifact hash, schema version, bounded prediction/score, and
creation time. Keep raw payloads out of result records unless their retention
and sync scope are intentional. Use the SDK's DQL write API with an explicit
`ON ID CONFLICT DO NOTHING` policy for exact replays; flag a same-ID,
different-content record as an integrity error by reading back the stored
document and comparing its immutable fields with the proposed observation.
Measure complete
inference-to-committed-write latency. Run at several input cadences and payload
sizes to expose write backpressure, database growth, and sync cost. Define a
retention rule for raw inputs and observations before the run. Include a long
disconnected interval
at the expected field write cadence and a higher-rate stress interval; measure
database bytes over time, not only the final file size.

Predeclare acceptance thresholds before the run. At minimum, verify:

1. Writes succeed with peer and cloud links absent; queries return the
   expected count and typed fields locally.
2. After closing and reopening the first SDK instance on the same database
   directory, observations remain and replaying an input does not duplicate
   its record.
3. After connecting peers over local transport, the subscribed second peer
   converges to one stored observation per stable ID, including the backlog
   written offline; record convergence time and transferred bytes.
4. A peer disconnect/rejoin and concurrent update do not produce an
   unapproved command or ambiguous final observation. Record conflict and
   schema-version behavior explicitly.

Set an explicit per-device storage ceiling and maximum disconnected duration
for each run. Fail the storage gate if growth under the declared retention rule
exceeds that ceiling, or if the backlog cannot converge after rejoin within the
declared time limit. Record p50/p95 inference, local-write, and end-to-end
latency separately; write failures/retries, backlog size, peak database size,
database growth rate, and peer delivery lag. The mock-device stage proves SDK
persistence/replication semantics on a development host. It does not prove
iPhone memory, battery, thermal behavior, BLE/AWDL transport, or the converted
model's prediction parity.

## iPhone stage

Run the same typed observation contract in a thin Swift iPhone app with the
actual packaged model and Ditto SDK. Replay the frozen inputs on a specified
iPhone model and iOS version; compare predictions with the lab reference and
measure full pipeline p95 latency, peak RAM, storage growth, energy, and
offline/rejoin behavior with a second peer. Only this stage can clear the
phone-class resource gate.

## SDK source and prerequisites

The local `getditto/ditto` checkout at `d89fb3480838` exposes
`Ditto.open(config:)`, `DittoConfig.persistenceDirectory`,
`ditto.store.execute(query:arguments:)`, `ditto.sync.start()`, and
`registerSubscription`; its Swift tests include local persistence and
loopback-connected instances. The local machine currently has Xcode Command
Line Tools but no `xcodebuild`, iOS simulator, or prebuilt Ditto Swift framework.
Building and running even the macOS harness first requires a full Xcode and
native `libdittoffi.a` build/link setup, or another configured host. The iPhone
stage additionally requires an iOS build. A simulator can rehearse functional
behavior; a physical iPhone is required to clear the phone-class resource and
radio gate. SDK execution requires an authorized Ditto license supplied outside
the experiment record.
