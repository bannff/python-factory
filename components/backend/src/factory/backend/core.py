"""Backend core - high-level convenience functions.

Provides simple API for common backend operations (cache, graph, document)
without needing to manage the full BackendRuntime lifecycle.
"""

from __future__ import annotations

from typing import Any

from .runtime.runtime import get_runtime, reset_runtime


# Re-export runtime management
__all__ = [
    "get_runtime",
    "reset_runtime",
    "cache_get",
    "cache_set",
    "cache_delete",
    "graph_add_node",
    "graph_add_edge",
    "graph_query",
    "document_insert",
    "document_find",
    "document_delete",
]


# Cache operations
def cache_get(key: str, adapter_name: str = "default-cache") -> Any:
    """Get a value from the cache.
    
    Args:
        key: Cache key.
        adapter_name: Name of the cache adapter to use.
        
    Returns:
        Cached value or None if not found.
    """
    return get_runtime().cache_get(key, adapter_name)


def cache_set(
    key: str,
    value: Any,
    ttl_seconds: int | None = None,
    adapter_name: str = "default-cache",
) -> None:
    """Set a value in the cache.
    
    Args:
        key: Cache key.
        value: Value to cache.
        ttl_seconds: Optional TTL in seconds.
        adapter_name: Name of the cache adapter to use.
    """
    get_runtime().cache_set(key, value, ttl_seconds, adapter_name)


def cache_delete(key: str, adapter_name: str = "default-cache") -> None:
    """Delete a key from the cache.
    
    Args:
        key: Cache key to delete.
        adapter_name: Name of the cache adapter to use.
    """
    get_runtime().cache_delete(key, adapter_name)


# Graph operations
def graph_add_node(
    node_id: str,
    properties: dict[str, Any],
    adapter_name: str = "default-graph",
) -> None:
    """Add a node to the graph.
    
    Args:
        node_id: Unique node identifier.
        properties: Node properties.
        adapter_name: Name of the graph adapter to use.
    """
    get_runtime().graph_add_node(node_id, properties, adapter_name)


def graph_add_edge(
    source_id: str,
    target_id: str,
    edge_type: str,
    properties: dict[str, Any] | None = None,
    adapter_name: str = "default-graph",
) -> None:
    """Add an edge between two nodes.
    
    Args:
        source_id: Source node ID.
        target_id: Target node ID.
        edge_type: Type of relationship.
        properties: Optional edge properties.
        adapter_name: Name of the graph adapter to use.
    """
    get_runtime().graph_add_edge(
        source_id, target_id, edge_type, properties or {}, adapter_name
    )


def graph_query(
    query: str,
    params: dict[str, Any] | None = None,
    adapter_name: str = "default-graph",
) -> list[dict[str, Any]]:
    """Execute a graph query.
    
    Args:
        query: Query string (format depends on backend).
        params: Query parameters.
        adapter_name: Name of the graph adapter to use.
        
    Returns:
        List of query results.
    """
    return get_runtime().graph_query(query, params or {}, adapter_name)


# Document operations
def document_insert(
    collection: str,
    document: dict[str, Any],
    adapter_name: str = "default-document",
) -> str:
    """Insert a document into a collection.
    
    Args:
        collection: Collection name.
        document: Document to insert.
        adapter_name: Name of the document adapter to use.
        
    Returns:
        Document ID.
    """
    return get_runtime().document_insert(collection, document, adapter_name)


def document_find(
    collection: str,
    query: dict[str, Any],
    limit: int = 100,
    adapter_name: str = "default-document",
) -> list[dict[str, Any]]:
    """Find documents matching a query.
    
    Args:
        collection: Collection name.
        query: Query filter.
        limit: Maximum results to return.
        adapter_name: Name of the document adapter to use.
        
    Returns:
        List of matching documents.
    """
    return get_runtime().document_find(collection, query, limit, adapter_name)


def document_delete(
    collection: str,
    doc_id: str,
    adapter_name: str = "default-document",
) -> None:
    """Delete a document from a collection.
    
    Args:
        collection: Collection name.
        doc_id: Document ID to delete.
        adapter_name: Name of the document adapter to use.
    """
    get_runtime().document_delete(collection, doc_id, adapter_name)
