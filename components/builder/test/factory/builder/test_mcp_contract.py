"""Full-server strict Pydantic v2 MCP contract tests for Builder."""
from __future__ import annotations

import asyncio

import pytest

from factory.builder.runtime.adapters.mock import MockBuilderAdapter
from factory.builder.runtime.runtime import BuilderRuntime
from factory.builder.server import create_mcp_server
from factory.mcp_utils.interface import SchemaMigrationError, ToolResult


_DETERMINISTIC = {
    "builder_get_capabilities", "builder_health_check", "builder_describe_config_schema",
}
_OPERATIONAL = {
    "builder_read_url", "builder_search_code", "builder_get_pipeline",
    "builder_read_package_file", "builder_list_package_files",
}


def _server() -> tuple[MockBuilderAdapter, object]:
    adapter = MockBuilderAdapter()
    adapter.seed_file("Pkg", "lib/stack.ts", "export class Stack {}")
    return adapter, create_mcp_server(BuilderRuntime(adapter))


def test_full_server_catalog_and_categories_are_exact() -> None:
    _, server = _server()
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert set(tools) == _DETERMINISTIC | _OPERATIONAL
    assert {name for name, tool in tools.items() if tool.fn._mcp_category == "deterministic"} == _DETERMINISTIC
    assert {name for name, tool in tools.items() if tool.fn._mcp_category == "operational"} == _OPERATIONAL


def test_public_transport_has_envelopes_and_preserves_defaults() -> None:
    _, server = _server()
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    direct = asyncio.run(tools["builder_read_url"].fn(url="https://code.amazon.com/packages/Pkg"))
    assert isinstance(direct, ToolResult)
    assert direct.ok and direct.data is not None

    async def exercise():
        calls = {
            "builder_get_capabilities": {}, "builder_health_check": {},
            "builder_describe_config_schema": {},
            "builder_read_url": {"url": "https://code.amazon.com/packages/Pkg"},
            "builder_search_code": {"query": "role"},
            "builder_get_pipeline": {"pipeline_name": "Deploy"},
            "builder_read_package_file": {"package_name": "Pkg", "file_path": "lib/stack.ts"},
            "builder_list_package_files": {"package_name": "Pkg"},
        }
        return {name: await server.call_tool(name, args) for name, args in calls.items()}

    results = asyncio.run(exercise())
    for name, result in results.items():
        assert result.is_error is False, name
        envelope = result.structured_content
        assert envelope is not None
        assert envelope["schema_version"] == "v1"
        assert envelope["ok"] is True
        assert envelope["error"] is None
    assert results["builder_search_code"].structured_content["data"]["page"] == 1
    assert results["builder_read_package_file"].structured_content["data"]["branch"] == "mainline"
    assert results["builder_list_package_files"].structured_content["data"]["path"] == ""


def test_public_transport_rejects_coercion_and_unknown_fields() -> None:
    _, server = _server()

    async def exercise():
        return await server.call_tool("builder_search_code", {"query": "role", "page": "1"})

    with pytest.raises(SchemaMigrationError):
        asyncio.run(exercise())

    async def exercise_unknown():
        return await server.call_tool(
            "builder_read_url", {"url": "https://code.amazon.com", "unexpected": True},
        )

    with pytest.raises(SchemaMigrationError):
        asyncio.run(exercise_unknown())


def test_missing_package_file_is_successful_negative_data() -> None:
    _, server = _server()

    async def exercise():
        return await server.call_tool(
            "builder_read_package_file", {"package_name": "Pkg", "file_path": "missing.ts"},
        )

    result = asyncio.run(exercise())
    assert result.is_error is False
    envelope = result.structured_content
    assert envelope is not None and envelope["ok"] is True
    assert envelope["data"] == {
        "found": False, "package": "Pkg", "path": "missing.ts",
        "branch": "mainline", "status": 404, "content": None, "page_url": None,
    }


def test_adapter_error_maps_use_safe_failed_envelope() -> None:
    class FailingAdapter(MockBuilderAdapter):
        async def read_url(self, url: str) -> dict[str, object]:
            return {"error": "cookie=/private/token path=/secret"}

    server = create_mcp_server(BuilderRuntime(FailingAdapter()))

    async def exercise():
        return await server.call_tool("builder_read_url", {"url": "https://code.amazon.com"})

    result = asyncio.run(exercise())
    assert result.is_error is True
    envelope = result.structured_content
    assert envelope == {
        "schema_version": "v1", "ok": False, "data": None,
        "error": "tool_execution_failed", "idempotency_key": None,
    }
    assert "cookie" not in result.content[0].text


def test_page_fallbacks_preserve_midway_and_proxy_success_data() -> None:
    from factory.builder.runtime.models import PageReadSuccess

    class PageFallbackAdapter(MockBuilderAdapter):
        async def search_code(self, query: str, search_type: str = "code", page: int = 1):
            return PageReadSuccess(url="https://code.amazon.com/search?q=role", content="search page", status=200)

        async def get_pipeline_details(self, pipeline_name: str):
            return PageReadSuccess(url="https://pipelines.amazon.com/pipelines/Deploy", content="pipeline page", status=200)

        async def list_package_files(self, package_name: str, path: str = "", branch: str = "mainline"):
            return PageReadSuccess(url="https://code.amazon.com/packages/Pkg/trees/mainline", content="listing page", status=200)

    server = create_mcp_server(BuilderRuntime(PageFallbackAdapter()))

    async def exercise():
        return (
            await server.call_tool("builder_search_code", {"query": "role"}),
            await server.call_tool("builder_get_pipeline", {"pipeline_name": "Deploy"}),
            await server.call_tool("builder_list_package_files", {"package_name": "Pkg"}),
        )

    search, pipeline, listing = asyncio.run(exercise())
    for result, expected in ((search, "search page"), (pipeline, "pipeline page"), (listing, "listing page")):
        assert result.is_error is False
        envelope = result.structured_content
        assert envelope is not None and envelope["ok"] is True
        assert envelope["data"]["page_fallback"]["content"] == expected
        assert envelope["data"]["page_fallback"]["status"] == 200


def test_midway_style_page_404_is_successful_missing_package_file() -> None:
    from factory.builder.runtime.models import PageReadFailure

    class Midway404Adapter(MockBuilderAdapter):
        async def read_package_file(self, package_name: str, file_path: str, branch: str = "mainline"):
            return PageReadFailure(
                url="https://code.amazon.com/packages/Pkg/blobs/mainline/--/missing.ts",
                status=404, error_code="http_error",
            )

    server = create_mcp_server(BuilderRuntime(Midway404Adapter()))

    async def exercise():
        return await server.call_tool(
            "builder_read_package_file", {"package_name": "Pkg", "file_path": "missing.ts"},
        )

    result = asyncio.run(exercise())
    envelope = result.structured_content
    assert result.is_error is False
    assert envelope is not None and envelope["ok"] is True
    assert envelope["data"] == {
        "found": False, "package": "Pkg", "path": "missing.ts", "branch": "mainline",
        "status": 404, "content": None, "page_url": None,
    }
