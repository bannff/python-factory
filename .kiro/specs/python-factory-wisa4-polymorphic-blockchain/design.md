# Polymorphic Blockchain Ledger Framework — Design

> Bead: `python-factory-wisa4`
> Status: proposed implementation plan; economy-only public surface.

## 1. Decision

The blockchain brick gains an internal composition layer, not a caller-selectable generic ledger. The server starts one trusted composition containing the economy profile. Existing economy MCP modules continue to obtain the economy runtime through the compatibility facade, so every public `blockchain_*` call retains its current flat, strict typed contract.

```text
trusted startup config
  → validated immutable BlockchainComposition
  → economy ProfileDefinition + EconomyProfileRuntimeFactory
  → EconomyProfileRuntime(adapter: mock | neo4j)
  → BlockchainRuntime compatibility facade.get_ledger()
  → unchanged economy MCP modules / resources / prompts / economy view
```

A later DCAL profile will use its own runtime, non-inheriting port/models/adapters, and explicit `blockchain_dcal_*` family under its existing separate spec. It is deliberately absent here.

## 2. Layout and ownership

```text
components/blockchain/src/factory/blockchain/
├── runtime/
│   ├── ports.py                    # preserved LedgerPort economy import path
│   ├── economy/
│   │   ├── ports.py                # optional source-compatible LedgerPort home
│   │   ├── runtime.py              # EconomyProfileRuntime / adapter selection
│   │   └── ledger/                 # existing economy adapters, split as needed
│   ├── composition/
│   │   ├── models.py               # frozen ProfileDefinition/Registration
│   │   ├── ports.py                # neutral ProfileRuntime/Factory protocols
│   │   ├── registry.py             # immutable validation and lookup
│   │   └── factory.py              # trusted startup composition
│   └── runtime.py                  # BlockchainRuntime compatibility facade
├── mcp/                            # unchanged economy registrations/contracts
│   ├── deterministic.py
│   ├── operational.py
│   ├── authoring.py
│   ├── resources.py
│   ├── prompts.py
│   └── views/                      # split legacy oversized view module
└── server.py                       # static economy registration only
```

Names are illustrative; final splitting must preserve imports and retain each new file below 200 LOC. `LedgerPort` stays economy-only. The composition protocol is intentionally narrow:

```python
@dataclass(frozen=True)
class ProfileDefinition:
    profile_id: str
    runtime_factory_id: str
    mounted: bool

class ProfileRuntime(Protocol):
    def capabilities(self) -> Mapping[str, JSONValue]: ...
    def health_check(self) -> Mapping[str, JSONValue]: ...

class ProfileRuntimeFactory(Protocol):
    def create(self, *, backend_id: str) -> ProfileRuntime: ...
```

The actual economy runtime may additionally expose `ledger: LedgerPort`; that is not lifted into `ProfileRuntime`. No shared protocol defines semantic ledger verbs.

## 3. Startup composition and configuration

`BlockchainCompositionFactory` consumes trusted process configuration only. During runtime/server startup, before MCP registration, it constructs the fixed tuple/map of registrations, validates it once, freezes registrations and backend mappings, and returns an immutable `BlockchainComposition`; accessors return immutable views or copies. It never executes on a tool invocation or request path. Validation rejects empty IDs, duplicate IDs, a profile that names an unavailable factory, a backend unavailable for that profile, and any profile other than economy marked mounted in this phase.

`BLOCKCHAIN_ADAPTER` remains the source-compatible economy adapter selector: absence resolves to `mock`; `neo4j` resolves to Neo4j. Alias normalization is explicit and finite (for example `mock_ledger → mock` only if that compatibility alias already exists); unknown values throw `BlockchainConfigurationError` with the setting/value/allowed IDs. The old final `return MockLedger()` fallback is removed.

`BlockchainRuntime` owns the startup-built validated composition, exposes `get_ledger()` with no parameter, and delegates economy health/capabilities/configuration facts. Existing callers do not learn profile names. If `BlockchainRuntime(adapter=...)` remains for tests or direct construction, it is trusted bootstrap injection only—not data derived from an MCP argument, tool request, request context, or caller input. Production server construction accepts only validated server configuration. The server creates this facade once and registers the existing economy modules exactly as before.

## 4. Public contracts and truthful metadata

The public surface is pinned before moving code:

| Surface | Refactor rule |
|---|---|
| 24 FastMCP tools | Exact names, categories, flat kwargs, strict Pydantic v2 inputs, defaults/required fields, and `ToolResult[concrete DTO]` annotations |
| Economy domain data | Exact wallet IDs/genesis, arithmetic, transactions/bounties, blocks/hash chain, normal-negative envelopes, authoring gate |
| MCP primitives | Existing resources, prompts, and `blockchain-economy` view payload are unchanged |
| Public Python | `BlockchainRuntime`, `get_ledger()`, `LedgerPort` import paths, `interface.py` conveniences remain usable |

The contract snapshot compares the complete brick MCP discovery surface, not merely tool count: exact tool names/categories; input and output schemas, Pydantic defaults and required fields; concrete output DTO schemas; serialized `ToolResult` success and normal-negative envelopes; resources; prompts; and the `blockchain-economy` view payload.

Capabilities/health/config-schema DTO *shapes* remain unchanged. Their values may report only the active economy adapter and finite supported economy canonical adapter IDs/compatibility aliases. They must not enumerate unmounted or future profiles, profile factories, internal backend maps, or composition registrations. The implementation records the approved baseline-versus-truthful metadata snapshot diff; it must not add fields, selectors, union DTOs, or change tool signatures.

## 5. Isolation model

The composition layer knows identities and factories, not profile data. Every profile owns its own persistence and execution identity: config prefix, storage table/index/label namespace, opaque ID prefix, cache/lock/queue/DLQ/worker namespace, event namespace, MCP resources/prompts/views, and cryptographic key namespace. It is invalid for a profile to inspect another profile's adapter or state as a fallback.

Events and Games remain economy consumers through typed MCP calls and existing public contracts. No direct `factory.blockchain` internal import is introduced outside this brick. Future profiles can have separate typed consumers only after their own compatibility/security design.

## 6. Failure handling and security posture

Composition failures happen during runtime/server construction before tools are served. They are configuration failures, not typed operational domain negatives. Economy operation failures retain their present typed payload behavior.

The profile boundary reduces cross-profile routing risk, but does not provide principal authentication. The current economy authoring gate stays unchanged. A future authoring profile must bind server-side principal authorization, and DCAL remains blocked by `python-factory-anb95`.

## 7. Rollout sequence

1. Capture catalog, schemas, resources/prompts/views, core/interface APIs, and normalized mock/Neo4j behavioral transcripts.
2. Repair the `python-factory-lzw7n` reserved-`treasury` Hypothesis baseline flake; run the full economy suite.
3. Split the three oversized files without behavior change and prove snapshots/transcripts still match.
4. Extract economy runtime and source-compatible `LedgerPort` location/aliases.
5. Introduce immutable composition models/factory and migrate `BlockchainRuntime` to the compatibility facade.
6. Make backend selection strict; correct only metadata values needed for truthful active composition reporting.
7. Verify adapter conformance, durable recovery when applicable, consumer compatibility, profile isolation, schema selector absence, and full guardian validation.
