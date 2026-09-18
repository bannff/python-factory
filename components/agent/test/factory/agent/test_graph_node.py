"""Tests for GraphNode — wraps a GraphExecutor as a nested graph node.

Verifies:
- invoke_async merges context and invocation_state correctly
- Returns dict with status, output, execution_order, execution_time
- Handles None invocation_state gracefully
- Context values are overridden by invocation_state on key collision
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from factory.agent.nodes.graph_node import GraphNode
from factory.agent.runtime.ports import GraphResult


def _make_executor(result: GraphResult) -> MagicMock:
    executor = MagicMock()
    executor.run = AsyncMock(return_value=result)
    return executor


def _node(result: GraphResult, context: dict | None = None) -> GraphNode:
    return GraphNode(_make_executor(result), context=context or {})


def _ok(**kwargs) -> GraphResult:
    kwargs.setdefault("status", "completed")
    kwargs.setdefault("results", {"output": ""})
    return GraphResult(**kwargs)


def _run(node, task="task", state=None):
    return asyncio.run(node.invoke_async(task, invocation_state=state))


class TestGraphNodeReturnShape:
    def test_returns_required_keys(self):
        out = _run(_node(_ok(execution_order=["a"], execution_time=1.0)))
        assert set(out.keys()) == {"status", "output", "execution_order", "execution_time"}

    def test_status_propagated(self):
        assert _run(_node(_ok()))["status"] == "completed"

    def test_output_from_results(self):
        assert _run(_node(_ok(results={"output": "hello"})))["output"] == "hello"

    def test_output_empty_when_missing(self):
        assert _run(_node(_ok(results={})))["output"] == ""

    def test_execution_order_propagated(self):
        out = _run(_node(_ok(execution_order=["n1", "n2"])))
        assert out["execution_order"] == ["n1", "n2"]

    def test_execution_time_propagated(self):
        out = _run(_node(_ok(execution_time=3.14)))
        assert out["execution_time"] == pytest.approx(3.14)

    def test_error_status_propagated(self):
        result = GraphResult(status="error", results={"error": "boom"})
        assert _run(_node(result))["status"] == "error"


class TestGraphNodeContextMerge:
    def _executor_with_capture(self):
        executor = MagicMock()
        executor.run = AsyncMock(return_value=_ok())
        return executor

    def test_none_state_uses_context(self):
        ex = self._executor_with_capture()
        asyncio.run(GraphNode(ex, {"env": "prod"}).invoke_async("t", invocation_state=None))
        assert ex.run.call_args[0][1]["env"] == "prod"

    def test_state_merged_with_context(self):
        ex = self._executor_with_capture()
        asyncio.run(GraphNode(ex, {"base": "ctx"}).invoke_async("t", invocation_state={"extra": "v"}))
        merged = ex.run.call_args[0][1]
        assert merged["base"] == "ctx" and merged["extra"] == "v"

    def test_state_overrides_context_on_collision(self):
        ex = self._executor_with_capture()
        asyncio.run(GraphNode(ex, {"k": "ctx"}).invoke_async("t", invocation_state={"k": "state"}))
        assert ex.run.call_args[0][1]["k"] == "state"

    def test_empty_context_and_empty_state(self):
        ex = self._executor_with_capture()
        asyncio.run(GraphNode(ex, {}).invoke_async("t", invocation_state={}))
        assert ex.run.call_args[0][1] == {}

    def test_task_converted_to_string(self):
        ex = self._executor_with_capture()
        asyncio.run(GraphNode(ex, {}).invoke_async(42))
        assert ex.run.call_args[0][0] == "42"
