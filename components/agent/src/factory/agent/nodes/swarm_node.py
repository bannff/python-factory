"""
SwarmNode - Wraps a SwarmExecutor as a graph node.

Enables the "graph of swarms" pattern where graph nodes can be entire swarms.
"""

from typing import TYPE_CHECKING, Any

from factory.agent.nodes.base import CustomNode

if TYPE_CHECKING:
    from factory.agent.executors.swarm import SwarmExecutor


class SwarmNode(CustomNode):
    """
    Wraps a SwarmExecutor as a graph node.

    This enables the "graph of swarms" pattern where each node
    in a graph can be an entire swarm with its own shared context.

    Example graph config:
        nodes:
          - id: research
            type: swarm
            swarm_id: research_swarm
          - id: analysis
            type: swarm
            swarm_id: analysis_swarm
        edges:
          - source: research
            target: analysis
    """

    def __init__(self, executor: "SwarmExecutor", context: dict[str, Any]):
        """
        Initialize SwarmNode.

        Args:
            executor: The SwarmExecutor to wrap
            context: Base context to merge with invocation_state
        """
        self.executor = executor
        self.context = context

    async def invoke_async(
        self, task: Any, invocation_state: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        """
        Execute the wrapped swarm.

        Args:
            task: The input task
            invocation_state: Additional context from the graph
            **kwargs: Additional arguments

        Returns:
            Swarm execution result
        """
        # Merge contexts
        merged_context = {
            **self.context,
            **(invocation_state or {}),
        }

        # Run the swarm
        result = await self.executor.run(str(task), merged_context)

        # Return result in format expected by graph
        return {
            "status": result.status,
            "output": result.output,
            "node_history": result.node_ids,
            "execution_time": result.execution_time,
        }
