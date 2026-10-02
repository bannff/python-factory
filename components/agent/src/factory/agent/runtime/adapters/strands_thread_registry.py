"""Per-thread agent cache and active-turn task registry for the strands chat facade."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

__all__ = ["StrandsThreadRegistry"]


class StrandsThreadRegistry:
    """Owns one cached ``strands.Agent`` per thread plus running-turn tasks.

    Cancel bookkeeping mirrors ``langchain_active_threads.py``: the task
    driving the current turn is never cancelled by its own turn.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}
        self._active: dict[str, asyncio.Task[Any]] = {}

    async def get_or_build(
        self, thread_id: str, agent_id: str, build: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Return the thread's cached Agent, awaiting ``build()`` once.

        ``agent_id`` documents that the first build wins the persona for
        the thread's cache lifetime (single-writer per thread).
        """
        del agent_id
        if thread_id not in self._agents:
            self._agents[thread_id] = await build()
        return self._agents[thread_id]

    def drop(self, thread_id: str) -> None:
        """Forget the thread's cached agent (durable delete lands phase 2)."""
        self._agents.pop(thread_id, None)

    def track(self, invocation_id: str) -> None:
        """Track the running turn's task (the caller's current task)."""
        task = asyncio.current_task()
        if task is not None:
            self._active[invocation_id] = task

    def release(self, invocation_id: str) -> None:
        self._active.pop(invocation_id, None)

    async def cancel(self, thread_id: str) -> bool:
        """Cancel the thread's agent loop and any of its other running turns."""
        cancelled = False
        agent = self._agents.get(thread_id)
        if agent is not None:
            agent.cancel()
            cancelled = True
        for invocation_id, task in list(self._active.items()):
            if task is not asyncio.current_task():
                task.cancel()
                self._active.pop(invocation_id, None)
                cancelled = True
        return cancelled

    async def aclose(self) -> None:
        for invocation_id, task in list(self._active.items()):
            if task is not asyncio.current_task():
                task.cancel()
                self._active.pop(invocation_id, None)
