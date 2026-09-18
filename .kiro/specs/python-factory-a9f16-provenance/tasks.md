# DCAL Ledger Profile — Implementation Tasks

> Beads: `python-factory-a9f16` (frozen protocol) and `python-factory-8qyzw` (taxonomy revision).
>
> Complete in order. Run existing focused tests before adding coverage. Record mandatory specialist verdicts through Companion-X memory using `user_id="kiro-agent"`.

## 0. Taxonomy lock and blockchain preparation

- [ ] 0.1 Treat DCAL solely as `dcal/v1` inside `components/blockchain`; do not create `components/provenance` or alter `BRICKS_INDEX.yaml`. Preserve all frozen canonicalization, cryptography, authentication, witness, bounds, redaction, and reconstruction rules from the requirements/design.
- [ ] 0.2 Snapshot and regression-pin the existing economy `LedgerPort`, models, runtime behavior, and exact 24-tool catalog: `get_capabilities`, `health_check`, `describe_config_schema`, `get_chain_info`, `get_balance`, `get_wallet`, `list_transactions`, `get_block`, `verify_chain`, `my_wallet`, `create_wallet`, `transfer`, `mint`, `post_bounty`, `claim_bounty`, `cancel_bounty`, `list_bounties`, `reconcile`, `authoring_get_status`, `authoring_seed_economy`, `get_dashboard_summary`, `get_activity`, `get_entity_graph_context`, and `get_views`—all under their existing `blockchain_*` names and schemas.
- [ ] 0.3 Split `mcp/views.py`, `mcp/dashboard_summary.py`, and `runtime/ledger/mock_ledger.py` before adding concerns; do not increase any of those three existing size violations. No new file exceeds 200 LOC.
- [ ] 0.4 Plan (do not make in this documentation-only change) the `BRICK.yaml` description/features update for sibling economy + DCAL profiles. Do not hand-edit index metadata.

**Requirements:** 1, 6

## 1. Independent DCAL architecture and strict surface

- [ ] 1.1 Add `runtime/dcal/{ports.py,runtime.py,canonical.py,append.py,merkle.py,verify.py,checkpoints.py,evidence.py,projections.py,models/,adapters/}` and `mcp/contracts/dcal/` plus `mcp/dcal_{deterministic,operational,authoring,resources,prompts}.py`. Retain `runtime/ports.py::LedgerPort` unchanged; define independent non-inheriting `DcalLedgerPort` / `ProvenanceLedgerPort`.
- [ ] 1.2 Establish hard isolation for DCAL/economy models, runtime factories/adapters, config, storage tables/namespaces/labels/indexes, opaque ID prefixes, cache keys, queues/workers/dead letters/locks, events, resources/prompts, and data-only views. Allow only audited stateless crypto/canonicalization/durability helpers; prohibit profile dispatch in shared helpers.
- [ ] 1.3 Define strict frozen bounded Pydantic v2 DTO families for producer operation/signature, trusted binding, record/receipt, policy/key/source/witness refs, proofs, evidence, checkpoint, and projection outputs. Every DCAL tool has flat kwargs and exact `ToolResult[OutputDTO]` egress.
- [ ] 1.4 Register only additive `blockchain_dcal_*` tools: the deterministic, operational, and authoring catalog specified in requirements §2. Add `blockchain://dcal/...` resources and DCAL prompts. Existing economy resources/prompts/views stay byte-compatible.

**Requirements:** 1, 2

## 2. Trusted profile binding and append spine

- [ ] 2.1 Require a gateway-issued, verified `TrustedEnvelope` or policy-approved credential context as the fail-closed identity/authorization seam; a caller-supplied MCP envelope never establishes DCAL identity. Resolve profile implicitly from the DCAL tool family and trusted config/policy; reject caller profile input. Bind and authorize `{profile="dcal", tenant_id, principal_id, ledger_id, policy_digest}` and trusted producer/source before signature verification, idempotency lookup, or sequence allocation.
- [ ] 2.2 Implement `dcal/v1` canonical JSON/parser and domain-separated digest helpers with normative vectors: NFC, lexical keys, duplicate rejection, timestamp formatting, integer-only semantics, explicit null/omission, and size/depth/collection/string limits.
- [ ] 2.3 Implement `ProducerSignature` verification over a bound `ProducerOperation`; use only `dcal_producer` P-256/SHA-256 low-S keys. Persist producer, receipt, and checkpoint signatures separately. Add production signer/verifier startup loud failure unless an approved HSM/KMS adapter is configured.
- [ ] 2.4 Implement atomic append-or-match. Durable identity/storage/cache keys include profile, tenant, principal, producer, ledger, action, and idempotency. Atomically persist winner, sequence, prior record, record/leaf commitment, tree state, and receipt; prove equal replay/mismatch conflict semantics.
- [ ] 2.5 Implement memory and SQLite DCAL adapters with identical semantics, restart recovery, and corruption fail-closed behavior. They must not share economy tables or state.

**Requirements:** 3, 4, 6

## 3. Proofs, checkpoint lifecycle, and evidence

- [ ] 3.1 Implement frozen RFC-6962 Merkle construction/proofs: leaf/node/empty root definitions; indexed/sized proof wire format; vectors for empty, one, odd, balanced, and extension trees; rejection of malformed/resource-exhausting proofs.
- [ ] 3.2 Implement key-purpose, algorithm, profile, tenant, ledger, validity, rotation, and revocation decisions. Wrong/economy keys and future-anchor misuse fail before accepting a signature; `ClockPort` binds receipt-time policy evaluation.
- [ ] 3.3 Implement immutable signed checkpoints and frozen witness policies with ≤32 entries, ten-minute freshness, k-of-n threshold, and distinct witness/operator/failure-domain counting. Below threshold is `pending`; duplicate/stale/revoked witnesses fail safely.
- [ ] 3.4 Append equivocation, verification, risk, quarantine, and release evidence linked to exact target commitments. Implement explicit states and policy-declared projection eligibility. Release is separately authorized and re-verified; no mutation/delete path exists.
- [ ] 3.5 Add authoring-gated source/key/policy/witness/projection/retention registration. Policy changes never reinterpret historic records. Add safe non-enumerating tenant/visibility reads and redacted logs/resources/errors.

**Requirements:** 4, 5

## 4. Rebuild, integration, anchoring, and migration

- [ ] 4.1 Implement immutable source snapshots, source digest, cursors, 24-hour caller-bound continuations, bounded rebuild pages, and atomic projection generation swaps. Same source must converge; corrupt source evidence fails/quarantines and is never repaired.
- [ ] 4.2 Keep global scheduling/retries/cancellation in Workflow through typed MCP. Publish only safe post-commit Events notices and optional rebuildable Graph projection through typed MCP; assert no DCAL-to-other-brick internal imports.
- [ ] 4.3 Define `DcalAnchorPort`, but do not implement or invoke it without an external-trust requirement and blockchain-specific design verdict. It accepts only a finalized checkpoint digest; success/failure appends evidence and cannot alter checkpoint/finality/history. Economy cannot anchor DCAL.
- [ ] 4.4 Implement versioned migration/alias/export-import verification policy for legacy standalone-name references. DCAL starts fresh `dcal/v1` genesis/root; prohibit historical mixing, conversion, re-hash/re-key, silent fallback/rename, and migration replay. Economy remains readable through unchanged tools.

**Requirements:** 1, 5, 6

## 5. Verification and completion

- [ ] 5.1 Add focused tests under `components/blockchain/test/factory/blockchain/test_dcal_*.py`: models/contracts, canonical records, append/idempotency, hashes/Merkle, witness/risk, projection rebuild, MCP contract, memory/SQLite persistence, and migration policy.
- [ ] 5.2 Add `test_dcal_*_properties.py` with `@given` and a `RuleBasedStateMachine` (≤200 LOC each; `max_examples=50`) covering append/exact and conflicting replay, bad signatures, checkpoints/witnesses/equivocation, quarantine/release, rebuild, and restart against a shadow model.
- [ ] 5.3 Add adversarial tests for direct-envelope spoofing/confused deputy; canonical/parser differentials; signature substitution across profile/tenant/principal/policy/subject/ledger; economy-key substitution; forged storage; proof malleability; key-time boundaries; witness Sybil/shared-control; auth/quarantine bypass; protected-reference leakage; crash/restart; and exhausted proof/witness/rebuild bounds.
- [ ] 5.4 Add explicit profile-isolation probes: no DCAL tool can reach economy state and no economy tool can reach DCAL state; no shared storage/cache/worker/dead-letter/lock/event/view/resource/prompt leakage; no fallback profile resolution; no migration replay.
- [ ] 5.5 Add strict 24-tool economy catalog/schema regression and DCAL catalog regression. Prove two unrelated neutral domains over identical typed `Agent → Workflow → blockchain_dcal → Evals` calls: non-security artifact-quality lineage and neutral document/artifact lineage. Both append evidence, obtain witness checkpoint, and bind Evals criteria/report without a domain branch.
- [ ] 5.6 Run `uv run pytest components/blockchain/test -v --tb=short`, focused DCAL properties/probes, and `foreman_guardian_check`; fix all introduced failures. Only then implement the planned BRICK.yaml feature/description update and regenerate metadata through Foreman if required.

## Completion criteria

- [ ] DCAL is an isolated deterministic profile of the blockchain brick; no provenance brick or index entry exists.
- [ ] Economy `LedgerPort`, models, tools, contracts, and 24-tool catalog are unchanged and byte-compatible.
- [ ] DCAL exposes strict same-brick DTOs, exact typed egress, `blockchain_dcal_*` tools, and a fresh `dcal/v1` genesis.
- [ ] Memory/SQLite DCAL adapters satisfy equivalent append/proof/rebuild semantics without sharing economy state.
- [ ] Signatures, proofs, witness thresholds, quarantine, redaction, rebuild, migration rejection, and profile isolation are automated and adversarially tested.
- [ ] Two neutral MCP acceptance probes and validation evidence are complete; required specialist verdicts are stored before closing `python-factory-a9f16` and `python-factory-8qyzw`.
