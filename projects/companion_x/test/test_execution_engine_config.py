"""Regression test for the M7.6 stuck-fire root cause (P1, owner smoke #2 13:29).

``factory.agent.runtime.managed_launch.launch_managed_graph`` hardcodes
``engine_id="langgraph"`` when calling ``workflow.enroll_execution``. But
Companion-X's real ``projects/companion_x/config/settings.yaml`` (the file
``WORKFLOW_CONFIG_DIR`` points at in every real launch) still registered the
pre-LangChain-migration engine id ``strands_graph``, pointing at
``execute_strands_graph_attempt`` / ``cancel_strands_graph_attempt`` — tools
that no longer exist (the Agent brick now ships
``execute_langgraph_attempt`` / ``cancel_langgraph_attempt``).

Every scheduled/background fire that reached ``enroll_execution`` therefore
hit ``ExecutionEngineRegistry.resolve("langgraph")`` -> ``ValueError: unknown
execution engine: langgraph`` -> the fire retried forever with no terminal
reason. This is a stale-config gap left over from the Strands retirement,
not a bug in the enrollment/registry mechanism itself (which is exercised
correctly by the workflow brick's own unit tests using an arbitrary fixture
engine id).

This test loads the REAL project config (not a test fixture) through the
exact same ``WorkflowRuntime.from_config_dir`` call ``server.py`` uses, so a
future accidental revert or a similarly-stale rename can never regress this
silently again.
"""
from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path(__file__).parents[1] / "config"


def test_real_settings_yaml_registers_the_langgraph_engine_managed_launch_calls():
    from factory.workflow.runtime.runtime import WorkflowRuntime

    runtime = WorkflowRuntime.from_config_dir(CONFIG_DIR)
    spec = runtime.execution_engines.resolve("langgraph")

    assert spec.invoke_target.brick_name == "agent"
    assert spec.invoke_target.tool_name == "execute_langgraph_attempt"
    assert spec.cancel_target is not None
    assert spec.cancel_target.brick_name == "agent"
    assert spec.cancel_target.tool_name == "cancel_langgraph_attempt"


def test_real_settings_yaml_no_longer_registers_the_dead_strands_engine_id():
    from factory.workflow.runtime.execution_engines import ExecutionEngineRegistry
    from factory.workflow.runtime.runtime import WorkflowRuntime

    runtime = WorkflowRuntime.from_config_dir(CONFIG_DIR)
    try:
        runtime.execution_engines.resolve("strands_graph")
    except ValueError:
        pass
    else:
        raise AssertionError(
            "strands_graph must not be registered — the Agent brick no "
            "longer exposes execute_strands_graph_attempt/"
            "cancel_strands_graph_attempt, so any caller of that engine id "
            "would fail exactly like the langgraph gap this test guards."
        )
    assert isinstance(runtime.execution_engines, ExecutionEngineRegistry)


def test_invoke_target_tools_exist_on_the_real_agent_mcp_surface():
    """Belt-and-suspenders: the configured tool names must be real, callable
    Agent MCP tools today, not just plausible-looking strings in YAML."""
    from factory.agent.mcp.managed_graph_tool import register

    class _FakeMCP:
        def tool(self):
            def decorator(fn):
                self.registered.append(fn.__name__)
                return fn
            return decorator

        def __init__(self) -> None:
            self.registered: list[str] = []

    fake = _FakeMCP()
    register(fake)
    assert "execute_langgraph_attempt" in fake.registered
    assert "cancel_langgraph_attempt" in fake.registered
