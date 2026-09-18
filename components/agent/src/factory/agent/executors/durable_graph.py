"""Application-ledger execution for resumable registered graphs."""
from __future__ import annotations

from typing import Any

from factory.agent.runtime.ports import GraphResult


def _node_dict(node: Any) -> dict[str, Any]:
    return node.model_dump(by_alias=True, exclude_unset=True) if hasattr(node, "model_dump") else dict(node)


def _cached_result(payload: dict[str, Any], run_id: str) -> GraphResult:
    fields = GraphResult.__dataclass_fields__
    values = {key: value for key, value in payload.items() if key in fields}
    values.update(run_id=run_id, cached=True)
    return GraphResult(**values)


async def run_durable_graph(executor: Any, task: str,
                            context: dict[str, Any]) -> GraphResult:
    """Run/resume with node checkpoints and terminal duplicate suppression."""
    from factory.agent.plugins.multiagent_lifecycle import GraphLifecyclePlugin
    from factory.agent.runtime.adapters.json_graph_run_ledger import JsonGraphRunLedger
    from factory.agent.runtime.graph_conditions import resolve_condition
    from factory.agent.runtime.graph_run_hooks import (
        GraphRunCheckpointHook, rehydrate_graph_outputs,
    )
    from factory.agent.runtime.graph_run_ledger import GraphRunConflict
    from factory.agent.runtime.registered_graph_support import (
        configure_builder, digest_json, structured_outputs, validate_run_id,
    )

    config = executor.config
    graph_id = config.id
    run_id_value = context.get("run_id")
    if not run_id_value:
        return GraphResult(
            status="error",
            results={"error": "resumable graph execution requires an explicit run_id"},
        )
    run_id = validate_run_id(str(run_id_value))
    config_digest = digest_json(config.model_dump(mode="json", by_alias=True))
    ledger = JsonGraphRunLedger()
    session_id = f"{graph_id}--{run_id}"
    try:
        claim = ledger.claim(
            graph_id, run_id, session_id, digest_json(task), config_digest,
        )
    except GraphRunConflict as exc:
        return GraphResult(status="error", results={"error": str(exc)}, run_id=run_id)
    if claim.cached:
        return _cached_result(claim.record.result or {}, run_id)

    try:
        builder = executor._graph_runtime.create_builder()
        for node in config.nodes:
            node_dict = _node_dict(node)
            built = await executor.node_builder.build_node(node_dict, context)
            if built is None:
                raise ValueError(f"Failed to build graph node {node.id!r}")
            executor._graph_runtime.add_node(builder, built, node.id)
        incoming = {
            target: tuple(edge.source for edge in config.edges if edge.target == target)
            for target in {edge.target for edge in config.edges}
        }
        schemas = {node.id: getattr(node, "output_schema", None) for node in config.nodes}
        for edge in config.edges:
            condition = None
            if edge.condition:
                condition = resolve_condition(
                    edge.condition, predecessors=incoming[edge.target], schemas=schemas,
                )
            executor._graph_runtime.add_edge(
                builder, edge.source, edge.target, condition,
            )
        configure_builder(builder, config, run_id)
        hooks = [
            GraphLifecyclePlugin(graph_id=graph_id, run_id=run_id),
            GraphRunCheckpointHook(ledger, claim, schemas),
        ]
        executor._graph_runtime.set_hook_providers(builder, hooks)
        graph = executor._graph_runtime.build(builder)
        rehydrate_graph_outputs(graph, claim)
        invocation = {
            **context, "run_id": run_id, "graph_id": graph_id,
            "graph_run_claim": claim,
        }
        result = await executor._graph_runtime.invoke_async(graph, task, invocation)
        if result.status != "completed":
            detail = result.results.get("error", f"status={result.status}")
            raise RuntimeError(f"graph failed: {detail}")
        if config.terminal_node and config.terminal_node not in claim.record.nodes:
            raise ValueError(
                f"Terminal node {config.terminal_node!r} did not produce valid output"
            )
        result.run_id = run_id
        result.session_id = session_id
        result.structured_outputs = structured_outputs(claim)
        result.results["structured_outputs"] = result.structured_outputs
        envelope = result.to_dict()
        ledger.complete(claim, envelope)
        return result
    except Exception as exc:
        ledger.fail(claim, str(exc))
        return GraphResult(
            status="error", results={"error": str(exc)}, run_id=run_id,
            session_id=session_id, structured_outputs=structured_outputs(claim),
        )


__all__ = ["run_durable_graph"]
