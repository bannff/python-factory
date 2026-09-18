# Companion-X Runtime Composition — Tasks

> `LangSuite` is an internal umbrella for concrete Lang ecosystem integrations. Do not create or depend on a `langsuite` package.

## E. Native MCP v2 evidence

- [ ] E.1 Record public MCP SDK v2 APIs for the scoped client and run clean in-process, HTTP, and stdio canaries for scope isolation, raw arguments, correlation/idempotency, and cleanup.
- [ ] E.2 For each selected concrete Lang package, record exact version, source, license/security posture, resolved lock graph, public API evidence, and compatibility with MCP v2.
- [ ] E.3 Generate preliminary concrete-package `artifact_adapter_closure` and `ServerSurfaceIdentity` inventory from locks, packaged code, and enabled/disabled configuration.
- [ ] E.4 Declare E passed only when E.1–E.3 pass. Until then do not mutate dependencies/locks, migrate server/client code, or add shims.

## 1. Neutral contracts and trusted selection

- [ ] 1.1 Add duplicate-key-rejecting runtime configuration and one trusted registered adapter selection with no fallback.
- [ ] 1.2 Add neutral `AgentRuntimePort`, descriptor, lifecycle events, capabilities, and typed feature rejection.
- [ ] 1.3 Add `ScopedCapabilityClientPort` contracts in `mcp_utils`; ensure every adapter receives it rather than creating a transport.
- [ ] 1.4 Add conformance fixtures for invoke/stream/structured output/cancellation/cleanup/scope isolation.

## 2. Native spine and control plane

- [ ] 2.1 Implement generated closure and closure-driven evidence admission for concrete packages.
- [ ] 2.2 Implement and bind `ServerSurfaceIdentity`; test exactly one identity per in-process, HTTP, and stdio process.
- [ ] 2.3 Implement the one public native MCP v2 scoped client and migrate Agent consuming paths to it.
- [ ] 2.4 Seal runtime, package, scope, closure, surface, Telemetry, and Evals policy facts into Workflow manifests; retain Workflow's exclusive durable ownership.

## 3. Concrete integrations

- [ ] 3.1 Add a LangChain single-agent adapter inside Agent, using only declared capabilities and Lang tools from the scoped client.
- [ ] 3.2 Add a provider-neutral explicit graph contract, then a bounded LangGraph adapter; reject undeclared graph/session features.
- [ ] 3.3 Add Evals-owned AgentEvals integration with frozen-policy reports and promotion boundaries.
- [ ] 3.4 Add Telemetry-owned normalized Langfuse export with redaction and correlation.
- [ ] 3.5 Remove Strands runtime/adapters, FastMCP, MCP-v1 imports, dependency pins, tests, metadata, and fallback configuration after Lang runtime and native-v2 parity passes.

## 4. Acceptance

- [ ] 4.1 Prove Agent → Workflow → scoped native MCP v2 → Evals in two unrelated domains.
- [ ] 4.2 Run focused Agent, MCP, Workflow, Evals, Telemetry, config, closure, surface, and Hypothesis state/scope tests.
- [ ] 4.3 Run `git diff --check` and `foreman_guardian_check`; do not commit, push, or close tracking work without explicit user direction.
