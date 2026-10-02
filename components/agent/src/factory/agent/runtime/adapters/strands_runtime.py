"""Strands runtime factories for the agent/graph/coordination seams.

One ``StrandsAgentRuntime`` per attempt (mirrors the LangChain runtime's
attempt-local shape): scoped-capability client projected to native strands
tools, per-invocation approval store, and thread registry caching. Graph
and coordination runtimes wrap the same agent runtime — the strands Agent
loop IS the bounded execution, so no separate graph compiler exists.
"""
from __future__ import annotations

import os
from typing import Any

from factory.mcp_utils.interface import ScopedCapabilityClientPort

from ..approval_policy import ApprovalPolicyStore
from ..runtime_contracts import (
    RuntimeAdapterDescriptor, RuntimeInvocation, RuntimeResult,
)
from .strands_agent_factory import build_thread_agent_tools
from .strands_chat import StrandsChatAgent
from .strands_model import build_strands_model
from .strands_thread_registry import StrandsThreadRegistry


class StrandsAgentRuntime:
    """Attempt-local strands agent using only pre-scoped capabilities."""

    def __init__(
        self, client: ScopedCapabilityClientPort, *,
        model_id: str = "default",
        approval_store: ApprovalPolicyStore | None = None,
    ) -> None:
        self._client = client
        self._model_id = model_id
        self._approval_store = approval_store
        self._threads = StrandsThreadRegistry()

    async def invoke(self, request: RuntimeInvocation) -> RuntimeResult:
        agent = await self._agent_for(request)
        result = await agent.invoke_async(request.prompt)
        text = "".join(
            b["text"] for b in result.message.get("content", ())
            if isinstance(b, dict) and isinstance(b.get("text"), str)
        )
        return RuntimeResult(
            invocation_id=request.invocation_id, output=text,
            status="completed", metadata={},
        )

    async def _agent_for(self, request: RuntimeInvocation) -> Any:
        from ..personas import resolve_agent_config
        from ..steering_documents import apply_steering
        from strands import Agent

        persona = resolve_agent_config(request.agent_id)
        system_prompt, _digest = apply_steering(persona.system_prompt)

        async def build() -> Any:
            tools = await build_thread_agent_tools(self._client, persona)
            return Agent(
                agent_id=persona.id, name=f"{persona.id}-{request.thread_id}",
                system_prompt=system_prompt,
                model=build_strands_model(request.model_id or self._model_id),
                tools=list(tools), callback_handler=None,
                hooks=[],
            )

        return await self._threads.get_or_build(
            request.thread_id or "", request.agent_id or "", build,
        )

    def descriptor(self) -> RuntimeAdapterDescriptor:
        return RuntimeAdapterDescriptor(
            adapter_id="strands", package_versions=(("strands-agents", "1.56.0"),),
        )

    async def aclose(self) -> None:
        await self._threads.aclose()


class StrandsGraphRuntime:
    """Bounded graph execution over the strands agent loop."""

    def __init__(self, agents: StrandsAgentRuntime) -> None:
        self._agents = agents

    async def run(self, request: RuntimeInvocation) -> RuntimeResult:
        return await self._agents.invoke(request)


def _default_approval_store() -> ApprovalPolicyStore:
    from .approval_policy_store import SqliteApprovalPolicyStore
    return SqliteApprovalPolicyStore(os.getenv(
        "COMPANION_X_APPROVAL_POLICY_DB_PATH", "./.storage/agent-approval.db",
    ))


__all__ = [
    "StrandsAgentRuntime", "StrandsGraphRuntime", "StrandsChatAgent",
    "_default_approval_store",
]
