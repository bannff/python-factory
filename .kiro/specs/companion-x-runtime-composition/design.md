# Companion-X Runtime Composition — Design

> Decision: LangSuite is internal shorthand for LangChain, LangGraph, and related free Lang ecosystem integrations. It is not a package name. Concrete integrations remain inside their owning brick.

## 1. Composition

```text
trusted runtime config → AgentRuntimePort → LangChain / LangGraph adapter
                                           │
                                           ▼
                         ScopedCapabilityClientPort (mcp_utils, native MCP v2)
                                           │
                                           ▼
                                  scoped polymorphic brick tools

Evals: AgentEvals integration and acceptance
Telemetry: normalized events and Langfuse export
Workflow: durable attempt lifecycle
```

The Agent adapter receives an already scoped client and converts its typed descriptors to Lang tools. LangGraph is used only for declared bounded graph capabilities; it does not own durable checkpoints, retries, or recovery. Native MCP-v2 registration preserves the established brick Pydantic-v2 boundary: raw decoded arguments reach the category-decorated handler once, and its typed `ToolResult` egress is projected once without SDK coercion, default insertion, duplicate validation, or duplicate serialization.

## 2. Concrete dependency evidence

```python
class PackageProvenance(FrozenModel):
    distribution: str
    version: str
    source_repository: str
    license: str
    lock_graph_digest: str
    public_api_evidence: EvidenceRef

class RuntimeCompatibilityRow(FrozenModel):
    runtime_adapter_id: str
    packages: tuple[PackageProvenance, ...]
    mcp_version: str
    root_lock_id: str
    project_lock_id: str
    canaries: dict[str, CanaryEvidence]
    status: Literal["accepted", "rejected"]
```

No `LangSuiteProvenance` type exists. A LangChain, LangGraph, AgentEvals, or Langfuse dependency is admitted only when selected by its brick and supported by concrete resolver, public-API, and transport evidence.

## 3. Neutral runtime and capability ports

```python
class AgentRuntimePort(Protocol):
    @property
    def descriptor(self) -> RuntimeAdapterDescriptor: ...
    async def invoke(self, request: AgentInvocation) -> AgentResult: ...
    async def stream(self, request: AgentInvocation) -> AsyncIterator[LifecycleEvent]: ...
    async def cancel(self, invocation_id: str) -> None: ...
    async def close(self) -> None: ...

class ScopedCapabilityClientPort(Protocol):
    async def list_capabilities(self) -> tuple[CapabilityDescriptor, ...]: ...
    async def invoke(self, request: CapabilityInvocation) -> CapabilityResult: ...
    async def read_resource(self, request: ResourceRequest) -> ResourceResult: ...
    async def render_prompt(self, request: PromptRequest) -> PromptResult: ...
    async def close(self) -> None: ...
```

`mcp_utils` owns the implementation of `ScopedCapabilityClientPort` and imports MCP SDK v2 only in its native adapter modules. Agent, Evals, Telemetry, and Workflow consume neutral interfaces. The Lang adapter constructs LangChain tools from `CapabilityDescriptor`; it never opens a transport.

## 4. Ownership

- Agent's LangChain/LangGraph adapter maps normalized requests/events to private SDK types and cleans up bounded attempt-local state.
- Evals owns the AgentEvals adapter and freezes evaluation policy before execution. Its reports bind runtime, scope, closure, server-surface, and policy facts.
- Telemetry accepts normalized events and owns Langfuse export/redaction/credentials. It is observational only.
- Workflow seals runtime binding and scope into the durable attempt record, and alone manages retries, cancellation, recovery, budgets, and terminal states.

## 5. Delivery order

1. Establish public MCP SDK v2 in-process, HTTP, and stdio canary evidence for the framework-neutral scoped client.
2. Add neutral Agent and `mcp_utils` contracts, trusted adapter configuration, closure generation, and `ServerSurfaceIdentity`.
3. Implement the one native MCP v2 server/client spine and migrate Agent consumers to receive the scoped client.
4. Add a concrete LangChain single-agent adapter. Add LangGraph only after an explicit provider-neutral bounded graph contract is admitted.
5. Add Evals-owned AgentEvals and Telemetry-owned Langfuse adapters, then bind all evidence into Workflow/Evals records.
6. Remove Strands, FastMCP, and MCP-v1 from the target artifact closure; prove two unrelated domains before release.

## 6. Non-goals

No package named `langsuite`; no LangChain/LangGraph project-engine or fallback selection; no FastMCP/MCP-v1 shim; no second MCP client or server surface; no raw HTTP bypass; and no adapter-owned durable lifecycle.
