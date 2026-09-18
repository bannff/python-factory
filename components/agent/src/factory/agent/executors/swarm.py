"""Swarm Executor - executes swarm configs via pluggable runtime.

Per-node telemetry (``swarm.node_start``/``handoff``/``node_stop``)
is emitted by ``SwarmLifecyclePlugin`` attached as a Strands hook.
Brick-boundary events (``swarm.launched``/``completed``/``failed``)
stay here — they have non-Strands callers (Kiro hooks, RL loop,
memory adapter).
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from factory.agent.runtime.ports import AgentConfig, SwarmResult
from factory.agent.runtime.runtime import AgentRuntimeFactory
from factory.agent.runtime.trace_context import trace_attributes_from_context

from ._envelope_scope import envelope_scope
from ._template import inject_variables

if TYPE_CHECKING:
    from factory.agent.registry.agents import AgentRegistry

logger = logging.getLogger(__name__)


def _emit_event(event_type: str, payload: dict[str, Any]) -> None:
    """Emit brick-boundary event via tool_invoker. Fire-and-forget."""
    try:
        from factory.mcp_utils.interface import get_service
        invoker = get_service("tool_invoker")
        if invoker:
            invoker("events_publish", source="agent.swarm_executor",
                    event_type=event_type, payload=payload)
    except Exception:
        pass


def _swarm_error(
    swarm_id: str, run_id: str, output: str, event_type: str = "swarm.failed",
) -> SwarmResult:
    """Emit a swarm.failed event and return a run_id-tagged error result."""
    _emit_event(event_type, {"swarm_id": swarm_id, "error": output})
    return SwarmResult(status="error", output=output, run_id=run_id or "")


def _build_swarm_hooks(
    swarm_id: str, run_id: str | None, context: dict[str, Any],
) -> list[Any]:
    """SwarmLifecyclePlugin hook list. Empty if SDK absent."""
    rid = run_id or str(context.get("run_id", "") or "")
    try:
        from factory.agent.plugins.multiagent_lifecycle import SwarmLifecyclePlugin
        return [SwarmLifecyclePlugin(swarm_id=swarm_id, run_id=rid)]
    except Exception:
        return []


def _attr(config: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a Pydantic model or a raw dict."""
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _ag_attr(ag: Any, key: str, default: Any = None) -> Any:
    """Read a field from a swarm-agent (model or dict)."""
    if isinstance(ag, dict):
        return ag.get(key, default)
    return getattr(ag, key, default)


class SwarmExecutor:
    """Executes a swarm config using the configured runtime adapter."""

    def __init__(
        self,
        config: dict[str, Any] | Any,
        agent_registry: "AgentRegistry | None" = None,
        backend: str = "strands",
    ):
        # Accept dict (legacy / tests) or typed SwarmConfig (uffq) —
        # use _attr/_ag_attr helpers to read uniformly.
        self.config = config
        self.agent_registry = agent_registry
        self.backend = backend
        self._agent_runtime = AgentRuntimeFactory.create_agent_runtime(backend)
        self._swarm_runtime = AgentRuntimeFactory.create_swarm_runtime(backend)
        self._mcp_tools: list[Any] | None = None  # set externally or lazy-loaded

    async def run(self, task: str, context: dict[str, Any]) -> SwarmResult:
        """Execute the swarm and return results."""
        swarm_id = _attr(self.config, "id", "unknown")
        entry_id = _attr(self.config, "entry_point", "")
        t0 = time.monotonic()
        with envelope_scope(context) as run_id:
            try:
                agents = []
                entry_agent = None
                for agent_config in (_attr(self.config, "agents", []) or []):
                    agent = self._build_agent(agent_config, {**context, "run_id": run_id})
                    agents.append(agent)
                    if _ag_attr(agent_config, "id") == entry_id:
                        entry_agent = agent
                if not agents:
                    return SwarmResult(
                        status="error",
                        output="No agents defined in swarm configuration",
                        run_id=run_id or "",
                    )

                _emit_event("swarm.launched", {
                    "swarm_id": swarm_id, "entry_point": entry_id,
                    "agent_count": len(agents),
                    "run_id": run_id or "",
                })

                if not entry_agent:
                    entry_agent = agents[0]

                hooks = _build_swarm_hooks(swarm_id, run_id, context)
                swarm = self._swarm_runtime.create_swarm(
                    agents,
                    entry_point=entry_agent,
                    max_handoffs=_attr(self.config, "max_handoffs", 20),
                    max_iterations=_attr(self.config, "max_iterations", 20),
                    execution_timeout=float(
                        _attr(self.config, "execution_timeout", 900)),
                    node_timeout=float(
                        _attr(self.config, "node_timeout", 300)),
                    hooks=hooks,
                )
                result = await self._swarm_runtime.invoke_async(
                    swarm, task, {**context, "run_id": run_id},
                )
                result.run_id = run_id or ""
                _emit_event("swarm.completed", {
                    "swarm_id": swarm_id, "status": result.status,
                    "run_id": run_id or "",
                    "execution_time": time.monotonic() - t0,
                    "token_usage": result.accumulated_usage,
                })
                return result

            except ImportError as e:
                return _swarm_error(
                    swarm_id, run_id or "",
                    f"Runtime package required: {e}",
                )
            except Exception as e:
                return _swarm_error(swarm_id, run_id or "", str(e))

    def _build_agent(self, agent_config: dict[str, Any], context: dict[str, Any]) -> Any:
        """Build an agent from configuration using the runtime adapter."""
        tools: list[Any] = list(self._mcp_tools or [])
        tools.extend(self._load_tools(_ag_attr(agent_config, "tools", []) or []))

        # Inject context variables into system prompt
        system_prompt = inject_variables(
            _ag_attr(agent_config, "system_prompt", ""), context,
        )

        # Build plugins: Skills + Collaboration
        plugins = self._build_plugins(agent_config)

        config = AgentConfig(
            name=_ag_attr(agent_config, "id", "agent"),
            description=_ag_attr(agent_config, "description", ""),
            system_prompt=system_prompt,
            model=_ag_attr(agent_config, "model", "us.amazon.nova-lite-v1:0"),
            tools=tools,
            plugins=plugins,
            trace_attributes=trace_attributes_from_context(context, agent_id=_ag_attr(agent_config, "id", "agent")),
        )

        return self._agent_runtime.create_agent(config)

    def _load_tools(self, tool_specs: list[str]) -> list[Any]:
        """Load tools from various sources."""
        from factory.agent.runtime.adapters import create_tool_loader
        loader = create_tool_loader(self.backend)
        return [t for t in (loader.load_tool(s) for s in tool_specs) if t]

    def _build_plugins(self, agent_config: Any) -> list[Any]:
        """Build per-agent Skills, collaboration, and offloading plugins."""
        from ._plugins import build_swarm_agent_plugins
        all_agents = [
            _ag_attr(a, "id", "")
            for a in (_attr(self.config, "agents", []) or [])
        ]
        return build_swarm_agent_plugins(
            _ag_attr(agent_config, "id", "agent"), all_agents,
            node_config={"skills": _ag_attr(agent_config, "skills", []) or []},
        )

    def _inject_variables(self, template: str, context: dict[str, Any]) -> str:
        """Backwards-compat shim — delegates to shared helper."""
        return inject_variables(template, context)
