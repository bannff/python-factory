from abc import ABC, abstractmethod
from typing import Any, Optional

class CacheAdapter(ABC):
    """Abstract base class for cache adapters."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the backend."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the backend is healthy."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set a key-value pair with optional TTL."""
        pass

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value by key."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key."""
        pass
