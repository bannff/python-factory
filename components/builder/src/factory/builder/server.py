"""Native MCP v2 server for builder brick.

Public MCP surface — no domain logic here.
"""
from __future__ import annotations

from typing import Any

from .runtime.runtime import BuilderRuntime
from .mcp import deterministic, operational, operational_files


def _register_tools(registry: Any, runtime: BuilderRuntime) -> None:
    deterministic.register(registry, runtime)
    operational.register(registry, runtime)
    operational_files.register(registry, runtime)


def create_tool_catalog(runtime: BuilderRuntime | None = None) -> Any:
    """Create the transport-neutral Builder tool catalog."""
    from factory.mcp_utils.runtime.tool_catalog import ToolCatalog

    active_runtime = runtime or BuilderRuntime()
    catalog = ToolCatalog("builder-module")
    _register_tools(catalog, active_runtime)
    return catalog


def create_mcp_server(runtime: BuilderRuntime | None = None) -> Any:
    """Return the canonical framework-neutral catalog."""
    return create_tool_catalog(runtime)
