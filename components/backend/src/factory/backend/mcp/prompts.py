"""MCP prompts for backend module."""

from __future__ import annotations

from typing import Any


def register(mcp: Any) -> None:
    """Register backend prompts."""

    @mcp.prompt()
    def backend_setup_adapter(
        adapter_name: str = "my-adapter",
        adapter_type: str = "cache",
        backend: str = "memory",
    ) -> str:
        """Guide for setting up a new backend adapter."""
        return f"""Help me set up a new backend adapter.

Adapter Name: {adapter_name}
Type: {adapter_type}
Backend: {backend}

Please guide me through:
1. Required configuration for {backend} backend
2. How to register the adapter
3. Testing the connection
4. Best practices for this adapter type

Use the backend MCP tools to complete the setup."""

    @mcp.prompt()
    def backend_cache_workflow(
        adapter_name: str = "default-cache",
    ) -> str:
        """Guide for cache operations workflow."""
        return f"""Help me work with the cache adapter: {adapter_name}

Please demonstrate:
1. Setting a value with TTL
2. Getting a value
3. Checking cache health
4. Best practices for cache key naming

Use cache_get and cache_set tools."""

    @mcp.prompt()
    def backend_graph_workflow(
        adapter_name: str = "default-graph",
    ) -> str:
        """Guide for graph operations workflow."""
        return f"""Help me work with the graph adapter: {adapter_name}

Please demonstrate:
1. Adding nodes with properties
2. Creating relationships
3. Querying the graph
4. Graph modeling best practices

Use graph_add_node and related tools."""

    @mcp.prompt()
    def backend_health_check() -> str:
        """Guide for checking backend health."""
        return """Help me check the health of all backend adapters.

Please:
1. Run health_check to get overall status
2. Identify any unhealthy adapters
3. Check adapter statistics
4. Suggest remediation for any issues

Start with the health_check tool."""

    @mcp.prompt()
    def backend_troubleshoot() -> str:
        """Guide for troubleshooting backend issues."""
        return """Help me troubleshoot backend adapter issues.

Please:
1. Check overall health status
2. Review adapter registry
3. Identify connection issues
4. Check error counts in statistics
5. Suggest fixes

Start with health_check and get_adapter_registry."""

    @mcp.prompt()
    def backend_migrate_adapter(
        from_backend: str = "memory",
        to_backend: str = "redis",
    ) -> str:
        """Guide for migrating between backend implementations."""
        return f"""Help me migrate from {from_backend} to {to_backend}.

Please guide me through:
1. Setting up the new {to_backend} adapter
2. Data migration strategy
3. Testing the new adapter
4. Switching over with minimal downtime
5. Cleanup of old adapter

Use backend authoring tools (requires BACKEND_ENABLE_AUTHORING_TOOLS=1)."""
