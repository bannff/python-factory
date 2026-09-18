# Implementation Plan: Native MCP Python SDK v2 Cutover

## E. Evidence gate

- [ ] E.1 Run public MCP SDK v2 canaries for in-process, HTTP, and stdio transport: scope isolation, raw arguments, correlation/idempotency, cancellation, and deterministic cleanup.
- [ ] E.2 For each selected concrete Lang/MCP package, record exact version, source, license/security posture, resolver/lock graph, and public API evidence. Do not create a `langsuite` dependency.
- [ ] E.3 Generate preliminary closure and `ServerSurfaceIdentity` inventory from resolved locks, packaged code, and enabled/disabled configuration.
- [ ] E.4 Begin dependency or runtime migration only after E.1–E.3 pass.

## 1. Foundations

- [ ] 1.1 Define concrete-package compatibility rows and generated closure-driven admission.
- [ ] 1.2 Define and bind `ServerSurfaceIdentity`; add exactly-one tests for all transports.
- [ ] 1.3 Define transport-neutral raw-argument, scope, context, task, result, and lifecycle contracts in `mcp_utils`.
- [ ] 1.4 Define a single `ScopedCapabilityClientPort` and trusted Agent runtime selection contracts.

## 2. Native MCP v2 spine

- [ ] 2.1 Implement public-v2 registration/composer using canonical typed-registration metadata: pass decoded raw mappings once to the existing strict Pydantic-v2 handler and project its `ToolResult` egress once; add schema/catalog comparison and transport error mapping without SDK coercion/default insertion or duplicate validation/serialization.
- [ ] 2.2 Implement the one scoped native v2 client for in-process, HTTP, and stdio, with deterministic cleanup.
- [ ] 2.3 Add negative tests rejecting FastMCP/MCP-v1, raw HTTP bypasses, private fields, direct imports, and local registries.
- [ ] 2.4 Migrate inventory-listed server and Agent consuming paths through the one registry/composer and scoped client.

## 3. Brick-owned Lang integrations

- [ ] 3.1 Add Agent-owned LangChain single-agent adapter and scoped descriptor-to-tool conversion.
- [ ] 3.2 Add provider-neutral explicit graph contracts, then bounded Agent-owned LangGraph adapter.
- [ ] 3.3 Add Evals-owned AgentEvals adapter, frozen-policy report binding, and promotion boundaries.
- [ ] 3.4 Add Telemetry-owned Langfuse exporter with redaction and correlation.
- [ ] 3.5 Remove Strands runtime/adapters, FastMCP, MCP-v1 imports, dependency pins, tests, metadata, and fallback configuration after Lang runtime and native-v2 parity passes.

## 4. Acceptance

- [ ] 4.1 Bind concrete package, scope, closure, surface, Evals, and Telemetry facts to manifests and release evidence.
- [ ] 4.2 Prove Agent → Workflow → scoped native MCP v2 → Evals in two unrelated domains.
- [ ] 4.3 Run focused feature, conformance, property, transport, clean-lock, rollback, `git diff --check`, and `foreman_guardian_check` validation.
