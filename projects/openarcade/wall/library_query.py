"""Pure library query functions. Zero Flet/fastmcp imports."""

from __future__ import annotations

from .models import GameTile


def search_games(tiles: list[GameTile], query: str) -> list[GameTile]:
    """Case-insensitive substring match on title OR system.

    Empty/whitespace query returns all tiles in original order.
    """
    q = query.strip().lower()
    if not q:
        return list(tiles)
    return [t for t in tiles if q in t.title.lower() or q in t.system.lower()]


def get_game(tiles: list[GameTile], game_id: str) -> GameTile | None:
    """Look up a single game by its id. Returns None if not found."""
    for t in tiles:
        if t.id == game_id:
            return t
    return None
