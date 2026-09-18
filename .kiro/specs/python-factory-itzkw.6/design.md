# SDK-native tool chaos

## Scope

Add the operational `evals_run_tool_chaos` surface separately from
`evals_run_simulation`. The path uses only `strands_evals` v1.0.2 public
primitives: `StateRegistry`, `ToolSimulator`, `ChaosCase`,
`ChaosExperiment`, `ChaosPlugin`, and the SDK-native effect classes.

## Safety and isolation

A developer-owned static catalog is the only source of tool definitions and
schemas. Callers provide a nonempty, duplicate-free subset of those names;
they cannot supply a callable or schema. Each baseline or fault variant gets
its own `StateRegistry` and `ToolSimulator`, configured with a fixed bounded
cache. Values persisted from simulator state are recursively JSON-safe and
bounded by depth, item count, key length, and string length.

The registered-persona MCP route cannot receive `ChaosPlugin`, so
`agent_id` is explicitly rejected. The target is a prompt-only Strands
`Agent` with the native plugin and only `ToolSimulator.get_tool()` wrappers.

## Evidence and persistence

Each base-case/fault combination is a pair with explicit `pair_key` and
`condition` (`baseline` or the validated fault condition); display names do
not define identity. A v2 artifact records bounded state snapshots and native
effect evidence for every variant, plus evaluator baseline-to-fault deltas.
Existing v1 `build_run_artifacts` output and reader behavior remain unchanged.

A completed invocation builds one canonical `evals_record_run` request with
`source="tool_chaos"`; the same request is returned for durable retry and is
the only persistence call made for that run.

## Verification

Fake-backed tests cover catalog allowlisting, native effect translation and
limits, recursive evidence bounds, fresh state per variant, explicit pair
identity and evaluator deltas, one canonical retryable record request, and
MCP registration. The SDK canary remains import/signature-only.
