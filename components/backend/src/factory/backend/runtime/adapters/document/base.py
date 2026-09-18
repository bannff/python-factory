from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from factory.backend.runtime.models import Document

class DocumentAdapter(ABC):
    """Abstract base class for document database adapters."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the backend."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend is healthy."""
        pass

    @abstractmethod
    def upsert(self, collection: str, document_id: str, data: Dict[str, Any]) -> Document:
        """Create or update a document."""
        pass

    @abstractmethod
    def get(self, collection: str, document_id: str) -> Optional[Document]:
        """Retrieve a document by ID."""
        pass

    @abstractmethod
    def find(self, collection: str, query: Dict[str, Any]) -> List[Document]:
        """Find documents matching a query."""
        pass
    
    @abstractmethod
    def delete(self, collection: str, document_id: str) -> bool:
        """Delete a document."""
        pass
