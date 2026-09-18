"""Adapter registry for managing backend adapters."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AdapterType(str, Enum):
    """Types of backend adapters."""
    CACHE = "cache"
    GRAPH = "graph"
    DOCUMENT = "document"


class AdapterConfig(BaseModel):
    """Configuration for a backend adapter."""
    name: str = Field(..., description="Unique adapter name")
    adapter_type: AdapterType = Field(..., description="Type of adapter")
    backend: str = Field(..., description="Backend implementation (e.g., redis, neo4j)")
    connection_string: str | None = Field(None, description="Connection string")
    enabled: bool = Field(True, description="Whether adapter is enabled")
    options: dict[str, Any] = Field(default_factory=dict, description="Additional options")


class AdapterStats(BaseModel):
    """Statistics for a backend adapter."""
    name: str
    adapter_type: AdapterType
    connected: bool = True
    operations_count: int = 0
    error_count: int = 0
    last_operation_at: str | None = None
    last_error: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AdapterRegistry:
    """Registry for managing backend adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, AdapterConfig] = {}
        self._stats: dict[str, AdapterStats] = {}

    def register(self, config: AdapterConfig) -> None:
        """Register an adapter (idempotent — skips if already registered)."""
        if config.name in self._adapters:
            return
        self._adapters[config.name] = config
        self._stats[config.name] = AdapterStats(
            name=config.name,
            adapter_type=config.adapter_type,
        )

    def unregister(self, name: str) -> None:
        """Unregister an adapter."""
        self._adapters.pop(name, None)
        self._stats.pop(name, None)

    def get(self, name: str) -> AdapterConfig | None:
        """Get an adapter by name."""
        return self._adapters.get(name)

    def list_adapters(self) -> list[str]:
        """List all adapter names."""
        return list(self._adapters.keys())

    def list_by_type(self, adapter_type: AdapterType) -> list[str]:
        """List adapters by type."""
        return [
            name for name, config in self._adapters.items()
            if config.adapter_type == adapter_type
        ]

    def get_stats(self, name: str) -> AdapterStats | None:
        """Get stats for an adapter."""
        return self._stats.get(name)

    def record_operation(self, name: str) -> None:
        """Record an operation for an adapter."""
        if name in self._stats:
            self._stats[name].operations_count += 1
            self._stats[name].last_operation_at = datetime.now(timezone.utc).isoformat()

    def record_error(self, name: str, error: str) -> None:
        """Record an error for an adapter."""
        if name in self._stats:
            self._stats[name].error_count += 1
            self._stats[name].last_error = error

    def update_connection_status(self, name: str, connected: bool) -> None:
        """Update connection status for an adapter."""
        if name in self._stats:
            self._stats[name].connected = connected

    def to_dict(self) -> dict[str, Any]:
        """Convert registry to dict."""
        return {
            "adapters": [
                {
                    "name": config.name,
                    "type": config.adapter_type.value,
                    "backend": config.backend,
                    "enabled": config.enabled,
                    "connected": self._stats[config.name].connected if config.name in self._stats else False,
                }
                for config in self._adapters.values()
            ]
        }


# Global registry instance
_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    """Get the global adapter registry."""
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
