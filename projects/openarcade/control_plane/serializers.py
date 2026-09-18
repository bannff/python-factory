"""Pure serializers used by multiple tool modules. Zero IO."""

from __future__ import annotations

from typing import Any

from wall.models import GameTile


def tile_summary(tile: GameTile) -> dict[str, str | None]:
    """Minimal dict for list/search responses."""
    return {
        "id": tile.id,
        "title": tile.title,
        "system": tile.system,
        "genre": tile.genre,
        "release_date": tile.release_date,
    }


def tile_detail(tile: GameTile) -> dict[str, Any]:
    """Full metadata dict for get_game responses."""
    return {
        "id": tile.id,
        "title": tile.title,
        "system": tile.system,
        "genre": tile.genre,
        "release_date": tile.release_date,
        "players": tile.players,
        "developer": tile.developer,
        "publisher": tile.publisher,
        "description": tile.description,
        "rating": tile.rating,
        "video_url": tile.video_url or None,
        "art_url": tile.art_url or None,
        "rom_path": tile.rom_path,
    }
