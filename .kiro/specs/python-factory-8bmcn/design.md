# python-factory-8bmcn — faithful simulation evidence

## Contract

`evals_run_simulation` gives every execution a stable run id before it invokes a target. A simulation task creates one correlation id per case. It captures target spans immediately after target invocation and clears the shared exporter before ActorSimulator runs. The evaluator trajectory is mapped from only the immutable target-span tuple. Actor output and its spans are durable, per-turn evidence but are never supplied to trajectory/session evaluators.

The pinned `strands-agents-evals==1.0.2` `Experiment.run_evaluations()` returns an already-flattened `EvaluationReport`. The adapter retains its native `to_dict()` output and evaluator-tagged rows. If an older/fake caller supplies multiple native reports, it calls `EvaluationReport.flatten()` and records every raw report. The explicit aggregate strategy is persisted in the summary.

For `persist=True`, the MCP surface allocates or reuses a run id before simulation. Results and failures return it. The response includes a canonical `evals_record_run` request. `persist_only=True` retries exactly that request through the existing idempotent UPSERT and does not invoke the runtime.

## Verification

Fake-only regression tests cover target-versus-actor span isolation, SDK report normalization and aggregation, persona/thread forwarding, and failed write followed by same-run-id canonical retry. No Bedrock or live models are called.
