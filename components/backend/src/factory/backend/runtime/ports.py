"""Backend ports - Protocol interfaces for backend adapters.

Defines abstract interfaces that backend adapters must implement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass
class AdapterHealth:
    """Health status for a backend adapter."""

    healthy: bool
    backend: str
    latency_ms: float | None = None
    error: str | None = None


@runtime_checkable
class CachePort(Protocol):
    """Port: Cache storage (Redis, memory, etc.)"""

    def connect(self) -> None:
        """Establish connection to the backend."""
        ...

    def health_check(self) -> bool:
        """Check if the backend is healthy."""
        ...

    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set a key-value pair with optional TTL."""
        ...

    def get(self, key: str) -> Any | None:
        """Retrieve a value by key."""
        ...

    def delete(self, key: str) -> bool:
        """Delete a key."""
        ...


@runtime_checkable
class GraphPort(Protocol):
    """Port: Graph storage (Neo4j, NetworkX, etc.)"""

    def connect(self) -> None:
        """Establish connection to the backend."""
        ...

    def health_check(self) -> bool:
        """Check if the backend is healthy."""
        ...

    def add_node(self, node_id: str, labels: list[str], properties: dict[str, Any]) -> bool:
        """Add a node to the graph."""
        ...

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by ID."""
        ...

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: dict[str, Any] | None = None,
    ) -> bool:
        """Add an edge between nodes."""
        ...

    def query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a graph query."""
        ...


@runtime_checkable
class DocumentPort(Protocol):
    """Port: Document storage (TinyDB, MongoDB, etc.)"""

    def connect(self) -> None:
        """Establish connection to the backend."""
        ...

    def health_check(self) -> bool:
        """Check if the backend is healthy."""
        ...

    def insert(self, collection: str, document: dict[str, Any]) -> str:
        """Insert a document, return document ID."""
        ...

    def find_one(self, collection: str, query: dict[str, Any]) -> dict[str, Any] | None:
        """Find a single document."""
        ...

    def find(self, collection: str, query: dict[str, Any], limit: int = 100) -> list[dict[str, Any]]:
        """Find documents matching query."""
        ...

    def update(self, collection: str, query: dict[str, Any], update: dict[str, Any]) -> int:
        """Update documents, return count updated."""
        ...

    def delete(self, collection: str, query: dict[str, Any]) -> int:
        """Delete documents, return count deleted."""
        ...
