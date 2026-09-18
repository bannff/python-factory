"""Backward-compatible memory cache adapter.

Delegates to ``factory.cache`` brick's MemoryCacheStore.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import CacheAdapter


class MemoryAdapter(CacheAdapter):
    """In-memory cache adapter — delegates to cache brick."""

    def __init__(self) -> None:
        from factory.cache.runtime.adapters.memory_adapter import MemoryCacheStore
        self._delegate = MemoryCacheStore()

    def connect(self) -> None:
        pass  # in-memory, nothing to connect

    def health_check(self) -> bool:
        h = self._delegate.health_check()
        return h.healthy

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        return self._delegate.set(key, value, ttl)

    def get(self, key: str) -> Optional[Any]:
        return self._delegate.get(key)

    def delete(self, key: str) -> bool:
        return self._delegate.delete(key)


# Backwards-compatible name used by the runtime.
class MemoryCacheAdapter(MemoryAdapter):
    pass
