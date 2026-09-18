"""Tests for curation art resolution + enrichment (no network — injected fake)."""

from __future__ import annotations

from pathlib import Path

from wall.art_curator import art_url, art_urls_in_preference, ART_PREFERENCE
from wall.models import GameTile
from control_plane.curation_tools import enrich_tiles_art


def _tile(title, art_url_rel):
    return GameTile(
        id=f"snes-{title}", title=title, system="SNES",
        art_url=art_url_rel, rom_path="", playable=True,
    )


# --- art_curator URL building ---

def test_art_url_maps_kind_to_libretro_folder():
    assert "Named_Titles" in art_url("SNES", "Killer Instinct (USA)", "title")
    assert "Named_Snaps" in art_url("SNES", "Killer Instinct (USA)", "snap")
    assert "Named_Boxarts" in art_url("SNES", "Killer Instinct (USA)", "boxart")


def test_art_url_unknown_system_or_kind_is_empty():
    assert art_url("DREAMCAST", "Foo", "title") == ""
    assert art_url("SNES", "Foo", "bogus") == ""
    assert art_url("SNES", "", "title") == ""


def test_preference_order_is_title_first():
    kinds = [k for k, _ in art_urls_in_preference("SNES", "Foo (USA)")]
    assert kinds == list(ART_PREFERENCE) == ["title", "snap", "boxart"]


# --- enrich_tiles_art (injected downloader) ---

class _FakeDownloader:
    """Returns bytes only for URLs containing one of `serve` substrings."""
    def __init__(self, serve):
        self.serve = serve
        self.calls: list[str] = []

    def get(self, url):
        self.calls.append(url)
        return b"PNGDATA" if any(s in url for s in self.serve) else None


def test_enrich_writes_preferred_title_art(tmp_path: Path):
    tiles = [_tile("Killer Instinct", "snes/boxart/Killer Instinct (USA).png")]
    dl = _FakeDownloader(serve=["Named_Titles"])  # title available
    res = enrich_tiles_art(tiles, tmp_path, "SNES", downloader=dl)
    assert res["curated"] == 1 and res["by_kind"] == {"title": 1}
    assert (tmp_path / "snes/boxart/Killer Instinct (USA).png").read_bytes() == b"PNGDATA"


def test_enrich_falls_back_to_snap_then_boxart(tmp_path: Path):
    tiles = [_tile("Foo", "snes/boxart/Foo (USA).png")]
    dl = _FakeDownloader(serve=["Named_Snaps"])  # title 404, snap ok
    res = enrich_tiles_art(tiles, tmp_path, "SNES", downloader=dl)
    assert res["by_kind"] == {"snap": 1}


def test_enrich_skips_when_no_art_available(tmp_path: Path):
    tiles = [_tile("Foo", "snes/boxart/Foo (USA).png")]
    dl = _FakeDownloader(serve=[])  # nothing resolves
    res = enrich_tiles_art(tiles, tmp_path, "SNES", downloader=dl)
    assert res["curated"] == 0 and res["skipped"] == 1
    assert not (tmp_path / "snes/boxart/Foo (USA).png").exists()  # never faked
