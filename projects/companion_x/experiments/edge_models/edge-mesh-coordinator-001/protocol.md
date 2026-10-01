# Protocol: edge-mesh-coordinator-001

**Status:** Protocol proposal for ENG-195 under ENG-188. No Ditto SDK,
multi-peer, fault-injection, or device result has been measured for this
experiment. Follow the sequence below; do not infer SDK conflict, ordering,
delivery, or convergence guarantees from this plan.

## Question and hypothesis

Can heterogeneous device-local specialist models contribute typed
observations to a shared offline workflow, while a small deterministic
coordinator assigns and tracks work safely through duplicate delivery, peer
loss, and rejoin? After the protocol and deterministic baseline have trustworthy
labels, does a tiny learned router improve peer selection without weakening
the same deterministic safety gates?

This tests the Ditto AI Strategy direction: useful intelligence at the point of
work; agent observations and task state that travel across the mesh and
reconcile after reconnect; task-quality, resource, and accepted-outcome
evidence. The Notion interoperability strategy recommends a deterministic
state/session manager first, then an advisory learned router only after the
protocol is stable. This is a proposal, not a measured result.

## Sequence

1. **N=1 specialist baseline.** Run one frozen specialist against its own
   task-quality evaluation split. Record model quality, abstention/error
   behavior, inference p50/p95, artifact bytes, peak memory, and energy when a
   real target exposes it. No coordinator or Ditto peer claim is made.
2. **N=2 observation replication gate.** Use the existing
   `edge-ditto-device-flow-001` runner: two independent SDK peers, separate
   stores, the same frozen scorer, and internet disabled. It writes, persists,
   replays, and synchronizes typed model observations. This gate proves only
   those operations; it does not implement task/session state, capability
   selection, or coordination. Record SDK version, topology, device/runtime,
   license gate, and evidence for every observed behavior. A container
   rehearsal is not a phone result.
3. **N=2 typed-coordination gate.** After the observation gate, implement and
   freeze the versioned capability/task/claim/result/session records and
   deterministic reducer. Run two peers with distinct roles/models and prove
   eligible routing, task/result provenance, restart, duplicate delivery,
   stale claim handling, and peer loss/rejoin. This is a separate protocol
   revision and run; do not attribute its behavior to the existing observation
   runner. Record the reducer/policy versions and exact accepted record sets.
4. **N=4 heterogeneous fault run.** Use at least sensor, audio, and vision
   specialist roles plus a coordinator role across four peers. Inject peer
   loss/rejoin, duplicate tasks, stale capability records, and simultaneous
   conflicting claims from a separately frozen orchestration-fault corpus.
   Exercise all faults offline, then reconnect and measure reconciliation.
5. **Learned-router comparison (later gate).** Only after deterministic runs
   produce reviewed, outcome-grounded routing labels, replay the same held-out
   fault scenarios with a tiny router selecting among eligible peers. Compare
   with deterministic routing. The router may rank or abstain; the deterministic
   coordinator still validates eligibility, task identity, expiry, and policy.
   Never train or tune on the comparison holdout.

The current maintenance-dispatch demo is a single trained sensor model plus a
deterministic SQLite coordinator with two logical workers. It validates a
container workflow/replay rehearsal only: its 100 NASA FD001 endpoints are not
four physical peers, synchronized multimodal field events, Ditto records, or
training labels for this router. Keep its result separate from all runs here.

## Versioned record contract

Use immutable, versioned records and a deterministic application reducer.
Field names below are required; encode timestamps as UTC RFC 3339 and digests
as lowercase SHA-256 hex. `schema_version` is an integer and unknown major
versions are rejected. IDs are deterministic from record role, group/session,
and source event or task identity; a same-ID/different-payload collision is an
integrity failure. Do not use wall-clock last-write-wins as application policy.

| Record | Required fields |
| --- | --- |
| Common envelope | `schema_version`, `record_type`, `record_id`, `group_id`, `session_id`, `producer_device_id`, `created_at`, `causation_ids[]` |
| Capability | common; `capability_id`, `revision`, `role`, `model_id`, `model_version`, `artifact_sha256`, `input_modalities[]`, `output_schema_version`, `runtime_id`, `valid_from`, `expires_at`, `status`, `authorization_scope`, `policy_version` |
| Observation | common; `observation_id`, `source_event_id`, `source_time`, `task_kind`, `model_id`, `model_version`, `artifact_sha256`, `output_schema_version`, `bounded_output`, `confidence_or_score`, `input_ref`, `retention_class` |
| Task | common; `task_id`, `task_kind`, `state`, `expires_at`, `required_capabilities[]`, `observation_ids[]`, `policy_version`, `policy_sha256`, `scenario_sha256`, `revision`, `terminal_reason`, `authorized_device_ids[]` |
| Claim | common; `claim_id`, `claim_revision`, `task_id`, `claimant_device_id`, `capability_id`, `task_revision`, `issued_at`, `expires_at`, `claim_status`, `authorization_scope`, `policy_version` |
| Result | common; `result_id`, `task_id`, `claim_id`, `claim_revision`, `worker_device_id`, `task_revision`, `outcome`, `result_ref`, `completed_at`, `model_id`, `artifact_sha256`, `input_ref` (content-addressed input digest), `policy_version`, `policy_sha256`, `scenario_sha256` |
| Session | common; `coordinator_device_id`, `session_kind`, `opened_at`, `closed_at`, `policy_version`, `membership_epoch`, `status`, `authorized_device_ids[]` |

In schema v1, a Task record is only a `proposed` task and its
`terminal_reason` is null. Active and terminal task states are reducer outputs
derived from validated claims/results; a proposal cannot assert its own
completion, abstention, or cancellation. A future explicit authorization record
is required before policy or human cancellation can become a terminal input.
The Session producer must equal its declared `coordinator_device_id`; a caller
must also pin the trusted coordinator ID outside received records and apply it
to Session and Task producers. This is a local policy check, not cryptographic
identity proof.
The caller also pins the expected policy version and exact policy-file digest;
the reducer rejects Session or Task records that declare another version or
digest. A record cannot establish its own policy authority.

Schema v1 `bounded_output` has no free-text value: it permits only `signal`
(boolean), `class_id` (integer 0–65535), `score` (finite float 0–1), `count`
(integer 0–1,000,000), and `severity_code` (integer 0–5). Each model's
`output_schema_version` must provide the external mapping from category code
to meaning. These structural limits reduce accidental private-content sync;
they cannot prove that a malicious numeric code does not encode private data.
The run policy must still authorize the producer and output schema.
Only `output_schema_version=1` is accepted until a versioned schema registry
is implemented.
An Observation's producer must belong to the session at its `created_at`
record-write time and have a matching available model capability then.
`source_time` describes the sensed event and may predate membership; it is
self-declared, not proof of event origin or time. Task-specific policy must
decide how old an input may be.

Capability and Claim status changes are append-only revisions under one
logical ID. Each revision has a distinct deterministic record ID, contiguous
revision number, and increasing creation time. Only status and version/time
may change; ownership, model, policy, and validity window stay fixed. An
`available` capability may become `unavailable`, and a `proposed` claim may
become `withdrawn`. A retry or renewal uses a new logical ID. The reducer
uses the effective revision at its policy clock and at a historical result's
completion time, so a later withdrawal cannot erase a valid earlier result.
Claimants must be authorized in an open Session at `issued_at` and continuously
remain members while the claim is considered. `created_at` is the record-write
time; `issued_at` may precede it, but a Claim must be recorded before a Result
can complete under it. A Result's `completed_at` may precede its own record
write. These timestamp checks rely on declared application clocks; SDK write
durability and clock trust still require an integration gate.

Keep raw audio, images, and high-rate sensor payloads local by default. Sync a
bounded output and content-addressed input reference; share raw inputs only when
the task requires it and the run records retention and access scope. A
capability is a time-bounded advertisement, not proof of a reachable or
authorized peer. Expiry uses an explicit policy clock/tolerance recorded per
run; confirm target SDK clock behavior before interpreting it.

## Authority and deterministic behavior

- Specialist models emit observations only. They cannot alter shared task or
  session state, choose an unauthorized peer, or execute an action.
- The deterministic coordinator validates schema, group/session membership,
  capability freshness, task expiry, and local policy before proposing work.
  A learned router can only rank eligible candidates or abstain.
- Task state is derived from versioned records using the pinned reducer/policy
  version. Repeated identical IDs are idempotent; conflicting bytes for one ID
  fail closed. Keep accepted observations, claims, and results inspectable.
- Once replicas have the same accepted record set, replaying those records in
  any arrival order (including duplicate delivery and restart) must produce the
  same canonical task/session state bytes and state digest. Test all feasible
  permutations for small conflict scenarios and seeded permutations for larger
  traces. During a partition, replicas may have different accepted sets; the
  equality gate applies after the declared records have reconciled. Conflicting
  claims, stale revisions, and terminal transitions must have explicit reducer
  outcomes, not wall-clock arrival-order behavior.
- Claims are proposals, not locks or proof that only one peer will execute.
  For a given observed candidate set, choose the winner by a pinned total
  ordering over `(task_id, task_revision, claimant_device_id, claim_id)` and
  record the losers. This app-level tie-break does not prevent simultaneous
  side effects at isolated peers; side effects remain disabled in this
  experiment. Validate stale claims and reclaims after expiry explicitly.
- Only application policy or a human may approve an external action. This
  experiment produces recommendations/results, never equipment actuation.
- Ditto behavior is an empirical question: record duplicate delivery,
  subscription visibility, offline writes, reconnect reconciliation, and
  conflicts as observed on the exact SDK/runtime. Do not describe any as an
  SDK guarantee unless supported by versioned documentation and measured here.

## Frozen data and fault corpus

Maintain two independently versioned and hashed corpora:

1. **Model task-quality datasets:** modality-specific examples and ground truth
   for each specialist (sensor, audio, vision). Create/train/evaluate these
   through the Dataset and Evals workflow; group-split by source asset/session
   to prevent leakage. Do not combine unrelated modalities as if time-aligned.
2. **Orchestration fault corpus:** synthetic, model-independent event traces
   with a frozen seed, topology, scheduled fault times, expected reducer state,
   eligible peers, and expected safety outcome. Cases cover peer loss/rejoin,
   duplicate task/result delivery, expired capability, concurrent claims,
   stale claim/result, and repeated replay. Never use this corpus as specialist
   training data or as learned-router labels. Keep train/validation/test
   scenarios partitioned by scenario template and topology; publish the exact
   corpus digest before execution.

For learned-router labels, capture deterministic-baseline eligible candidates,
task context, selected route, completion/failure, and human-reviewed outcome.
Do not label a route “correct” merely because it was selected. Freeze a new
label set and independent held-out scenarios before router training.

## Outcomes and gates

Report per device and whole mesh: task completion and abstention; duplicate
execution proposals; unsafe/ineligible route and policy violations; stale
claim acceptance; conflicting claims; failover/reclaim success; local and
end-to-end p50/p95 latency; peer-loss-to-recovery time; rejoin-to-reconciliation
time; bytes transferred; peak database size/growth; write/retry/error counts;
and model/runtime versions. Report specialist task metrics separately from
coordination metrics. On real hardware, add peak memory, energy, and thermal
measurements; otherwise mark each unavailable.

Hard gates for every stage: exact replay does not create a second logical
task/result; equivalent accepted record sets reduce to byte-identical canonical
task/session state regardless of arrival order; stale or ineligible peers are
not selected by the reducer; no model or claim directly causes a side effect;
and each result cites its input, model artifact, claim, policy, and scenario
digests. N=2/N=4 convergence,
latency, resource, and recovery targets must be set before the first measured
run from the intended deployment envelope. Until then, numerical thresholds
are **provisional/unset**; report measurements and deviations without declaring
the mesh production-ready.

The N=1 model-quality gate needs its own preregistered task metric and baseline.
The learned-router gate requires a label-reviewed held-out comparison, route
accuracy/abstention, unsafe-route rate, calibration, fallback rate, and added
latency/bytes/memory/energy. Promotion requires no safety-gate regression and a
predeclared improvement in accepted task outcomes; the numerical improvement
threshold is **provisional/unset** until the deployment owner sets it.

## Reproducibility and evidence

Before each run, pin the protocol revision, SDK version/wheel hash, model and
dataset hashes, task/fault corpus hashes, reducer and policy versions, device
and OS/runtime, topology, peer-role assignment, seed, connectivity schedule,
clock assumptions, and measurement tools. Store sanitized per-peer result
records and a manifest with artifact digests; exclude credentials, raw media,
and private SDK stores. Record protocol deviations and unavailable metrics.
Tests of schemas/reducers are useful contract evidence but do not count as an
SDK peer run. A container run does not clear the iPhone/Android app, radio,
energy, thermal, or field-data gates.

## Sources

- [Ditto AI Strategy — Unstoppable Intelligence](https://app.notion.com/p/3e39d9829a3281c9ae29ccc2fdb0ceee): Executive Summary; Models; Workflows; Distributed Intelligence; Trust & Economics.
- [Edge model interoperability and on-device coordinator strategy](https://app.notion.com/p/3eb9d9829a32810f9a04d7a620f80fab): deterministic-first recommendation, versioned record proposal, evaluation sequence, and open questions.
- [`edge-ditto-device-flow-001` protocol](../edge-ditto-device-flow-001/protocol.md): current N=2 runner and SDK prerequisites; no measured peer result yet.
- [`edge-maintenance-dispatch-demo-001` protocol/results](../edge-maintenance-dispatch-demo-001/protocol.md): single-model container rehearsal and its explicit limitations.
- [ENG-195: Define edge-model interoperability and on-device coordinator strategy](https://linear.app/ditto/issue/ENG-195/define-edge-model-interoperability-and-on-device-coordinator-strategy), child of [ENG-188](https://linear.app/ditto/issue/ENG-188/heterogeneous-edge-model-coordination-over-offline-ditto-peers).
