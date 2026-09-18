"""Adapter operations — bridges backend API to brick adapter APIs.

The backend exposes a simplified API (cache_get, graph_add_node, etc.)
while the underlying cache/graph/storage bricks use richer Protocol
interfaces.  This module translates between the two.
"""

from __future__ import annotations

import uuid
from typing import Any


class AdapterOperations:
    """Operations delegated to brick adapters with API bridging."""

    def __init__(
        self,
        cache_adapters: dict[str, Any],
        graph_adapters: dict[str, Any],
        document_adapters: dict[str, Any],
    ):
        self._cache = cache_adapters
        self._graph = graph_adapters
        self._document = document_adapters

    # ---- helpers ----

    def _get(self, store: dict[str, Any], name: str, kind: str) -> Any:
        adapter = store.get(name)
        if adapter is None:
            raise ValueError(f"{kind} adapter '{name}' not found")
        return adapter

    # ---- Cache (CacheStore protocol — direct match) ----

    def cache_get(self, key: str, adapter_name: str = "default-cache") -> Any:
        return self._get(self._cache, adapter_name, "Cache").get(key)

    def cache_set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int | None = None,
        adapter_name: str = "default-cache",
    ) -> None:
        self._get(self._cache, adapter_name, "Cache").set(
            key, value, ttl_seconds,
        )

    def cache_delete(self, key: str, adapter_name: str = "default-cache") -> None:
        self._get(self._cache, adapter_name, "Cache").delete(key)

    # ---- Graph (KnowledgeGraph protocol — bridge needed) ----

    def graph_add_node(
        self,
        node_id: str,
        properties: dict[str, Any],
        adapter_name: str = "default-graph",
    ) -> None:
        from factory.graph.runtime.ports import Entity

        adapter = self._get(self._graph, adapter_name, "Graph")
        entity = Entity(
            id=node_id,
            type=properties.pop("type", "node"),
            properties=properties,
        )
        adapter.add_entity(entity)

    def graph_add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: dict[str, Any],
        adapter_name: str = "default-graph",
    ) -> None:
        from factory.graph.runtime.ports import Relationship

        adapter = self._get(self._graph, adapter_name, "Graph")
        rel = Relationship(
            id=properties.pop("id", str(uuid.uuid4())),
            type=edge_type,
            source_id=source_id,
            target_id=target_id,
            properties=properties,
        )
        adapter.add_relationship(rel)

    def graph_query(
        self,
        query: str,
        params: dict[str, Any],
        adapter_name: str = "default-graph",
    ) -> list[dict[str, Any]]:
        adapter = self._get(self._graph, adapter_name, "Graph")
        result = adapter.query(query, params)
        # Flatten QueryResult.entities into plain dicts for the backend API
        return [
            {"id": e.id, "type": e.type, **e.properties}
            for e in result.entities
        ]

    # ---- Document (DocumentStore protocol — bridge needed) ----

    def document_insert(
        self,
        collection: str,
        document: dict[str, Any],
        adapter_name: str = "default-document",
    ) -> str:
        adapter = self._get(self._document, adapter_name, "Document")
        doc = adapter.insert(collection, document)
        return doc.id

    def document_find(
        self,
        collection: str,
        query: dict[str, Any],
        limit: int = 100,
        adapter_name: str = "default-document",
    ) -> list[dict[str, Any]]:
        adapter = self._get(self._document, adapter_name, "Document")
        docs = adapter.find(collection, query, limit)
        return [{"id": d.id, "collection": d.collection, **d.data} for d in docs]

    def document_delete(
        self,
        collection: str,
        doc_id: str,
        adapter_name: str = "default-document",
    ) -> None:
        adapter = self._get(self._document, adapter_name, "Document")
        adapter.delete(collection, doc_id)
