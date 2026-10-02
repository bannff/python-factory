"""ChatAgentPort facade over the Strands runtime adapter (durable
sessions: ``RepositorySessionManager`` per thread over the SQL repo)."""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

from factory.mcp_utils.interface import ScopedCapabilityClientPort

from ..models import (
    ChatStreamEvent, DoneEvent, ErrorEvent, FrontendToolSpec, ReasoningTextEvent,
    StateDeltaEvent, TextDeltaEvent, ToolCallDeltaEvent, ToolResultEvent,
)
from ..ports import AgentResult
from ..personas import AGENT_ID_ENV, DEFAULT_AGENT_ID
from ..runtime_contracts import RuntimeInvocation
from .strands_agent_factory import bind_invocation, reset_invocation
from .strands_frontend_stub import register_frontend_stubs, unregister_frontend_stubs
from .strands_session_manager import build_session_manager
from .strands_session_repository import SqlSessionRepository
from .strands_stream import strands_event_tuples
from .strands_thread_registry import StrandsThreadRegistry

# Event kinds the phase-1 facade emits (the phase-2 interrupt rail adds
# "interrupt" via the same dispatch table).
_EVENTS: dict[str, type] = {
    "text_delta": TextDeltaEvent, "tool_call_delta": ToolCallDeltaEvent,
    "tool_result": ToolResultEvent, "reasoning_text": ReasoningTextEvent,
    "state_delta": StateDeltaEvent, "done": DoneEvent,
}


class StrandsChatAgent:
    """Persistent chat facade preserving persona and thread identity.

    ``StrandsThreadRegistry`` owns the per-thread agent cache and the
    live-turn lifecycle; capabilities are projected as native strands
    tools by ``strands_agent_factory``; durable sessions ride the
    strands ``RepositorySessionManager`` over ``SqlSessionRepository``.
    """

    def __init__(self, client: ScopedCapabilityClientPort, model_factory: Any,
                 model_id: str = "", memory_scope: str = "default") -> None:
        self._client = client
        self._model_factory = model_factory
        self._model_id = model_id
        self._memory_scope = memory_scope
        self._threads = StrandsThreadRegistry()
        self._tools: list[Any] | None = None
        self._sessions = SqlSessionRepository()

    def _request(
        self, thread_id: str, message: str, agent_id: str | None, *,
        fe_tools: list[FrontendToolSpec] | None = None,
        messages: list[dict[str, Any]] | None = None, model_id: str | None = None,
        tenant_id: str | None = None, owner_id: str | None = None,
        memory_mode: str | None = None,
    ) -> RuntimeInvocation:
        del fe_tools, messages
        return RuntimeInvocation(
            invocation_id=f"chat-{uuid4().hex}",
            agent_id=agent_id or os.getenv(AGENT_ID_ENV, DEFAULT_AGENT_ID),
            prompt=message,
            capability_scope_digest=self._client.scope.digest,
            model_id=model_id or self._model_id,
            memory_scope=self._memory_scope,
            memory_mode=memory_mode or "",
            thread_id=thread_id, tenant_id=tenant_id, owner_id=owner_id,
        )

    async def _agent_for(self, thread_id: str, agent_id: str) -> Any:
        """Build (or reuse) the thread's Agent; discover tools once."""
        from ..personas import resolve_agent_config
        from ..steering_documents import apply_steering
        from .strands_agent_factory import build_thread_agent_tools
        from .strands_model import build_strands_model

        async def build() -> Any:
            persona = resolve_agent_config(agent_id)
            if self._tools is None:
                self._tools = await build_thread_agent_tools(self._client, persona)
            from strands import Agent

            system_prompt, _digest = apply_steering(persona.system_prompt)
            builder = self._model_factory or build_strands_model
            return Agent(
                agent_id=persona.id, name=f"{persona.id}-{thread_id}",
                system_prompt=system_prompt, model=builder(self._model_id),
                tools=list(self._tools), callback_handler=None,
                session_manager=build_session_manager(f"{persona.id}-{thread_id}"),
            )

        return await self._threads.get_or_build(thread_id, agent_id, build)

    async def invoke(self, thread_id: str, message: str,
                     tools: list[Any] | None = None,
                     agent_id: str | None = None) -> AgentResult:
        del tools
        agent = await self._agent_for(
            thread_id, agent_id or os.getenv(AGENT_ID_ENV, DEFAULT_AGENT_ID),
        )
        try:
            result = await agent.invoke_async(message)
        except asyncio.CancelledError:
            return AgentResult("", "cancelled", {})
        text = "".join(
            block["text"] for block in result.message.get("content", ())
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        )
        return AgentResult(text, "completed", {})

    async def stream(
        self, thread_id: str, message: str,
        fe_tools: list[FrontendToolSpec] | None = None,
        messages: list[dict[str, Any]] | None = None,
        agent_id: str | None = None, model_id: str | None = None,
        tenant_id: str | None = None, owner_id: str | None = None,
        memory_mode: str | None = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        request = self._request(
            thread_id, message, agent_id, fe_tools=fe_tools, messages=messages,
            model_id=model_id, tenant_id=tenant_id, owner_id=owner_id,
            memory_mode=memory_mode,
        )
        agent = await self._agent_for(thread_id, request.agent_id)
        self._threads.track(request.invocation_id)
        stubs = register_frontend_stubs(agent, fe_tools)
        token = bind_invocation(request)
        try:
            async for raw in agent.stream_async(message):
                for kind, payload in strands_event_tuples(raw):
                    if kind == "tool_result" and not payload.get("is_error"):
                        payload = _maybe_sentinel_payload(payload)
                    yield _EVENTS[kind](**payload)
        except Exception as exc:
            from .provider_errors import log_stream_failure, provider_error_message
            log_stream_failure(exc)
            yield ErrorEvent(message=provider_error_message(exc))
        finally:
            reset_invocation(token)
            unregister_frontend_stubs(agent, stubs)
            self._threads.release(request.invocation_id)

    async def steer(
        self, thread_id: str, send_id: str, message: str, *,
        agent_id: str | None = None, tenant_id: str | None = None,
        owner_id: str | None = None,
    ) -> Any | None:
        """Queued-guidance hook port lands with the phase-2 model-call hook."""
        del thread_id, send_id, message, agent_id, tenant_id, owner_id
        return None

    async def cancel(self, thread_id: str) -> bool:
        """Cancel the running turn(s) for a thread via the strands seam."""
        return await self._threads.cancel(thread_id)

    def close(self, thread_id: str) -> None:
        """Drop the cached agent AND its durable session rows (all personas)."""
        self._threads.drop(thread_id)
        suffix = f"-{thread_id}"
        for session_id in self._sessions.session_ids():
            if session_id.endswith(suffix):
                self._sessions.delete_session(session_id)

    async def fork_thread(self, agent_id: str, source_thread_id: str,
                          target_thread_id: str) -> bool:
        """Copy a thread's durable transcript onto a new thread id under
        the SAME persona. False when the source has no durable history."""
        return self._sessions.fork_session(
            f"{agent_id}-{source_thread_id}", f"{agent_id}-{target_thread_id}",
        )

    async def history(self, agent_id: str, thread_id: str) -> list[dict[str, Any]]:
        """Return the durable transcript in AG-UI message shape."""
        from .strands_history import session_messages_to_agui
        return session_messages_to_agui(self._sessions, f"{agent_id}-{thread_id}")

    async def aclose(self) -> None:
        await self._threads.aclose()


def _maybe_sentinel_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep the ``_frontend_pending`` sentinel payload byte-identical:
    the AG-UI mapper routes the FE handler round-trip off these fields."""
    inner = payload.get("payload")
    if isinstance(inner, list) and len(inner) == 1:
        json_block = inner[0].get("json") if isinstance(inner[0], dict) else None
        if isinstance(json_block, dict) and json_block.get("_frontend_pending") is True:
            return {
                "tool_call_id": payload["tool_call_id"], "payload": json_block,
                "is_error": False,
            }
    return payload


__all__ = ["StrandsChatAgent"]
