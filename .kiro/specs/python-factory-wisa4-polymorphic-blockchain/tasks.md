# Polymorphic Blockchain Ledger Framework — Tasks

> Bead: `python-factory-wisa4`
> Implement in order. This refactor does not implement or register DCAL.

## 0. Baseline and contract freeze

- [ ] 0.1 Claim `python-factory-wisa4`; retrieve and record the current economy composition and the dependency boundary with DCAL (`a9f16`/`8qyzw`) without editing either spec.
- [ ] 0.2 Add `test_economy_contract_snapshot.py` to capture and compare the complete fresh-server MCP discovery surface for the brick: exact 24-tool names and categories; input/output JSON schemas; strict/default/required-field behavior; concrete output DTO `model_json_schema()` and output-model annotations; representative serialized `ToolResult` success and every documented normal-negative envelope; resources; prompts; and the `blockchain-economy` view payload. This is a discovery/schema-level freeze, not a tool-count-only assertion.
- [ ] 0.3 Add `test_economy_behavior_transcripts.py` with normalized deterministic transcripts for mock economy genesis, wallet IDs, create/duplicate/missing wallet, transfer/mint errors and successes, bounties, block/hash verification, reconciliation, auto-wallet, and enabled/disabled authoring.
- [ ] 0.4 Repair `python-factory-lzw7n` in `test_ledger_properties.py`: exclude owner value `treasury` from generated owner IDs, then add a deterministic `owner="treasury"` regression that proves creation is rejected (or preserves the established reserved-owner contract), treasury genesis/balance is unchanged, and no duplicate treasury wallet/block/transaction is emitted. Run `uv run pytest components/blockchain/test/factory/blockchain/test_ledger_properties.py -v --tb=short`; do not call the full baseline green before it passes.
- [ ] 0.5 Run and preserve the baseline from `test_typed_mcp_boundary.py`, economy unit tests, core/interface tests, and current Games/Events blockchain consumer tests. Record intentional pre-existing failures separately; do not mask them.

## 1. Preparatory decomposition

- [ ] 1.1 Split `components/blockchain/src/factory/blockchain/mcp/views.py` before adding behavior, preserving `blockchain_get_views` output byte-for-byte.
- [ ] 1.2 Split `mcp/dashboard_summary.py` before adding behavior, preserving dashboard/activity/entity-graph output and tool bindings.
- [ ] 1.3 Split `runtime/ledger/mock_ledger.py` before adding behavior, preserving ledger model, transaction ordering, event/graph integration calls, and chain output.
- [ ] 1.4 Add regression tests around each split and confirm every new/changed implementation file remains below 200 LOC.

## 2. Preserve the economy profile

- [ ] 2.1 Introduce `runtime/economy/` and move/alias `LedgerPort` only source-compatibly. Add `test_economy_import_compatibility.py` for every supported legacy import and `BlockchainRuntime.get_ledger()` use.
- [ ] 2.2 Extract `EconomyRuntime`/`EconomyProfileRuntime`; preserve zero-argument economy mock semantics, `BLOCKCHAIN_ADAPTER=mock|neo4j` mapping, existing mock/Neo4j integrations, and no-argument `get_ledger()`.
- [ ] 2.3 Keep all existing economy MCP registration files and contract DTO imports static. Assert no signature, Pydantic default, category, or concrete `ToolResult[OutputDTO]` annotation changes in `test_typed_mcp_boundary.py` and `test_economy_contract_snapshot.py`.
- [ ] 2.4 Preserve public `interface.py`, core exports, auto-wallet behavior, and direct-in-brick imports. Add `test_economy_core_interface_regression.py`.

## 3. Add internal composition only

- [ ] 3.1 Add immutable neutral composition models/ports/factory under `runtime/composition/`: profile definition/registration, runtime factory, runtime health/capabilities, and validated composition. Do not define common wallet/block/transfer/bounty/proof/amount/transaction operations.
- [ ] 3.2 Add `test_profile_composition_config.py` for default economy/mock composition; explicit Neo4j composition; unsupported backend; unknown profile; duplicate profile; duplicate backend; invalid profile/backend pair; and fail-before-server behavior. Assert the factory builds/validates exactly once at runtime/server startup before MCP registration, freezes registrations/backend mappings, returns immutable views or copies, rejects direct mutation, and is never invoked from a tool/request path.
- [ ] 3.3 Refactor `BlockchainRuntime` into the composition facade. It exposes only compatibility `get_ledger()` with no profile parameter and delegates economy health/capabilities. If `adapter=...` remains for tests/direct construction, test that it is trusted bootstrap injection only and cannot be sourced from MCP ingress, a tool request, request context, or caller input; production server construction accepts only validated server configuration.
- [ ] 3.4 Make unknown `BLOCKCHAIN_ADAPTER` values loud configuration errors; add compatibility-alias tests for every accepted legacy spelling. Verify no fallback can construct `MockLedger` after an invalid selection.
- [ ] 3.5 Add `test_no_profile_selector_contract.py`, asserting no economy tool schema/property/signature mentions `profile`, `ledger_type`, `backend`, or selector synonyms; no `get_ledger(profile=...)`; no `blockchain_execute`; no profile union DTO; no mutable registry API; and no MCP/request-context route to constructor-level adapter injection.

## 4. Metadata, adapters, and consumers

- [ ] 4.1 Preserve capability/health/config-schema DTO shapes. Update only values needed to truthfully report the active economy adapter and finite supported economy canonical adapter IDs/compatibility aliases; reject projection of unmounted/future profiles, profile factories, internal backend maps, or composition registrations. Review snapshot diffs explicitly in `test_economy_metadata_truthfulness.py`.
- [ ] 4.2 Add `test_economy_adapter_conformance.py` that executes the normalized transcript against mock and Neo4j. Document every supported deviation in an allowlist with rationale; fail on an unlisted difference.
- [ ] 4.3 Where an adapter is durable, add `test_economy_durable_recovery.py` and `test_economy_concurrency.py` for crash/restart recovery, idempotent state visibility, and no duplicate/partial ledger mutations. Skip only where the adapter cannot claim durability.
- [ ] 4.4 Add/update `test_economy_consumer_compatibility.py` plus the existing Games and Events focused tests to prove typed MCP consumers still handle `ToolResult` success/normal-negative data exactly as before. Do not introduce cross-brick imports.
- [ ] 4.5 Add `test_profile_isolation_readiness.py` that validates composition has only economy mounted and rejects cross-profile state/config/namespace fallback. It must confirm no DCAL tools, resources, prompts, or views are registered.

## 5. Completion validation

- [ ] 5.1 Run `uv run pytest components/blockchain/test/factory/blockchain/test_typed_mcp_boundary.py -v --tb=short`.
- [ ] 5.2 Run `uv run pytest components/blockchain/test/factory/blockchain/test_ledger_properties.py -v --tb=short` and the new `test_economy_*.py` / `test_profile_*.py` suites.
- [ ] 5.3 Run `uv run pytest components/blockchain/test -v --tb=short` only after the `python-factory-lzw7n` repair; resolve failures introduced by this work.
- [ ] 5.4 Run the focused Games and Events consumer compatibility tests identified in the baseline, then `foreman_guardian_check`. Fix all introduced failures and confirm no new index/LOC/import violation.
- [ ] 5.5 Update only implementation-adjacent documentation/metadata justified by landed code; do not add DCAL functionality or change the DCAL specifications. Record that activation remains blocked by `python-factory-anb95`.
