"""Information tools — get_system_info.

register() wires onto the passed FastMCP instance (cerv6 pattern).
Pure core shared by UI + assistant; no UI/Flet imports.
"""

from __future__ import annotations

from typing import Any

from .context import ServerContext
from .information_query import get_system_info as _get_system_info


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register the information tool (get_system_info)."""

    @mcp.tool()
    def get_system_info(system: str | None = None) -> dict[str, Any]:
        """Get honest system information: game count, core, extensions, art coverage, config layers.

        Only returns fields that can be truthfully derived from existing data.
        Omits anything unsourceable (no fake surfaces).

        Args:
            system: System to query (e.g. "snes"). Defaults to the server's configured system.
        """
        return _get_system_info(
            tiles=context.tiles,
            media_root=context.media_root,
            system=system,
            default_system=context.system,
        )
