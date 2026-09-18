"""Pure filtering and derivation for the game library. No I/O, no exceptions."""

from __future__ import annotations

from .models import GameTile


def filter_tiles(
    tiles: list[GameTile],
    *,
    system: str | None = None,
    letter: str | None = None,
    query: str | None = None,
) -> list[GameTile]:
    """Apply each non-None filter sequentially (intersection). Pure."""
    result = tiles
    if system is not None:
        result = [t for t in result if t.system == system]
    if letter is not None:
        up = letter.upper()
        result = [t for t in result if t.title and t.title[0].upper() == up]
    if query is not None:
        q = query.lower()
        result = [t for t in result if q in t.title.lower()]
    return result


def derive_systems(tiles: list[GameTile]) -> list[str]:
    """Sorted distinct systems present in tiles."""
    return sorted({t.system for t in tiles})


def derive_letters(tiles: list[GameTile]) -> list[str]:
    """Sorted distinct uppercased first letters of tile titles."""
    return sorted({t.title[0].upper() for t in tiles if t.title})
