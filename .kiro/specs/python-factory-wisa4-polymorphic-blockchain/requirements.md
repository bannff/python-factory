# Polymorphic Blockchain Ledger Framework — Requirements

> Bead: `python-factory-wisa4`
> Scope: foundational refactor only. It preserves the economy profile and prepares the isolated DCAL follow-on (`python-factory-a9f16`, `python-factory-8qyzw`); it does **not** implement DCAL or mount DCAL MCP tools.

## Introduction

`components/blockchain` becomes a ledger-technology framework that composes explicit, isolated ledger profiles. This phase has one mounted public profile: the existing economy. The framework is polymorphic inside the server, while the public economy MCP contract remains exactly the present contract until a future profile independently introduces an explicit typed tool family.

## 1. Scope and compatibility boundary

1. The brick name, package namespace, `BRICK.yaml` identity, and `blockchain_*` economy namespace SHALL remain unchanged. This work SHALL NOT create a new brick, alter `BRICKS_INDEX.yaml`, or modify the DCAL specification.
2. The server SHALL mount exactly the existing 24 economy tools: 13 deterministic, 9 operational, and 2 authoring. Names, categories, flat keyword ingress, Pydantic v2 models/defaults/required fields, concrete `ToolResult[OutputDTO]` return annotations, and expected typed-negative behavior SHALL remain byte-compatible.
3. Resources, prompts, `blockchain_get_views`, and its `blockchain-economy` payload SHALL remain byte-compatible. Disabled and enabled authoring behavior, including typed `authoring_disabled`, remains unchanged.
4. Economy runtime behavior remains unchanged: default mock runtime; wallet-ID construction; treasury genesis; balances; transfers/mint; bounties; hash-chain/block behavior; reconciliation; normal-negative results; auto-wallet; public core/interface convenience semantics; and Events/Games integration behavior.
5. Before implementation, the team SHALL snapshot and compare the complete brick MCP discovery surface: exact tool names and categories; input and output JSON schemas, Pydantic defaults, required fields, concrete output DTO schemas, and serialized `ToolResult` success and normal-negative envelopes; plus resources, prompts, and `blockchain-economy` view payloads. This is a discovery/schema-level contract freeze, not merely a tool-count check. A changed public contract is prohibited unless accepted under a separate, versioned decision; the only permitted wisa4 metadata evolution is a shape-preserving correction required by §4.

6. If `BlockchainRuntime(adapter=...)` is retained for tests or direct construction, that argument is trusted bootstrap injection only. It SHALL never derive from an MCP argument, tool request, request context, or caller-controlled input. Production server construction accepts validated server configuration only.

## 2. Internal profile composition model

1. `BlockchainRuntime` SHALL resolve a fixed `BlockchainComposition` exactly once during runtime/server startup, before MCP registration. The composition MAY use an immutable, internal map of allowed `ProfileDefinition` values to `ProfileRuntimeFactory` values; it SHALL not expose a mutable runtime registry. Registrations and backend mappings are frozen before tools are registered, accessors return immutable views or copies, and the factory SHALL never run on a tool invocation or request path.
2. A profile declares public semantics; an adapter declares how that profile persists or reaches a backend. An economy profile may use mock or Neo4j adapters, but neither adapter is a distinct public profile.
3. The startup map SHALL select only trusted, explicitly allowed profile factories and backend factories. Duplicate profile IDs, duplicate backend IDs, unknown profile configuration, unknown backend configuration, or invalid profile/backend combinations SHALL raise a descriptive configuration error before serving tools. No path may silently fall back to `MockLedger`.
4. There SHALL be no MCP `profile`, `ledger_type`, `backend`, or equivalent selector argument; no `get_ledger(profile=...)`; no generic `blockchain_execute`; no profile-dependent union DTO; and no caller-controlled routing.
5. The economy profile is the default and only mounted profile in this phase. Future profile selection is exclusively by that profile's explicitly named MCP tool family and trusted server/policy configuration—not by a caller parameter.

## 3. Ports, models, and source compatibility

1. `runtime/ports.py::LedgerPort` remains the economy semantic port. It may move only through a source-compatible import alias/re-export; all existing economy callers retain their imports and behavior.
2. The framework SHALL add neutral composition/lifecycle ports only, such as immutable `ProfileDefinition`, `ProfileRegistration`, `ProfileRuntimeFactory`, and `ProfileRuntime` with capabilities and health. It SHALL NOT add a semantic common-ledger operation port.
3. Framework ports SHALL not require or mention wallets, blocks, transfers, bounties, Merkle proofs, transaction models, or floating-point amounts. Future profiles own non-inheriting ports, models, DTOs, and operations.
4. Shared framework utilities are limited to audited stateless primitives (for example, configuration parsing or immutable composition validation). They SHALL contain neither mutable profile dispatch/state nor economy/prospective-profile business semantics.
5. Direct imports are permitted only inside `factory.blockchain`. Cross-brick consumers and integrations remain typed MCP-only.

## 4. Runtime, server, and configuration evolution

1. The implementation SHALL introduce `EconomyRuntime` or `EconomyProfileRuntime`, then retain `BlockchainRuntime` as a compatibility facade whose zero-argument/default behavior is economy mock and whose `get_ledger()` remains available with no profile argument. If a constructor-level `adapter` injection remains for tests or direct construction, it is trusted bootstrap injection only; it never accepts MCP/request/context/caller-derived data. Production server construction accepts only validated server configuration.
2. `BLOCKCHAIN_ADAPTER` retains its economy-default meaning and accepted compatibility mapping (`mock` by default; `neo4j` when configured). Startup normalization may map aliases to canonical adapter IDs, but rejected values must loud-fail. The documented canonical IDs and accepted legacy aliases require tests.
3. Server registration remains static for current economy `deterministic`, `operational`, `authoring`, resources, prompts, and views. This phase SHALL add no DCAL module, registration, resource, prompt, or view.
4. `blockchain_get_capabilities`, `blockchain_health_check`, and `blockchain_describe_config_schema` retain their current Pydantic output shapes and ingress. Their values may report only the active economy adapter and the finite canonical economy adapter IDs/accepted compatibility aliases; they SHALL not enumerate unmounted/future profiles, profile factories, internal backend maps, or composition registrations. Snapshot changes to values must be explicitly reviewed as shape-preserving truthfulness corrections.
5. The framework’s own composition data is server-side only and never becomes a public generic execution surface.

## 5. Isolation and security readiness

1. The economy profile remains isolated from future profiles. Each future profile SHALL bring non-inheriting models, ports, adapters, configuration keys, tables/indexes/namespaces, opaque-ID prefixes, caches, locks, queues, DLQs, workers, events, resources, prompts, data-only views, and key namespaces.
2. No future profile may read, fall back to, emit through, or render economy state unless a separately specified typed integration authorizes it. This applies equally to storage, cache, workers, events, resources, prompts, and views.
3. Startup profile/backend configuration is trusted server configuration only. This boundary prevents confused-deputy routing and accidental cross-profile dispatch; it does not authenticate callers.
4. This refactor SHALL NOT claim to resolve the generic unauthenticated API issue. DCAL activation remains blocked until principal/auth enforcement remediation `python-factory-anb95` is complete. Economy authoring remains byte-compatible in phase 1; future-profile authoring requires server-side principal authorization.

## 6. Quality gates and acceptance

1. Split existing violations `mcp/views.py`, `mcp/dashboard_summary.py`, and `runtime/ledger/mock_ledger.py` before changing them. Every new implementation file is under 200 LOC.
2. All stateful economy behavior remains covered by `test_ledger_properties.py`, including its `RuleBasedStateMachine`. The baseline blocker `python-factory-lzw7n` SHALL be fixed first by excluding the reserved owner `treasury` from generated owner strategies; full-suite green status is invalid until then.
3. Add the precise regression suites listed in `tasks.md`: catalog/schema plus each concrete output DTO schema and representative serialized `ToolResult` success/normal-negative envelope, semantic/mutation, transcript, composition/configuration and direct immutability, adapter conformance, durable recovery/concurrency where applicable, core/interface, consumer compatibility, selector-absence, and explicit reserved-treasury behavior tests.
4. Implementation completion requires focused tests, `uv run pytest components/blockchain/test -v --tb=short`, the specified Games/Events tests, and `foreman_guardian_check` with no introduced failure.
