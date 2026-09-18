"""Builder runtime — transport-neutral internal tooling access."""
from __future__ import annotations

import os

from .models import BuilderResult, PageReadFailure, PageReadSuccess
from .ports import BuilderPort


def create_adapter() -> BuilderPort:
    """Create the configured transport adapter."""
    adapter_name = os.environ.get("BUILDER_ADAPTER", "mock")
    match adapter_name:
        case "midway":
            from .adapters.midway import MidwayBuilderAdapter
            return MidwayBuilderAdapter()
        case "mcp_proxy":
            from .adapters.mcp_proxy import McpProxyBuilderAdapter
            return McpProxyBuilderAdapter()
        case "mock" | _:
            from .adapters.mock import MockBuilderAdapter
            return MockBuilderAdapter()


class BuilderRuntime:
    """Runtime for Builder operations without MCP transport concerns."""

    def __init__(self, adapter: BuilderPort | None = None) -> None:
        self._adapter = adapter or create_adapter()

    async def read_url(self, url: str) -> PageReadSuccess | PageReadFailure:
        return await self._adapter.read_url(url)

    async def search_code(
        self, query: str, search_type: str = "code", page: int = 1,
    ) -> BuilderResult:
        return await self._adapter.search_code(query, search_type, page)

    async def get_pipeline_details(self, pipeline_name: str) -> BuilderResult:
        return await self._adapter.get_pipeline_details(pipeline_name)

    async def read_package_file(
        self, package_name: str, file_path: str, branch: str = "mainline",
    ) -> BuilderResult:
        return await self._adapter.read_package_file(package_name, file_path, branch)

    async def list_package_files(
        self, package_name: str, path: str = "", branch: str = "mainline",
    ) -> BuilderResult:
        return await self._adapter.list_package_files(package_name, path, branch)

    def health_check(self) -> dict[str, object]:
        return self._adapter.health_check()
