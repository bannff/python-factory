"""Concurrent AG-UI message offer without owning steering state."""
from __future__ import annotations

from typing import Any


def delivery_event(value: Any) -> dict[str, Any]:
    """Project a persisted delivery without message content or principal data."""
    return {
        "type": "CUSTOM", "name": "session.steer",
        "value": {
            "session_id": value.session_id,
            "delivery_id": value.delivery_id,
            "send_id": value.send_id,
            "state": "written",
            "revision": value.revision,
        },
    }


async def offer_busy_steer(
    thread_id: str, messages: list[dict[str, Any]], user_message: str,
    agent_id: str | None, identity: dict[str, str] | None,
) -> dict[str, Any] | None:
    """Persist guidance only when its verified Agent thread is active."""
    if identity is None:
        return None
    from .ag_ui_helpers import extract_user_message_id
    send_id = extract_user_message_id(messages)
    if send_id is None:
        return None
    from factory.agent.interface import get_chat_agent
    delivery = await get_chat_agent().steer(
        thread_id, send_id, user_message, agent_id=agent_id,
        tenant_id=identity["tenant_id"], owner_id=identity["principal_id"],
    )
    return delivery_event(delivery) if delivery is not None else None


__all__ = ["delivery_event", "offer_busy_steer"]
