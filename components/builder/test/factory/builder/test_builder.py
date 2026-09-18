"""Tests for Builder transport-neutral adapters and runtime."""
from __future__ import annotations

import asyncio
from typing import Any

from hypothesis import given, settings, strategies as st

from factory.builder.runtime.adapters.mock import MockBuilderAdapter
from factory.builder.runtime.models import PageReadFailure
from factory.builder.runtime.runtime import BuilderRuntime


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class TestMockAdapter:
    def test_read_url(self) -> None:
        result = _run(MockBuilderAdapter().read_url("https://code.amazon.com/packages/Foo"))
        assert result.status == 200 and "Foo" in result.content

    def test_search_code(self) -> None:
        result = _run(MockBuilderAdapter().search_code("IAM policy"))
        assert result.total == 0 and result.results == []

    def test_pipeline_details(self) -> None:
        result = _run(MockBuilderAdapter().get_pipeline_details("MyPipeline"))
        assert result.name == "MyPipeline" and result.status == "healthy"

    def test_read_seeded_file(self) -> None:
        adapter = MockBuilderAdapter()
        adapter.seed_file("MyPkg", "lib/stack.ts", "export class MyStack {}")
        assert _run(adapter.read_package_file("MyPkg", "lib/stack.ts")).content == "export class MyStack {}"

    def test_read_missing_file_preserves_safe_404(self) -> None:
        result = _run(MockBuilderAdapter().read_package_file("MyPkg", "nope.ts"))
        assert isinstance(result, PageReadFailure)
        assert result.status == 404 and result.error_code == "http_error"

    def test_list_seeded_files(self) -> None:
        adapter = MockBuilderAdapter()
        for path in ("lib/a.ts", "lib/b.ts", "src/c.ts"):
            adapter.seed_file("Pkg", path, path)
        assert _run(adapter.list_package_files("Pkg", "lib/")).count == 2

    def test_health_check(self) -> None:
        assert MockBuilderAdapter().health_check()["healthy"] is True


class TestBuilderRuntime:
    def test_default_adapter_is_mock(self) -> None:
        assert BuilderRuntime().health_check()["adapter"] == "mock"

    @settings(max_examples=20)
    @given(url=st.from_regex(r"https://code\.amazon\.com/packages/[A-Za-z]+", fullmatch=True))
    def test_read_url_returns_content(self, url: str) -> None:
        assert _run(BuilderRuntime().read_url(url)).status == 200

    @settings(max_examples=20)
    @given(query=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))))
    def test_search_returns_typed_result(self, query: str) -> None:
        assert _run(BuilderRuntime().search_code(query)).query == query

    @settings(max_examples=20)
    @given(name=st.text(min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))))
    def test_pipeline_returns_name(self, name: str) -> None:
        assert _run(BuilderRuntime().get_pipeline_details(name)).name == name


class TestMcpContract:
    def test_server_creates(self) -> None:
        from factory.builder.server import create_mcp_server
        assert create_mcp_server() is not None

    def test_capabilities(self) -> None:
        from factory.builder.server import create_mcp_server
        assert create_mcp_server() is not None


def test_proxy_page_map_becomes_typed_page_fallback(monkeypatch) -> None:
    from factory.builder.runtime.adapters import mcp_proxy
    from factory.builder.runtime.models import PageReadSuccess

    monkeypatch.setattr(
        mcp_proxy, "_get_invoker",
        lambda: lambda _tool, **_kwargs: {"url": "https://code.amazon.com/search?q=role", "content": "page", "status": 200},
    )
    result = _run(mcp_proxy.McpProxyBuilderAdapter().search_code("role"))
    assert isinstance(result, PageReadSuccess)
    assert result.url.endswith("q=role") and result.content == "page" and result.status == 200


def test_proxy_404_is_a_typed_page_failure(monkeypatch) -> None:
    from factory.builder.runtime.adapters import mcp_proxy

    monkeypatch.setattr(
        mcp_proxy, "_get_invoker",
        lambda: lambda _tool, **_kwargs: {"url": "https://code.amazon.com/packages/Pkg", "status": 404, "error": "missing"},
    )
    result = _run(mcp_proxy.McpProxyBuilderAdapter().read_package_file("Pkg", "missing.ts"))
    assert isinstance(result, PageReadFailure)
    assert result.status == 404 and result.error_code == "http_error"


def test_midway_404_retains_http_status_without_exception_text(monkeypatch) -> None:
    import httpx

    from factory.builder.runtime.adapters.midway import MidwayBuilderAdapter
    from factory.builder.runtime.models import PageReadFailure

    request = httpx.Request("GET", "https://code.amazon.com/packages/Pkg")
    response = httpx.Response(404, request=request)

    class Client:
        def get(self, url: str):
            raise httpx.HTTPStatusError("sensitive", request=request, response=response)

    adapter = MidwayBuilderAdapter()
    monkeypatch.setattr(adapter, "_get_client", lambda: Client())
    result = _run(adapter.read_url(str(request.url)))
    assert isinstance(result, PageReadFailure)
    assert result.status == 404 and result.error_code == "http_error"
    assert "sensitive" not in result.model_dump_json()
