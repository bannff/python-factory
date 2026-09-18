"""Operational typed MCP tools for Builder internal tooling."""
from __future__ import annotations

from typing import Any
from factory.mcp_utils.interface import ToolResult, operational
from factory.mcp_utils.registration import typed_tool
from factory.mcp_utils.runtime.tool_failure import tool_execution_failure

from ..runtime.runtime import BuilderRuntime
from .contracts.models import (
    PipelineInput,
    PipelineOutput,
    ReadUrlInput,
    SearchCodeInput,
    SearchCodeOutput,
    UrlReadOutput,
)
from .projections import pipeline, search_code, url_read


def register(mcp: Any, runtime: BuilderRuntime) -> None:
    """Register operational tools."""

    @typed_tool(mcp)
    @operational(input_model=ReadUrlInput, output_model=UrlReadOutput)
    async def builder_read_url(url: str) -> ToolResult[UrlReadOutput]:
        """Read content from an internal Amazon URL."""
        request = ReadUrlInput.model_validate({"url": url})
        try:
            data = await runtime.read_url(request.url)
        except Exception:
            return tool_execution_failure(builder_read_url)
        output = url_read(data) if data is not None else None
        return ToolResult(ok=True, data=output) if output is not None else tool_execution_failure(builder_read_url)

    @typed_tool(mcp)
    @operational(input_model=SearchCodeInput, output_model=SearchCodeOutput)
    async def builder_search_code(
        query: str, search_type: str = "code", page: int = 1,
    ) -> ToolResult[SearchCodeOutput]:
        """Search internal code repositories by query and page."""
        request = SearchCodeInput.model_validate({
            "query": query, "search_type": search_type, "page": page,
        })
        try:
            data = await runtime.search_code(
                request.query, request.search_type, request.page,
            )
        except Exception:
            return tool_execution_failure(builder_search_code)
        output = search_code(data, request.query, request.page)
        return ToolResult(ok=True, data=output) if output is not None else tool_execution_failure(builder_search_code)

    @typed_tool(mcp)
    @operational(input_model=PipelineInput, output_model=PipelineOutput)
    async def builder_get_pipeline(pipeline_name: str) -> ToolResult[PipelineOutput]:
        """Get pipeline details including stages and health."""
        request = PipelineInput.model_validate({"pipeline_name": pipeline_name})
        try:
            data = await runtime.get_pipeline_details(request.pipeline_name)
        except Exception:
            return tool_execution_failure(builder_get_pipeline)
        output = pipeline(data, request.pipeline_name)
        return ToolResult(ok=True, data=output) if output is not None else tool_execution_failure(builder_get_pipeline)
