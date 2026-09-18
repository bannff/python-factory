"""Backward-compatible NetworkX graph adapter.

Delegates to ``factory.graph`` brick's NetworkXGraph.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .base import GraphAdapter
from factory.backend.runtime.models import Node, Edge


class NetworkXAdapter(GraphAdapter):
    """In-memory graph adapter — delegates to graph brick."""

    def __init__(self) -> None:
        from factory.graph.runtime.adapters.networkx_adapter import NetworkXGraph
        self._delegate = NetworkXGraph()

    def connect(self) -> None:
        pass  # in-memory, nothing to connect

    def health_check(self) -> bool:
        h = self._delegate.health_check()
        return h.healthy

    def add_node(self, label: str, properties: Dict[str, Any]) -> Node:
        from factory.graph.runtime.ports import Entity

        node_id = properties.pop("id", None) or str(uuid.uuid4())
        entity = Entity(id=node_id, type=label, properties=properties)
        self._delegate.add_entity(entity)
        return Node(id=node_id, label=label, properties=properties)

    def add_edge(
        self,
        from_id: str,
        to_id: str,
        relationship_type: str,
        properties: Dict[str, Any],
    ) -> Edge:
        from factory.graph.runtime.ports import Relationship

        edge_id = properties.pop("id", None) or str(uuid.uuid4())
        rel = Relationship(
            id=edge_id,
            type=relationship_type,
            source_id=from_id,
            target_id=to_id,
            properties=properties,
        )
        self._delegate.add_relationship(rel)
        return Edge(
            id=edge_id,
            from_id=from_id,
            to_id=to_id,
            relationship_type=relationship_type,
            properties=properties,
        )

    def get_node(self, node_id: str) -> Optional[Node]:
        entity = self._delegate.get_entity(node_id)
        if entity is None:
            return None
        return Node(
            id=entity.id,
            label=entity.type,
            properties=entity.properties,
        )

    def query(self, query: str) -> List[Any]:
        if query.startswith("neighbors:"):
            node_id = query.split(":")[1]
            neighbors = self._delegate.get_neighbors(node_id)
            return [n.id for n in neighbors]
        return []


class NetworkXGraphAdapter(NetworkXAdapter):
    """Backward-compatible alias for earlier import paths."""
    pass
