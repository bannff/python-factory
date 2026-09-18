# Native MCP Python SDK v2 Cutover — Requirements

## Introduction

The cutover delivers one official public MCP Python SDK v2 stack, one server surface per runtime process, and one framework-neutral scoped capability path. “LangSuite” is internal shorthand, not a distribution or dependency: Agent owns LangChain/LangGraph, Evals owns Lang evaluation integrations, and Telemetry owns Langfuse.

## 1. Evidence and concrete dependencies

1. Before a selected concrete Lang or MCP package is added or changed, evidence records its exact distribution/version, source, license/security posture, resolved lock graph, public APIs, and in-process/HTTP/stdio canaries.
2. The selected stack must use MCP major 2 and have no FastMCP or MCP-v1 dependency in the artifact closure. A resolver result alone is insufficient.
3. No `langsuite` package, provenance field, or closure member exists. `langchain-mcp-adapters` is optional; it cannot be used unless its released version passes the same evidence.

## 2. One surface and one scoped client

1. Each artifact defines `ServerSurfaceIdentity`: canonical entry point, MCP route/transport bindings, and process/lifecycle identity. Manifest, server/client inventories, and evidence must agree.
2. Each process exposes exactly one native MCP v2 surface. Exactly-one tests cover in-process, HTTP, and stdio activation.
3. `mcp_utils` owns the sole `ScopedCapabilityClientPort`, which uses public v2 APIs for discovery, invoke, resources, prompts, correlation, idempotency, cancellation, and cleanup.
4. FastMCP, MCP-v1, raw HTTP, private SDK fields, direct brick imports, alternate clients, and adapter-local registries are prohibited.

## 3. Ownership

1. Agent owns private LangChain/LangGraph adapters and conversion of scoped descriptors into Lang tools. LangGraph state is bounded to an attempt.
2. Evals owns AgentEvals or other Lang evaluation adapters, frozen policies, immutable evidence-bound reports, deficiencies, acceptance, and promotion.
3. Telemetry owns normalized instrumentation and Langfuse export/redaction/credentials. It has no control-plane authority.
4. Workflow remains the sole durable owner of attempts, retries, cancellation, recovery, budgets, history, and terminal reasons.

## 4. Closure and acceptance

1. `artifact_adapter_closure` is generated from resolved locks, packaged importable code, and enabled/disabled configured/registered entries. Every concrete closure member requires a passing compatibility row.
2. Release evidence binds command, environment, revision, exact locks, package rows, scope, closure, surface identity, and canary results. It fails closed on missing or failed evidence.
3. Validation includes public-v2 API checks, three transports, inventory integration, property tests for raw arguments/scope/lifecycle/closure, replay contracts, clean-lock scans, `git diff --check`, and `foreman_guardian_check`.
