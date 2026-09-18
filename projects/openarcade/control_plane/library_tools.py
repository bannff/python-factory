"""Library tools — list, search, get games.

register() wires these onto the passed FastMCP instance.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from wall.library_query import search_games as _search_games, get_game as _get_game
from wall.models import GameTile

from .context import ServerContext
from .serializers import tile_summary, tile_detail


def _is_curated(tile: GameTile) -> bool:
    """A tile is curated/playable iff it has cover art AND is playable (ROM resolved).

    This matches the wall's display filter: gamelist_source.load_gamelist with
    require_media=True keeps only tiles with a local cover file, and
    _resolve_rom_paths marks missing-ROM tiles as playable=False.
    See: wall/gamelist_source.py:89-96.
    """
    return bool(tile.art_url) and tile.playable


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register library tools (list_games, search_games, get_game, library_summary)."""
    tiles = context.tiles

    @mcp.tool()
    def list_games() -> list[dict[str, str | None]]:
        """List curated/playable games — only titles with cover art and a resolved ROM.

        This matches what the user sees on the game wall. Games without local
        cover art or without a playable ROM are excluded.
        """
        return [tile_summary(t) for t in tiles if _is_curated(t)]

    @mcp.tool()
    def search_games(query: str) -> list[dict[str, str | None]]:
        """Search curated games by title or system (case-insensitive substring)."""
        return [tile_summary(t) for t in _search_games(tiles, query) if _is_curated(t)]

    @mcp.tool()
    def get_game(game_id: str) -> dict[str, Any] | None:
        """Get full metadata for a single curated/playable game by its id.

        Returns None for unknown OR uncurated ids so the agent's view never
        leaks games the wall hides (grounding contract).
        """
        tile = _get_game(tiles, game_id)
        if tile is None or not _is_curated(tile):
            return None
        return tile_detail(tile)

    @mcp.tool()
    def library_summary() -> dict[str, Any]:
        """Grounded library summary: total curated game count, per-system counts, available systems.

        Returns only games the user can actually play (cover art + ROM present).
        """
        curated = [t for t in tiles if _is_curated(t)]
        system_counts = Counter(t.system for t in curated)
        return {
            "total_curated_games": len(curated),
            "systems": sorted(system_counts.keys()),
            "per_system": dict(sorted(system_counts.items())),
        }
