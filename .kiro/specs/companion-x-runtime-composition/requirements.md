# Companion-X Runtime Composition — Requirements

> Status: approved architecture. “LangSuite” is internal shorthand for the free Lang ecosystem, not a package or provider identifier.

## Introduction

Companion-X uses one trusted Agent runtime selected from registered concrete adapters. The Lang ecosystem implementation uses LangChain for agents and tools and LangGraph for declared bounded graphs. The scoped native MCP SDK v2 capability client is framework-neutral and provides the same polymorphic brick tools to every runtime. Workflow owns durable execution; Evals owns acceptance; Telemetry owns observability.

## 1. Concrete-package evidence and admission

1. “LangSuite” SHALL NOT appear as a distribution, lock entry, provider ID, provenance record, or closure member. Each selected concrete package records exact distribution, version, upstream repository, license/security posture, resolved lock graph, and public API evidence.
2. Before a concrete package is added or upgraded, evidence SHALL prove it resolves with the selected MCP SDK v2 stack and has no FastMCP or MCP-v1 dependency in the selected artifact closure.
3. A resolver result alone is insufficient. Evidence includes public-API inspection and clean in-process, HTTP, and stdio canaries for the scoped native MCP v2 path.
4. No package named `langsuite` is added. `langchain-mcp-adapters` is optional and may be selected only when its released version passes the same evidence; it is never required for the architecture.

## 2. Runtime selection and neutral boundary

1. Trusted startup configuration selects exactly one registered `runtime_adapter_id` from an allowlist. Selection is never raw MCP, graph, persona, API, or user input; unavailable, disabled, duplicate, unknown, or incompatible adapters fail safely without fallback.
2. Agent exposes a neutral `AgentRuntimePort` for bounded invocation, streaming, cancellation, structured output, declared capabilities, and deterministic cleanup. SDK objects remain private to adapters.
3. The Lang adapter owns LangChain agent construction, Lang-compatible tool conversion, and LangGraph execution for explicitly declared bounded graph capabilities. LangGraph is not a separate project engine or a durable process ledger.
4. Strands is removed from the target artifact closure. No Strands fallback, compatibility adapter, dependency, or runtime selection remains after the cutover.

## 3. One scoped native MCP v2 path

1. `mcp_utils` owns one `ScopedCapabilityClientPort` backed only by public MCP Python SDK v2 APIs. It resolves and enforces policy before discovery, invocation, resource/prompt access, correlation, idempotency, result mapping, cancellation, and cleanup.
2. Every runtime adapter receives this same port. Adapters cannot open another MCP session, use raw HTTP, access private server internals, import brick runtimes, widen scope, or maintain an adapter-local capability registry.
3. The client exposes typed, allowlisted capability descriptors and results. The Lang adapter may convert those descriptors to Lang tools but cannot bypass the client.
4. Scope policy ID and canonical digest bind the execution manifest, client inventory, Telemetry, Evals evidence, and replay identity. Scope changes conflict before invocation.

## 4. Brick ownership

1. **Agent** owns LangChain/LangGraph adapters, attempt-local execution, Lang tool conversion, and normalized runtime events/results.
2. **Evals** owns AgentEvals or other Lang evaluation adapters, frozen evaluator policy, immutable evidence-bound reports, typed deficiencies, acceptance, and promotion. Agent cannot set or mutate acceptance criteria after execution.
3. **Telemetry** owns normalized instrumentation and optional Langfuse export, credentials, redaction, and trace correlation. It cannot alter output, Workflow state, retry policy, or Evals decisions.
4. **Workflow** exclusively owns attempt IDs, budgets, retries, cancellation, recovery, stopping rules, terminal reasons, and durable history. LangGraph state and checkpointers are attempt-local unless Workflow explicitly governs them.

## 5. Closure, server identity, and acceptance

1. `artifact_adapter_closure` is generated from resolved locks, packaged importable code, and enabled or disabled configured/registered entries. Every concrete closure member requires an evidence row; manual inclusion assertions are insufficient.
2. Each artifact has one `ServerSurfaceIdentity`: canonical entry point, MCP route/transport bindings, and process/lifecycle identity. Manifest, inventories, and evidence bind the same identity; in-process, HTTP, and stdio tests enforce exactly one surface.
3. Completion requires the native-v2 evidence gate, generated closure admission, focused scope/lifecycle/manifest/replay/Telemetry/Evals tests, Hypothesis stateful tests, `git diff --check`, and `foreman_guardian_check`.
4. The identical Agent → Workflow → scoped native MCP v2 client → Evals path SHALL be proven in two unrelated domains with only project and domain-pack data differing.
