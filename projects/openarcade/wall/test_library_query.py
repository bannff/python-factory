"""Behavior tests for library_query — pure core, no IO."""

from wall.models import GameTile
from wall.library_query import search_games, get_game


def _tile(id: str, title: str, system: str = "SNES") -> GameTile:
    return GameTile(id=id, title=title, system=system, art_url="")


_TILES = [
    _tile("snes-baseball", "Super Baseball 2020", "SNES"),
    _tile("snes-mario", "Super Mario World", "SNES"),
    _tile("nes-mario", "Super Mario Bros", "NES"),
    _tile("arcade-sf2", "Street Fighter II", "ARCADE"),
]


class TestSearchGames:
    def test_title_substring_case_insensitive(self):
        # Arrange / Act
        result = search_games(_TILES, "baseball")
        # Assert
        assert len(result) == 1
        assert result[0].id == "snes-baseball"

    def test_system_match(self):
        # Arrange / Act
        result = search_games(_TILES, "nes")
        # Assert — matches SNES and NES (both contain "nes")
        ids = {t.id for t in result}
        assert "snes-baseball" in ids
        assert "snes-mario" in ids
        assert "nes-mario" in ids

    def test_empty_query_returns_all(self):
        # Arrange / Act
        result = search_games(_TILES, "")
        # Assert
        assert len(result) == len(_TILES)

    def test_whitespace_query_returns_all(self):
        result = search_games(_TILES, "   ")
        assert len(result) == len(_TILES)


class TestGetGame:
    def test_hit(self):
        # Arrange / Act
        result = get_game(_TILES, "arcade-sf2")
        # Assert
        assert result is not None
        assert result.title == "Street Fighter II"

    def test_miss(self):
        # Arrange / Act
        result = get_game(_TILES, "nonexistent-id")
        # Assert
        assert result is None
