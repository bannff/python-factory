"""Graph Executor - executes graph configs via pluggable runtime.

Per-node telemetry via ``GraphLifecyclePlugin``; brick-boundary events
(``graph.launched``/``completed``/``failed``) emitted here.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from factory.agent.runtime.ports import GraphResult
from factory.agent.runtime.runtime import AgentRuntimeFactory

from ._envelope_scope import envelope_scope
from ._graph_helpers import apply_limits, build_condition
from .graph_nodes import GraphNodeBuilder

if TYPE_CHECKING:
    from factory.agent.registry.agents import AgentRegistry
    from factory.agent.registry.graphs import GraphRegistry
    from factory.agent.registry.swarms import SwarmRegistry


def _emit_event(event_type: str, payload: dict[str, Any]) -> None:
    """Emit brick-boundary event via tool_invoker. Fire-and-forget."""
    try:
        from factory.mcp_utils.interface import get_service
        invoker = get_service("tool_invoker")
        if invoker:
            invoker("events_publish", source="agent.graph_executor",
                    event_type=event_type, payload=payload)
    except Exception:
        pass


def _graph_error(
    graph_id: str, run_id: str, error: str, results_msg: str,
) -> GraphResult:
    """Emit graph.failed and return a run_id-tagged error GraphResult."""
    _emit_event("graph.failed", {
        "graph_id": graph_id, "run_id": run_id or "",
        "status": "failed", "error": error,
    })
    return GraphResult(
        status="error", results={"error": results_msg}, run_id=run_id or "",
    )


def _build_graph_hooks(
    graph_id: str, run_id: str | None, context: dict[str, Any],
) -> list[Any]:
    rid = run_id or str(context.get("run_id", "") or "")
    try:
        from factory.agent.plugins.multiagent_lifecycle import (
            GraphLifecyclePlugin,
        )
        return [GraphLifecyclePlugin(graph_id=graph_id, run_id=rid)]
    except Exception:
        return []


def _kind(config: Any) -> str:
    if isinstance(config, dict):
        return str(config.get("kind", "graph"))
    return getattr(config, "kind", "graph")


def _attr(config: Any, key: str, default: Any = None) -> Any:
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _node_dict(node: Any) -> dict[str, Any]:
    if isinstance(node, dict):
        return node
    return node.model_dump(by_alias=True, exclude_unset=True) if hasattr(node, "model_dump") else dict(node)


class GraphExecutor:
    def __init__(
        self, config: dict[str, Any] | Any,
        swarm_registry: "SwarmRegistry | None" = None,
        agent_registry: "AgentRegistry | None" = None,
        graph_registry: "GraphRegistry | None" = None,
        backend: str = "strands",
    ):
        # Accept dict (legacy / tests) or typed RegistryConfig (uffq).
        # No coercion — use _kind/_attr/_node_dict helpers to read.
        self.config = config
        self.swarm_registry = swarm_registry
        self.agent_registry = agent_registry
        self.graph_registry = graph_registry
        self.backend = backend
        self._graph_runtime = AgentRuntimeFactory.create_graph_runtime(backend)
        self.node_builder = GraphNodeBuilder(
            swarm_registry, agent_registry, graph_registry,
        )

    async def run(
        self, task: str, context: dict[str, Any], *,
        bypass_legacy_resume: bool = False,
    ) -> GraphResult:
        """Execute once; the private bypass exists only for legacy compatibility."""
        if _kind(self.config) == "workflow":
            from .workflow import WorkflowExecutor
            wf = WorkflowExecutor(
                self.config,
                swarm_registry=self.swarm_registry,
                agent_registry=self.agent_registry,
                graph_registry=self.graph_registry,
                backend=self.backend,
            )
            wf._mcp_tools = self.node_builder._mcp_tools  # bd-42dz
            return await wf.run(task, context)

        if bool(_attr(self.config, "resumable", False)) \
                and not bypass_legacy_resume:
            from .durable_graph import run_durable_graph
            return await run_durable_graph(self, task, context)

        graph_id = _attr(self.config, "id", "unknown")
        t0 = time.monotonic()
        with envelope_scope(context) as run_id:
            rid = run_id or context.get("run_id", "") or ""
            try:
                builder = self._graph_runtime.create_builder()
                node_ids = []
                for nc in (_attr(self.config, "nodes", []) or []):
                    nc_dict = _node_dict(nc)
                    node = await self.node_builder.build_node(nc_dict, context)
                    if node:
                        nid = nc_dict.get("id")
                        self._graph_runtime.add_node(builder, node, nid)
                        node_ids.append(nid)

                for edge in (_attr(self.config, "edges", []) or []):
                    cond = None
                    ec = _node_dict(edge)
                    if ec.get("condition"):
                        cond = self._build_condition(ec["condition"])
                    self._graph_runtime.add_edge(
                        builder, ec["source"], ec["target"], cond,
                    )

                entry_points = _attr(self.config, "entry_points", []) or []
                if not entry_points and node_ids:
                    entry_points = [node_ids[0]]
                for entry in entry_points:
                    self._graph_runtime.set_entry_point(builder, entry)

                apply_limits(builder, self.config)

                # Lifecycle plugin BEFORE build (Strands wires at build time).
                hooks = _build_graph_hooks(graph_id, run_id, context)
                if hooks:
                    self._graph_runtime.set_hook_providers(builder, hooks)
                graph = self._graph_runtime.build(builder)

                # Post-build trace_attributes for managed provenance
                # (Strands 1.50.2 has no builder trace setter)
                managed_attrs = context.get("_managed_trace_attributes")
                if managed_attrs and hasattr(graph, "trace_attributes"):
                    graph.trace_attributes = {
                        **graph.trace_attributes, **managed_attrs,
                    }

                _emit_event("graph.launched", {
                    "run_id": rid, "status": "running",
                    "graph_id": graph_id, "node_count": len(node_ids),
                    "nodes": node_ids,
                    "execution_mode": context.get("execution_mode", "ephemeral"),
                    "durable": bool(context.get("durable", False)),
                })
                result = await self._graph_runtime.invoke_async(
                    graph, task, context,
                )
                result.run_id = rid
                _emit_event("graph.completed", {
                    "graph_id": graph_id, "status": result.status,
                    "run_id": rid,
                    "execution_mode": context.get("execution_mode", "ephemeral"),
                    "durable": bool(context.get("durable", False)),
                    "execution_time": time.monotonic() - t0,
                    "execution_order": result.execution_order,
                })
                return result

            except ImportError as e:
                return _graph_error(
                    graph_id, rid, str(e), f"Runtime package required: {e}",
                )
            except Exception as e:
                return _graph_error(graph_id, rid, str(e), str(e))

    def _build_condition(self, condition_spec: str) -> Any:
        """Backwards-compat shim for tests — delegates to helper."""
        return build_condition(
            condition_spec, _attr(self.config, "conditions", {}) or {},
        )
