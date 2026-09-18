"""Systems tools — list_systems.

register() wires these onto the passed FastMCP instance.
"""

from __future__ import annotations

from typing import Any

from .context import ServerContext
from .settings_query import list_systems as _list_systems


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register systems tools (list_systems)."""
    tiles = context.tiles

    @mcp.tool()
    def list_systems() -> list[str]:
        """List sorted distinct game systems present in the library."""
        return _list_systems(tiles)
