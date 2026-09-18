"""Gateway wiring for the side-chat scratch conversation (feature-map row 19).

Composes the real dependencies — the ambient chat model, the live
tool-category lookup, and the MCP aggregator's dispatch — into a
:class:`SideChatService`, then mounts it as the `side/{open,turn,close}`
HTTP routes via :func:`side_routes.register_side_routes`.

This is the ~2-line seam every earlier slice was built and injected against:
every layer beneath it (policy, gate, conversation store, executor, service,
HTTP router, the LLM planner) is already unit-tested in isolation — this
module's only job is composition, so it stays a thin, readable wire-up
rather than a place new logic accumulates.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

#: Ambient default model id — same "bare openrouter, env-selected model"
#: convention ``resolve_chat_profile`` and the rest of the codebase use when
#: no session-specific model is in scope for a request.
_DEFAULT_MODEL_ID = "openrouter"


def register_side_chat(app: Any) -> None:
    from factory.mcp_utils.runtime.side_chat_service import SideChatService
    from factory.mcp_utils.runtime.side_llm_complete import build_mcp_utils_complete
    from factory.mcp_utils.runtime.side_planner import build_llm_side_planner
    from .side_routes import register_side_routes

    model_id = os.getenv("SIDE_CHAT_MODEL_ID", _DEFAULT_MODEL_ID)

    def category_lookup() -> dict[str, str]:
        # Resolved fresh per turn: bricks load lazily, so an early-boot
        # lookup could see fewer tools than are actually available later.
        from factory.mcp_server.runtime.category_lookup import build_category_lookup
        return build_category_lookup()

    def dispatch(tool_name: str, args: dict[str, Any]) -> Any:
        import asyncio

        from .bridge import _get_aggregator
        agg = _get_aggregator()
        if agg is None:
            raise RuntimeError("MCP aggregator unavailable")
        result = agg.invoke_tool(tool_name, **args)
        if asyncio.iscoroutine(result):
            # SideChatService.turn is synchronous (built pure/testable), and
            # this dispatch runs inside the `side/turn` request handler
            # OUTSIDE any running event loop (FastAPI runs sync endpoints in
            # a worker thread), so a fresh loop here is safe — same shape as
            # bridge.py's own `await`, just from a sync call site.
            result = asyncio.run(result)
        return result

    try:
        complete = build_mcp_utils_complete(model_id)
        planner = build_llm_side_planner(complete, category_lookup)
    except Exception:
        # No model configured (e.g. missing OPENROUTER_API_KEY) — the side
        # panel still opens/records turns; it just can't run any tools until
        # a model is configured. Never fail route registration over this.
        logger.warning("[side_chat] planner unavailable, side turns will run no tools", exc_info=True)
        planner = lambda query: []  # noqa: E731

    service = SideChatService(planner=planner, category_lookup=category_lookup, dispatch=dispatch)
    register_side_routes(app, lambda: service)


__all__ = ["register_side_chat"]
