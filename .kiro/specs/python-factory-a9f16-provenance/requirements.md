# DCAL Ledger Profile — Requirements

> Beads: `python-factory-a9f16` (frozen provenance protocol); `python-factory-8qyzw` (taxonomy relocation)

## Introduction

DCAL is the `dcal/v1` deterministic provenance-ledger profile inside the existing `blockchain` technology brick. It records attributed operations as immutable signed records, creates witness-cosigned checkpoints, proves inclusion and append-only continuity, and rebuilds declared derived projections. It is not a new brick or a general blockchain replacement. Economy remains a separate sibling profile with its existing wallet, transfer, bounty, transaction, models, `LedgerPort`, and byte-compatible 24-tool MCP catalog.

## 1. Boundary, sibling profiles, and isolation

1. `components/blockchain` SHALL host DCAL; implementation SHALL NOT scaffold `provenance` or modify `BRICKS_INDEX.yaml`.
2. Economy `LedgerPort` is unchanged and MUST NOT be widened, inherited, repurposed, or used by DCAL. DCAL SHALL define independent, non-inheriting `DcalLedgerPort` / `ProvenanceLedgerPort` under `runtime/dcal/` and SHALL never use wallets, transfers, bounties, transactions, or float economic amounts.
3. DCAL owns deterministic signed evidence, append-or-match, Merkle/checkpoint proofs, witness attestations, risk/quarantine evidence, and deterministic projection reconstruction. Workflow owns retries, budgets, cancellation, recovery, and terminal reasons; Evals owns frozen criteria/acceptance; CRDT/mesh owns domain state and only consumes verified projections.
4. Isolation is mandatory for models; adapters/runtime factories/configuration; storage tables, namespaces, labels, and indexes; opaque-ID prefixes; caches; queues/workers/dead letters/locks; events; resources/prompts; and data-only views. There is no cross-profile read, fallback, worker, event, or view path.
5. Events may publish safe post-commit IDs/digests/statuses and Graph may consume a rebuildable projection, both only through typed MCP boundaries. Neither is authoritative.
6. A future `DcalAnchorPort` may one-way anchor only a finalized DCAL checkpoint digest. Economy cannot anchor DCAL; anchor failure appends evidence only and cannot alter a checkpoint, finality, or history.

## 2. Strict additive MCP contract

1. All DCAL public tools are additive `blockchain_dcal_*` tools using same-brick frozen, strict Pydantic v2 DTOs (`ConfigDict(extra="forbid", strict=True, frozen=True)`), bounded fields, flat keyword ingress, and exact `ToolResult[OutputDTO]` egress. No ingress profile parameter, raw containers, nested request wrappers, or ingress `schema_version` exists.
2. Deterministic tools: `blockchain_dcal_get_capabilities`, `_health_check`, `_describe_config_schema`, `_get_record`, `_get_receipt`, `_get_tree_head`, `_get_inclusion_proof`, `_get_consistency_proof`, `_verify_inclusion_proof`, `_verify_consistency_proof`, `_verify_record`, `_get_checkpoint`, `_list_checkpoints`, `_get_evidence`, `_list_quarantine`, and `_get_projection_status`.
3. Operational tools: `blockchain_dcal_append_operation`, `_append_evidence`, `_submit_witness_attestation`, `_issue_checkpoint`, `_verify_external_evidence`, `_start_projection_rebuild`, `_continue_projection_rebuild`, and `_reconcile_projection`.
4. Authoring tools: `blockchain_dcal_authoring_register_source`, `blockchain_dcal_authoring_register_key_binding`, `blockchain_dcal_authoring_publish_policy`, `blockchain_dcal_authoring_activate_policy`, `blockchain_dcal_authoring_register_witness`, `blockchain_dcal_authoring_retire_witness`, `blockchain_dcal_authoring_register_projection`, and `blockchain_dcal_authoring_set_retention_hold`; each requires register-time authoring enablement and server-side principal authorization.
5. Expected outcomes (`not_found`, `matched`, `conflict`, `pending`, `quarantined`, `proof_invalid`) are successful typed data; unexpected infrastructure failures are failed safe envelopes. Versioned DCAL resources expose record/envelope/proof/evidence/policy schemas and safe checkpoint/status documents; prompts cover append, proof verification, quarantine resolution, rebuild, and redacted export.

## 3. Profile binding, records, signatures, and authorization

1. Profile selection is implicit in the `blockchain_dcal_*` family plus trusted server configuration/policy, never caller input. Before signature verification, idempotency lookup, or sequence allocation, the server SHALL authenticate, bind, and authorize `{profile="dcal", tenant_id, principal_id, ledger_id, policy_digest}` plus trusted producer/source ownership.
2. Durable identity and every storage/cache key SHALL include profile, tenant, principal, producer, ledger, action, and idempotency key. Caller identity that conflicts with gateway-authenticated context is rejected; unauthenticated direct MCP clients receive only explicitly public documentation/schema resources.
3. Canonical `dcal/v1` records bind protocol/canonicalization version, profile, tenant/principal/producer/source refs, ledger, operation ID/kind, policy ID/digest, subjects, protected evidence refs, idempotency identity, prior commitment, and key/algorithm context. Corrections, revocations, risk decisions, quarantines, and releases append linked evidence; they never mutate history.
4. The atomic append transaction establishes one durable idempotency winner, contiguous sequence, prior hash, leaf/record commitment, and receipt. Equal identity/key/fingerprint returns the original receipt; a changed fingerprint returns stable conflict without append.
5. `ProducerSignature{key_id, algorithm="ecdsa-p256-sha256", signature_b64url}` signs canonical `ProducerOperation`, including claimed tenant/principal/producer/source/policy binding. The server resolves and compares that binding and verifies a registered DCAL producer key before idempotency/sequence work; persisted producer, receipt, and checkpoint signatures remain distinct.

## 4. Frozen `dcal/v1` profile

1. Canonical bytes are UTF-8 canonical JSON: NFC strings, lexical Unicode-code-point keys, duplicate-key rejection before Pydantic, RFC 3339 UTC timestamps with exactly six fractional digits and `Z`, integers only, explicit null distinct from omission, and no binary/non-finite values. Sensitive/binary content is a protected reference.
2. SHA-256 commitments use domain-separated record, idempotency, evidence, leaf, node, and checkpoint tags. Every signed message binds `{protocol="dcal", version="v1", profile="dcal", purpose, tenant, ledger_id, policy_digest, canonical_digest}`. ECDSA P-256/SHA-256 uses fixed 64-byte low-S `r||s`; purpose/algorithm/profile/tenant/ledger substitution fails.
3. Key purposes are `dcal_producer`, `dcal_witness`, `dcal_checkpoint`, `dcal_verifier`, and future `dcal_anchor`; economy or wrong-purpose/profile/tenant/ledger keys are rejected. Production signer/verifier construction loud-fails without an approved HSM/KMS-capable adapter. Receipt-time `ClockPort` policy snapshots govern validity, rotation overlap, and revocation; revocation blocks new acceptance but does not rewrite historic receipts.
4. Inline limits: canonical bytes ≤1 MiB, depth ≤16, collection ≤256, string ≤64 KiB, proof ≤64 nodes. Witness fan-out ≤32 with a 30-second deadline. Rebuild pages ≤500 records/8 MiB and signed continuations bind snapshot digest/cursor/caller scope with 24-hour expiry. Exhaustion is reject, pending, or quarantined—never accepted.
5. Pre-commit redaction/classification permits only protocol/version, opaque random IDs, bounded operation kind, policy/key references, and protected evidence references. Tenant/visibility authorization applies to every DCAL read. Public outputs never expose raw evidence, sensitive/low-entropy digests, subject values, secrets, credentials, or backend details.

## 5. Merkle, witness, evidence, and projections

1. `leaf=SHA256(0x00||canonical_record_bytes)`, `node=SHA256(0x01||left||right)`, `empty_root=SHA256(b"")`; contiguous zero-based leaves and RFC-6962 largest-power-of-two inclusion/consistency proofs are mandatory. Proofs bind scope/algorithm/sizes and reject malformed, surplus, missing, misordered, or non-32-byte nodes.
2. A signed checkpoint binds ledger, tree size/root, prior checkpoint digest, policy digest/version, issuance time, witness-set version, signer key ID, tenant, and profile. Witnesses sign the exact checkpoint digest.
3. Frozen witness policy contains canonical `{witness_id,key_id,operator_id,failure_domain}`, k-of-n threshold, ≤32 fan-out, ten-minute receipt-time freshness, and uniqueness across witness/operator/failure-domain. Below threshold is `pending`, never final. Mutually exclusive valid witness statements create immutable equivocation evidence and quarantine policy-declared descendants.
4. States are `received`, `structurally_valid`, `pending_verification`, `verified`, `rejected`, or `quarantined`. Quarantine preserves original evidence/checks/proofs. Release is separately authorized signed evidence referencing a re-verification result; it never mutates the quarantine record.
5. Projections derive only from immutable ordered source snapshots, snapshot digest, declaration/version, and resumable checkpoint; same source converges identically and swaps generation atomically. Corrupt source signatures/links/proofs fail or quarantine, never heal.

## 6. Compatibility and acceptance

1. DCAL begins fresh `dcal/v1` genesis/root. There is no historical economy/provenance mixing, conversion, re-hash, re-key, implicit alias, or fallback. Economy data remains readable through its unchanged tools.
2. If historical standalone-name references exist, a versioned migration policy SHALL offer explicit aliases only in documentation, and explicit export/import verification that preserves source bytes, verifies source/destination manifests, and rejects replay into DCAL. It SHALL not silently rename or import history.
3. Tests live at `components/blockchain/test/factory/blockchain/test_dcal_*.py`; they include strict regression for the existing 24-tool economy catalog and adversarial profile isolation (tool/storage/cache/worker/event/view leakage, key substitution, envelope spoofing, migration replay) alongside all frozen canonicalization/signature/proof/witness/quarantine/rebuild/crash tests.
4. Two unrelated neutral domains SHALL prove the identical typed MCP path `Agent → Workflow → blockchain_dcal → Evals`, with no domain branch. No new implementation file exceeds 200 LOC. Before DCAL concerns are added, split the three existing blockchain violations: `mcp/views.py`, `mcp/dashboard_summary.py`, and `runtime/ledger/mock_ledger.py`.
