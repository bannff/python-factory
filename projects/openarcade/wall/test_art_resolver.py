"""Tests for wall.art_resolver -- pure URL formatter."""

from wall.art_resolver import box_art_url


def test_known_system_and_name_produces_correct_url():
    url = box_art_url("SNES", "Street Fighter II (USA)")
    assert url == (
        "https://thumbnails.libretro.com/"
        "Nintendo%20-%20Super%20Nintendo%20Entertainment%20System/"
        "Named_Boxarts/Street%20Fighter%20II%20%28USA%29.png"
    )


def test_n64_system_uses_correct_folder():
    url = box_art_url("N64", "GoldenEye 007 (USA)")
    assert "Nintendo%20-%20Nintendo%2064/Named_Boxarts/GoldenEye%20007%20%28USA%29.png" in url


def test_unknown_system_returns_empty():
    assert box_art_url("DREAMCAST", "Sonic Adventure (USA)") == ""


def test_none_art_name_returns_empty():
    assert box_art_url("SNES", None) == ""


def test_empty_art_name_returns_empty():
    assert box_art_url("SNES", "") == ""


def test_case_insensitive_system_lookup():
    url = box_art_url("snes", "Mortal Kombat (USA)")
    assert "Nintendo%20-%20Super%20Nintendo%20Entertainment%20System" in url


def test_mame_system_folder():
    url = box_art_url("MAME", "Street Fighter II (World)")
    assert url.startswith("https://thumbnails.libretro.com/MAME/Named_Boxarts/")


# --- Bridge-level integration: art_name -> art_url on GameTile ---

from pathlib import Path
from unittest.mock import MagicMock

from wall.curator_bridge import tile_from_report


def _report(name: str, system: str = "snes"):
    """Minimal CompatReport stub for testing tile art resolution."""
    from factory.curator.interface import CompatReport, CompatStatus, RomCandidate

    cand = RomCandidate(path=Path(f"/roms/{name}.sfc"), filename=f"{name}.sfc", extension=".sfc", size_bytes=64)
    return CompatReport(candidate=cand, status=CompatStatus.OK, system=system)


def test_bridge_showcase_game_gets_art_url():
    tile = tile_from_report(_report("street_fighter_ii"))
    assert tile is not None
    assert "Nintendo%20-%20Super%20Nintendo%20Entertainment%20System" in tile.art_url
    assert "Street%20Fighter%20II%20%28USA%29" in tile.art_url
    assert tile.art_name == "Street Fighter II (USA)"


def test_bridge_unknown_game_gets_empty_art_url():
    tile = tile_from_report(_report("random_unknown_game"))
    assert tile is not None
    assert tile.art_url == ""
    assert tile.art_name is None
