# Design: Native MCP Python SDK v2 Cutover

## Overview

The MCP v2 spine is independent of agent frameworks. It exposes one scoped client and one server surface; the Agent brick converts client descriptors into LangChain tools and privately composes LangGraph only for declared bounded graphs.

```text
concrete-package evidence + public MCP v2 canaries
       │
       ▼
artifact closure + ServerSurfaceIdentity
       │
       ▼
ScopedCapabilityClientPort (mcp_utils, native public v2 APIs)
       │
       ├── Agent: LangChain / LangGraph adapter
       ├── Evals: AgentEvals adapter
       └── Telemetry: Langfuse exporter
```

## 1. Evidence and closure

```python
class PackageCompatibilityRow(FrozenModel):
    package: PackageProvenance
    role: Literal["agent_runtime", "evaluation", "telemetry", "mcp"]
    mcp_version: str
    lock_ids: dict[str, str]
    public_api_evidence: EvidenceRef
    canaries: dict[str, CanaryEvidence]
    status: Literal["accepted", "rejected"]
```

`LangSuite` has no row. The closure generator derives concrete package and adapter members from locks, importable packaged modules, and enabled/disabled registered configuration. It never trusts a hand-written provider list.

## 2. Native client and surface

`mcp_utils` owns transport-neutral scope and DTO contracts plus the sole native v2 implementation. Native imports are isolated in its adapter module. The implementation initializes, discovers, invokes, reads, renders, cancels, and closes through public APIs for in-process, HTTP, and stdio. It returns neutral types only.

Each native registration carries the canonical brick input/output DTO metadata and the already category-decorated handler. The native SDK wrapper passes the decoded argument mapping to that handler unchanged exactly once; the existing Pydantic-v2 typed boundary remains the sole ingress authority and its `ToolResult` typed egress remains the sole output authority. The composer must not apply an SDK signature adapter, a second `model_validate`, coercion, default insertion, or a second serialization layer.

The canonical server composer produces progressive and flat views from the same registry and binds one `ServerSurfaceIdentity`. No adapter creates a connection, server, registry, or raw HTTP path.

## 3. Brick integrations

- Agent receives the scoped client and converts only allowed capability descriptors into private LangChain tool representations. LangGraph graphs use an explicit neutral graph request/result contract and bounded in-memory state.
- Evals maps immutable execution evidence to an optional AgentEvals integration, freezes policy before evaluation, and owns reports and promotion.
- Telemetry consumes normalized lifecycle events and owns optional Langfuse export, credentials, redaction, and correlation.
- Workflow seals scope, closure, surface, package versions, Evals policy, and Telemetry revision into each attempt; retries create fresh bounded adapter state.

## 4. Delivery order

1. Prove the official MCP v2 public API in three transport canaries without changing dependencies or runtime code.
2. Add neutral contracts, trusted configuration, generated closure, and server identity.
3. Build the native client/server spine and migrate Agent consumers to the scoped port.
4. Add LangChain single-agent support, then explicit bounded LangGraph support.
5. Add Evals-owned AgentEvals and Telemetry-owned Langfuse integrations.
6. Prove two unrelated domains, then make one controlled cutover that removes Strands, FastMCP, and MCP-v1 from the active artifact closure; no legacy runtime is retained.

## 5. Non-goals

No `langsuite` package, no framework fallback, no FastMCP/MCP-v1 shim, no second stack/surface, no raw HTTP bypass, and no adapter-owned durable lifecycle.
