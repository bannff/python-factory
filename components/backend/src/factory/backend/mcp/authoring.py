"""Authoring (security-gated) MCP tools for backend module.

These tools manage adapter configuration and registration.
"""

from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

from factory.mcp_utils.interface import authoring

if TYPE_CHECKING:
    from ..authoring import BackendAuthoring


def register(mcp: Any, get_authoring: Callable[[], "BackendAuthoring"]) -> None:
    """Register authoring tools with the MCP server."""
    from ..runtime.registry import AdapterConfig, AdapterType

    @mcp.tool()
    @authoring
    def backend_authoring_get_status() -> dict[str, Any]:
        """Get authoring tools status."""
        return get_authoring().get_status()

    @mcp.tool()
    @authoring
    def backend_authoring_register_adapter(
        name: str,
        adapter_type: str,
        backend: str,
        connection_string: str | None = None,
        enabled: bool = True,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a new adapter."""
        try:
            config = AdapterConfig(
                name=name,
                adapter_type=AdapterType(adapter_type),
                backend=backend,
                connection_string=connection_string,
                enabled=enabled,
                options=options or {},
            )
            return get_authoring().register_adapter(config)
        except Exception as e:
            return {"error": str(e)}
