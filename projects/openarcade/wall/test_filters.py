"""Tests for wall.filters — pure filtering logic."""

from wall.filters import filter_tiles, derive_systems, derive_letters
from wall.models import GameTile


def _t(title: str, system: str = "SNES") -> GameTile:
    return GameTile(id=f"{system}-{title}", title=title, system=system, art_url="")


_TILES = [
    _t("Street Fighter II", "SNES"),
    _t("Mortal Kombat", "SNES"),
    _t("Killer Instinct", "N64"),
    _t("Sonic", "Genesis"),
    _t("Super Mario World", "SNES"),
]


def test_filter_by_system_exact_match():
    result = filter_tiles(_TILES, system="N64")
    assert result == [_TILES[2]]


def test_filter_by_system_returns_empty_on_mismatch():
    assert filter_tiles(_TILES, system="GBA") == []


def test_filter_by_letter():
    result = filter_tiles(_TILES, letter="S")
    titles = [t.title for t in result]
    assert titles == ["Street Fighter II", "Sonic", "Super Mario World"]


def test_filter_by_letter_case_insensitive():
    assert filter_tiles(_TILES, letter="k") == [_TILES[2]]


def test_filter_by_query_case_insensitive_substring():
    result = filter_tiles(_TILES, query="kombat")
    assert result == [_TILES[1]]


def test_filter_combined_system_and_letter_intersection():
    result = filter_tiles(_TILES, system="SNES", letter="S")
    titles = [t.title for t in result]
    assert titles == ["Street Fighter II", "Super Mario World"]


def test_filter_empty_input_returns_empty():
    assert filter_tiles([], system="SNES", letter="A", query="x") == []


def test_filter_no_filters_returns_all():
    assert filter_tiles(_TILES) == _TILES


def test_derive_systems_sorted_distinct():
    result = derive_systems(_TILES)
    assert result == ["Genesis", "N64", "SNES"]


def test_derive_letters_sorted_unique_uppercased():
    result = derive_letters(_TILES)
    assert result == ["K", "M", "S"]
