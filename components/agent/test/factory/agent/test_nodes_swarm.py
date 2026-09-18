"""Tests for SwarmNode."""

import pytest

from factory.agent.nodes.swarm_node import SwarmNode
from factory.agent.runtime.ports import NodeExecution


class TestSwarmNode:
    """Tests for SwarmNode."""

    @pytest.mark.asyncio
    async def test_context_merging(self):
        """Test that contexts are properly merged."""

        # Create a mock executor
        class MockExecutor:
            def __init__(self):
                self.last_context = None

            async def run(self, task, context):
                self.last_context = context
                from factory.agent.executors.swarm import SwarmResult

                return SwarmResult(status="completed", output="test")

        mock_executor = MockExecutor()
        base_context = {"user_id": "123", "session": "abc"}

        node = SwarmNode(mock_executor, base_context)

        await node.invoke_async("test task", invocation_state={"request_id": "456"})

        # Check contexts were merged
        assert mock_executor.last_context["user_id"] == "123"
        assert mock_executor.last_context["session"] == "abc"
        assert mock_executor.last_context["request_id"] == "456"

    @pytest.mark.asyncio
    async def test_result_format(self):
        """Test that results are properly formatted."""

        class MockExecutor:
            async def run(self, task, context):
                from factory.agent.executors.swarm import SwarmResult

                return SwarmResult(
                    status="completed",
                    output="Test output",
                    node_history=[
                        NodeExecution(node_id="a"),
                        NodeExecution(node_id="b"),
                    ],
                    execution_time=1.5,
                )

        node = SwarmNode(MockExecutor(), {})
        result = await node.invoke_async("test")

        assert result["status"] == "completed"
        assert result["output"] == "Test output"
        assert result["node_history"] == ["a", "b"]
        assert result["execution_time"] == 1.5
