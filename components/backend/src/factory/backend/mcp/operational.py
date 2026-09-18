"""Operational (stateful) MCP tools for backend module.

These tools perform backend operations: cache, graph, and document operations.
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

from factory.mcp_utils.interface import operational

if TYPE_CHECKING:
    from ..runtime.registry import AdapterRegistry
    from ..runtime.runtime import BackendRuntime


def register(
    mcp: Any,
    get_runtime: Callable[[], "BackendRuntime"],
    get_registry: Callable[[], "AdapterRegistry"],
) -> None:
    """Register operational tools with the MCP server."""

    @mcp.tool()
    @operational
    def cache_get(key: str, adapter_name: str = "default-cache") -> dict[str, Any]:
        """Get a value from cache."""
        try:
            value = get_runtime().cache_get(key, adapter_name)
            get_registry().record_operation(adapter_name)
            return {"key": key, "value": value, "found": value is not None}
        except Exception as e:
            get_registry().record_error(adapter_name, str(e))
            return {"error": str(e)}

    @mcp.tool()
    @operational
    def cache_set(
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
        adapter_name: str = "default-cache",
    ) -> dict[str, Any]:
        """Set a value in cache."""
        try:
            get_runtime().cache_set(key, value, ttl_seconds, adapter_name)
            get_registry().record_operation(adapter_name)
            return {"ok": True, "key": key}
        except Exception as e:
            get_registry().record_error(adapter_name, str(e))
            return {"error": str(e)}

    @mcp.tool()
    @operational
    def graph_add_node(
        node_id: str,
        properties: dict[str, Any] | None = None,
        adapter_name: str = "default-graph",
    ) -> dict[str, Any]:
        """Add a node to the graph."""
        try:
            get_runtime().graph_add_node(node_id, properties or {}, adapter_name)
            get_registry().record_operation(adapter_name)
            return {"ok": True, "node_id": node_id}
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    @operational
    def document_insert(
        collection: str,
        document: dict[str, Any],
        adapter_name: str = "default-document",
    ) -> dict[str, Any]:
        """Insert a document."""
        try:
            doc_id = get_runtime().document_insert(collection, document, adapter_name)
            get_registry().record_operation(adapter_name)
            return {"ok": True, "id": doc_id}
        except Exception as e:
            return {"error": str(e)}
