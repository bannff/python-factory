from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from factory.backend.runtime.models import Node, Edge

class GraphAdapter(ABC):
    """Abstract base class for graph database adapters."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the backend."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend is healthy."""
        pass

    @abstractmethod
    def add_node(self, label: str, properties: Dict[str, Any]) -> Node:
        """Create a new node."""
        pass

    @abstractmethod
    def add_edge(self, from_id: str, to_id: str, relationship_type: str, properties: Dict[str, Any]) -> Edge:
        """Create a new edge."""
        pass

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[Node]:
        """Retrieve a node by ID."""
        pass
    
    @abstractmethod
    def query(self, query: str) -> List[Any]:
        """Execute a raw query (backend-specific)."""
        pass
