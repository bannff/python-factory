"""MCP-proxy Builder adapter with transport-neutral result DTOs."""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from ..models import (
    CodeSearchResult,
    PageReadFailure,
    PageReadSuccess,
    PipelineDetails,
)


def _get_invoker() -> Callable[..., object] | None:
    try:
        from factory.mcp_utils.interface import get_service
        invoker = get_service("tool_invoker")
        return invoker if callable(invoker) else None
    except Exception:
        return None


def _source_map(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    try:
        decoded: object = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _page(value: object, url: str) -> PageReadSuccess | PageReadFailure:
    source = _source_map(value)
    if source is not None:
        try:
            return PageReadSuccess.model_validate(source)
        except Exception:
            status = source.get("status")
            if isinstance(status, int) and 100 <= status <= 599:
                return PageReadFailure(url=url, status=status, error_code="http_error")
    return PageReadSuccess(url=url, content=str(value), status=200)


def _structured_or_page(
    value: object, result_type: type[CodeSearchResult] | type[PipelineDetails], url: str,
) -> CodeSearchResult | PipelineDetails | PageReadSuccess | PageReadFailure:
    source = _source_map(value)
    if source is not None:
        try:
            return result_type.model_validate(source)
        except Exception:
            try:
                return PageReadSuccess.model_validate(source)
            except Exception:
                pass
    return PageReadFailure(url=url, error_code="request_failed")


class McpProxyBuilderAdapter:
    """BuilderPort implementation backed by the registered MCP invoker."""

    async def read_url(self, url: str) -> PageReadSuccess | PageReadFailure:
        invoker = _get_invoker()
        if invoker is None:
            return PageReadFailure(url=url, error_code="request_failed")
        try:
            return _page(invoker("ReadInternalWebsites", inputs=[url]), url)
        except Exception:
            return PageReadFailure(url=url, error_code="request_failed")

    async def search_code(self, query: str, search_type: str = "code", page: int = 1):
        invoker = _get_invoker()
        url = f"https://code.amazon.com/search?q={query}&type={search_type}&p={page}"
        if invoker is None:
            return PageReadFailure(url=url, error_code="request_failed")
        try:
            return _structured_or_page(
                invoker("InternalCodeSearch", query=query, searchType=search_type, page=page),
                CodeSearchResult, url,
            )
        except Exception:
            return PageReadFailure(url=url, error_code="request_failed")

    async def get_pipeline_details(self, pipeline_name: str):
        invoker = _get_invoker()
        url = f"https://pipelines.amazon.com/pipelines/{pipeline_name}"
        if invoker is None:
            return PageReadFailure(url=url, error_code="request_failed")
        try:
            return _structured_or_page(invoker("GetPipelineDetails", pipelineName=pipeline_name), PipelineDetails, url)
        except Exception:
            return PageReadFailure(url=url, error_code="request_failed")

    async def read_package_file(self, package_name: str, file_path: str, branch: str = "mainline"):
        return await self.read_url(
            f"https://code.amazon.com/packages/{package_name}/blobs/{branch}/--/{file_path}"
        )

    async def list_package_files(self, package_name: str, path: str = "", branch: str = "mainline"):
        url = f"https://code.amazon.com/packages/{package_name}/trees/{branch}"
        return await self.read_url(f"{url}/--/{path}" if path else url)

    def health_check(self) -> dict[str, object]:
        return {"healthy": _get_invoker() is not None, "adapter": "mcp_proxy"}
