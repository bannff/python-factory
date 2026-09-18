"""Deterministic (read-only) MCP tools for backend module.

These are contract tools that expose capabilities, health, and schema.
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

from factory.mcp_utils.interface import deterministic

if TYPE_CHECKING:
    from ..runtime.registry import AdapterRegistry
    from ..runtime.runtime import BackendRuntime


def register(
    mcp: Any,
    get_runtime: Callable[[], "BackendRuntime"],
    get_registry: Callable[[], "AdapterRegistry"],
    is_authoring_enabled: Callable[[], bool],
) -> None:
    """Register deterministic tools with the MCP server."""
    from ..runtime.registry import AdapterConfig, AdapterType

    @mcp.tool()
    @deterministic
    def get_capabilities() -> dict[str, Any]:
        """Get backend module capabilities."""
        return {
            "schema_version": "1.0.0",
            "supported_backends": {
                "cache": ["memory", "redis"],
                "graph": ["networkx", "neo4j"],
                "document": ["tinydb"],
            },
            "authoring_enabled": is_authoring_enabled(),
            "feature_flags": {
                "health_checks": True,
                "connection_tests": True,
                "stats_tracking": True,
            },
        }

    @mcp.tool()
    @deterministic
    def health_check() -> dict[str, Any]:
        """Check health of all backend adapters."""
        from ..runtime.health import HealthChecker

        # Ensure default adapters are registered before reporting health.
        get_runtime()
        return HealthChecker(get_registry()).overall_health()

    @mcp.tool()
    @deterministic
    def describe_config_schema() -> dict[str, Any]:
        """Get JSON schema for backend configuration."""
        return {
            "adapter_config": AdapterConfig.model_json_schema(),
            "adapter_types": [t.value for t in AdapterType],
        }

    @mcp.tool()
    @deterministic
    def get_adapter_registry() -> dict[str, Any]:
        """Get the adapter registry."""
        return get_registry().to_dict()
