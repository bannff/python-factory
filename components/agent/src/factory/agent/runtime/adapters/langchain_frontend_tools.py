"""LangGraph-native frontend tools that suspend until CopilotKit resumes."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
from langgraph.types import interrupt

from ..models import FrontendToolSpec


def _build_frontend_tool(spec: FrontendToolSpec) -> BaseTool:
    """Build one SDK-native structured tool with injected ``ToolRuntime``."""

    @tool(
        spec.name,
        description=spec.description,
        args_schema=spec.parameters or {"type": "object", "properties": {}},
    )
    async def frontend_tool(runtime: ToolRuntime, **kwargs: Any) -> Any:
        return interrupt({
            "_frontend_pending": True,
            "name": spec.name,
            "args": kwargs,
            "tool_call_id": runtime.tool_call_id,
        })

    return frontend_tool


def build_frontend_tools(specs: tuple[FrontendToolSpec, ...]) -> list[BaseTool]:
    """Convert validated CopilotKit registrations into LangChain tools."""
    return [_build_frontend_tool(spec) for spec in specs]


__all__ = ["build_frontend_tools", "frontend_digest"]


def frontend_digest(specs: tuple[FrontendToolSpec, ...]) -> str:
    payload = [spec.model_dump(mode="json") for spec in specs]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()
