"""Framework-neutral catalog for the deprecated backend brick."""
from __future__ import annotations

from typing import Any
from .runtime.registry import get_registry
from .runtime.runtime import BackendRuntime, get_runtime
from .authoring import get_authoring_tools, is_authoring_enabled
from .mcp import deterministic, operational, authoring, resources, prompts
from factory.mcp_utils.server import make_lazy_runner
from factory.mcp_utils.runtime.tool_catalog import ToolCatalog


def create_tool_catalog(runtime: BackendRuntime | None = None) -> ToolCatalog:
    runtime = runtime or get_runtime()
    catalog = ToolCatalog("backend-module")
    get_current = lambda: runtime
    deterministic.register(catalog, get_current, get_registry, is_authoring_enabled)
    operational.register(catalog, get_current, get_registry)
    authoring.register(catalog, get_authoring_tools)
    resources.register(catalog)
    prompts.register(catalog)
    return catalog


def create_mcp_server(runtime: BackendRuntime | None = None) -> ToolCatalog:
    return create_tool_catalog(runtime)


def get_capabilities() -> dict[str, Any]:
    return {"name": "backend", "version": "1.0.0", "backends": ["memory", "redis", "postgres"], "features": ["backend_services", "infrastructure", "cache_adapters", "graph_adapters"]}


def health_check() -> dict[str, Any]:
    return {"healthy": True, "services": ["cache", "graph", "document"]}


def describe_config_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {"cache_backend": {"type": "string", "enum": ["memory", "redis"]}, "graph_backend": {"type": "string", "enum": ["networkx", "neo4j"]}}}


get_mcp_server, main = make_lazy_runner(create_mcp_server)
if __name__ == "__main__":
    main()
