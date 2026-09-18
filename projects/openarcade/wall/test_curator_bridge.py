"""Tests for wall.curator_bridge — B11/B13."""

from pathlib import Path

from factory.curator.interface import CompatReport, CompatStatus, RomCandidate

from wall.curator_bridge import tile_from_report, wall_from_scan
from wall.fixtures import create_fixture_tree
from wall.models import GameTile


def _candidate(name: str = "test_rom.sfc") -> RomCandidate:
    p = Path(f"/fake/{name}")
    return RomCandidate(path=p, filename=name, extension=p.suffix.lower(), size_bytes=64)


def test_tile_from_ok_report_has_clean_title():
    report = CompatReport(candidate=_candidate("donkey_kong_country.sfc"), status=CompatStatus.OK, system="snes")
    tile = tile_from_report(report)
    assert tile is not None
    assert tile.title == "Donkey Kong Country"
    assert tile.system == "SNES"
    assert "\u26a0" not in tile.title
    assert tile.playable is True
    assert tile.status_detail is None


def test_tile_from_missing_core_report_is_not_playable():
    report = CompatReport(candidate=_candidate("goldeneye.z64"), status=CompatStatus.MISSING_CORE, system="n64")
    tile = tile_from_report(report)
    assert tile is not None
    assert tile.playable is False
    assert tile.status_detail == "MISSING_CORE"
    assert "\u26a0" not in tile.title
    # Title is clean
    assert tile.title == "Goldeneye"


def test_tile_from_unknown_system_is_skipped():
    report = CompatReport(candidate=_candidate("mystery.xyz"), status=CompatStatus.UNKNOWN_SYSTEM, system=None)
    assert tile_from_report(report) is None


def test_wall_from_scan_over_fixture(tmp_path: Path):
    rom, cores, bios = create_fixture_tree(tmp_path)
    vm = wall_from_scan(rom, cores, bios, columns=5)
    assert vm.columns == 5
    ok_tiles = [t for t in vm.tiles if t.playable]
    flagged_tiles = [t for t in vm.tiles if not t.playable]
    assert len(ok_tiles) >= 1, f"Expected >=1 playable tile, got {ok_tiles}"
    assert len(flagged_tiles) >= 1, f"Expected >=1 non-playable tile, got {flagged_tiles}"
    # No ⚠ anywhere
    assert all("\u26a0" not in t.title for t in vm.tiles)
