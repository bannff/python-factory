"""GraphNode — wraps a nested GraphExecutor as a graph node.

Enables the "graph of graphs" pattern where a node in a graph
can itself be an entire sub-graph.

Example graph config:
    nodes:
      - id: security_review
        type: graph
        graph_id: security-review
      - id: report
        type: agent
        agent_id: report_writer
    edges:
      - source: security_review
        target: report
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from factory.agent.nodes.base import CustomNode

if TYPE_CHECKING:
    from factory.agent.executors.graph import GraphExecutor


class GraphNode(CustomNode):
    """Wraps a GraphExecutor as a node in a parent graph."""

    def __init__(self, executor: "GraphExecutor", context: dict[str, Any]):
        self.executor = executor
        self.context = context

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any,
    ) -> dict[str, Any]:
        merged = {**self.context, **(invocation_state or {})}
        result = await self.executor.run(str(task), merged)
        return {
            "status": result.status,
            "output": result.results.get("output", ""),
            "execution_order": result.execution_order,
            "execution_time": result.execution_time,
        }
