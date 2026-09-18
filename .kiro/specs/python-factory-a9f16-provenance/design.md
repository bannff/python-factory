# DCAL Ledger Profile — Design

> Status: **APPROVED WITH NOTES — gateway-authenticated `TrustedEnvelope` is mandatory; profile isolation is a security boundary**
>
> Beads: `python-factory-a9f16` (protocol), `python-factory-8qyzw` (taxonomy relocation)

## 1. Definition and profile boundary

DCAL is the `dcal/v1` deterministic provenance profile within the `blockchain` technology brick. It accepts authorized producer-signed operations, atomically commits immutable records, issues signed Merkle heads/checkpoints, captures witness/evidence/quarantine decisions, and deterministically rebuilds projections. It is not a new `provenance` component and does not generalize the existing economy ledger.

`LedgerPort`, economy models, runtime factories/adapters, configuration, persistence, `blockchain_*` economy tools, and all 24 existing tool contracts remain byte-compatible. DCAL instead uses a separate non-inheriting `DcalLedgerPort` (also named `ProvenanceLedgerPort` at the interface seam). It has no wallets, transfers, bounties, transactions, or floats.

```text
producer → authenticated context + blockchain_dcal_* operation
  → bind dcal profile/tenant/principal/ledger/policy → canonicalize/sign/authorize
  → atomic append-or-match → immutable record + Merkle frontier
  → bounded verification → evidence/witness/checkpoint
  → immutable accepted snapshot → deterministic projection generation
  → optional safe Events notice / Graph projection / DcalAnchorPort evidence
```

Workflow owns global lifecycle/retries/cancellation; Evals owns frozen acceptance; CRDT/mesh owns local state. Events and Graph are nonauthoritative MCP consumers.

## 2. Layout and isolation

```text
components/blockchain/src/factory/blockchain/
├── runtime/
│   ├── ports.py                         # unchanged economy LedgerPort
│   └── dcal/
│       ├── ports.py  runtime.py  canonical.py  append.py  merkle.py
│       ├── verify.py checkpoints.py evidence.py projections.py
│       ├── models/                      # DCAL-only Pydantic families
│       └── adapters/                    # memory/sqlite/HSM/witness/anchor
└── mcp/
    ├── contracts/dcal/                  # strict DCAL DTOs
    ├── dcal_deterministic.py
    ├── dcal_operational.py
    ├── dcal_authoring.py
    ├── dcal_resources.py
    └── dcal_prompts.py
```

DCAL and economy have distinct models, adapter/runtime factories, config keys, storage tables/namespaces/labels/indexes, opaque ID prefixes, caches, queues/workers/dead letters/locks, events, resources/prompts, and data-only views. Shared code may contain only audited stateless cryptography, canonicalization, or durability utilities; it contains no profile dispatch or mutable state. Server registration exposes additive DCAL modules without changing economy registration.

Before new DCAL work, split existing `mcp/views.py`, `mcp/dashboard_summary.py`, and `runtime/ledger/mock_ledger.py`; do not increase those violations. All new files remain below 200 LOC.

## 3. Ports and trusted binding

```python
class DcalLedgerPort(Protocol):
    def append_or_match(self, *, identity: DurableIdentity, request_digest: str,
                        record: DcalLogRecord) -> AppendDecision: ...
    def get_record(self, *, scope: DcalScope, record_id: str) -> DcalLogRecord | None: ...
    def page_snapshot(self, *, snapshot: SourceSnapshot, cursor: str | None) -> RecordPage: ...

class MerkleStorePort(Protocol): ...
class SignerPort(Protocol): ...
class VerifierPort(Protocol): ...
class WitnessPort(Protocol): ...
class AuthorizationPort(Protocol): ...
class ClockPort(Protocol): ...
class ProjectionPort(Protocol): ...
class DcalAnchorPort(Protocol):
    def anchor_finalized_checkpoint(self, *, checkpoint_digest: str) -> AnchorDecision: ...
```

The DCAL runtime resolves `{profile="dcal", tenant_id, principal_id, producer_id, ledger_id, policy_digest}` from a gateway-authenticated or policy-approved credential context. It authorizes this binding before producer signature verification, idempotency lookup, and sequence allocation. `DurableIdentity` and cache/store keys include profile, tenant, principal, producer, ledger, action, and idempotency key. Direct caller envelope claims cannot establish identity; profile is never a tool parameter.

Production signing/verifying loud-fails without an approved HSM/KMS-capable adapter. Key purposes are `dcal_producer`, `dcal_witness`, `dcal_checkpoint`, `dcal_verifier`, and future `dcal_anchor`; economy or mismatched purpose/profile/tenant/ledger keys fail closed.

## 4. Frozen `dcal/v1` protocol

Canonical JSON is UTF-8, NFC, lexical Unicode-code-point key sorted, duplicate-key rejected before validation, integer-only, binary/non-finite-free, explicit-null-preserving, and timestamp-normalized to six-fraction UTC `Z`. Limits are 1 MiB canonical bytes, depth 16, 256 collection items/keys, 64 KiB strings, and protected references for sensitive/binary evidence.

SHA-256 commitments are domain-separated. ECDSA P-256/SHA-256 signatures use low-S fixed 64-byte `r||s`, and every signed message binds:

```json
{"protocol":"dcal","version":"v1","profile":"dcal","purpose":"…",
 "tenant":"…","ledger_id":"…","policy_digest":"…","canonical_digest":"…"}
```

`ProducerOperation` includes claimed tenant/principal/producer/source/policy binding; its `ProducerSignature` is checked against the server-resolved binding and a registered `dcal_producer` key before allocation. `DcalLogRecord` separately preserves producer, receipt, and checkpoint signatures. `ClockPort` supplies receipt time; key-policy snapshots determine activation, rotation overlap, and revocation without rewriting valid historic acceptance.

## 5. Append, proofs, witness, and evidence

The append transaction atomically creates the idempotency winner, sequence, prior commitment, record/leaf commitment, Merkle state, and receipt. An equal replay returns the durable receipt; a divergent fingerprint returns stable conflict. Public metadata is redacted before commitment and exposes only opaque identifiers, bounded operation kind, policy/key references, and protected evidence references.

Merkle v1 is `leaf=SHA256(0x00||record)`, `node=SHA256(0x01||left||right)`, and `empty_root=SHA256(b"")`; RFC-6962 largest-power-of-two proofs derive direction from sizes/index and reject malformed/surplus/missing/misordered/non-32-byte siblings. Golden vectors cover empty, one, odd, balanced, and extension trees.

Checkpoints bind scope, profile/tenant, tree size/root, prior digest, policy digest/version, witness-set version, issuance time, and signer key. Frozen witness policy has canonical witness/key/operator/failure-domain entries, threshold, ≤32 fan-out, ten-minute freshness, and distinctness over all three independence dimensions. Valid conflicting roots for the same witness/key and `(ledger, tree_size, policy_digest)` append equivocation evidence and quarantine descendants. Missing quorum is `pending`, not final.

States are `received`, `structurally_valid`, `pending_verification`, `verified`, `rejected`, and `quarantined`. Quarantine and release are immutable linked evidence; a release requires authorization and re-verification. Rebuild replays an immutable ordered snapshot with source digest, declaration/version, and a 24-hour caller-bound continuation; pages are ≤500 records/8 MiB. It atomically swaps a convergent generation and never repairs corrupt evidence.

## 6. MCP surface, resources, and integrations

All DCAL tools return `ToolResult[DCAL DTO]` and are prefixed `blockchain_dcal_`:

| Class | Tools |
|---|---|
| deterministic | capabilities, health, config schema, record/receipt/head reads, inclusion/consistency proof reads and verification, record verification, checkpoint/evidence/quarantine reads, projection status |
| operational | append operation/evidence, submit attestation, issue checkpoint, verify external evidence, start/continue/reconcile rebuild |
| authoring | register source/key/policy/witness/projection, activate/retire policy or witness, set retention hold |

Concrete names are the catalog in requirements §2. Resources use versioned `blockchain://dcal/...` schemas and safe status/head/checkpoint documents; prompts are DCAL-specific append, verification, quarantine-resolution, rebuild, and redacted-export guides. Data-only DCAL views cannot discover or render economy state, and economy views cannot discover or render DCAL state.

`DcalAnchorPort` receives only a finalized checkpoint digest. Its success/failure is appended as evidence; it is not a source of truth and cannot change finality. Events and Graph receive only post-commit safe data through typed MCP calls.

## 7. Migration and acceptance

DCAL starts a new `dcal/v1` genesis/root. No economy or prior standalone record can mix, convert, re-hash, re-key, or silently alias into it. A versioned migration policy may document an explicit legacy-name alias and support verified export/import manifests, but source bytes and manifests must validate and replay/import into DCAL is rejected. Economy remains readable through unchanged tools.

Acceptance includes memory/SQLite semantic parity; strict economy-24 catalog regression; DCAL strict-contract tests; state-machine Hypothesis tests; restart/crash linearizability; and adversarial profile-confusion coverage for tools, storage, caches, workers, events, views, keys, trusted envelopes, and migration replay. Two neutral, unrelated MCP-only probes must use `Agent → Workflow → blockchain_dcal → Evals` without a domain branch.
