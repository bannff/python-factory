"""Adversarial edge-case tests for wall.curator_bridge — B11/B13 QA."""

from pathlib import Path

from factory.curator.interface import CompatReport, CompatStatus, RomCandidate

from wall.curator_bridge import tile_from_report, wall_from_scan
from wall.fixtures import create_fixture_tree
from wall.models import GameTile


def _candidate(name: str = "test.sfc", subdir: str = "fake") -> RomCandidate:
    p = Path(f"/{subdir}/{name}")
    return RomCandidate(path=p, filename=name, extension=p.suffix.lower(), size_bytes=64)


# --- Edge 1: Same stem across systems must get UNIQUE ids ---


def test_same_stem_different_systems_get_unique_ids():
    r1 = CompatReport(candidate=_candidate("sf2.zip", "roms/arcade"), status=CompatStatus.OK, system="arcade")
    r2 = CompatReport(candidate=_candidate("sf2.sfc", "roms/snes"), status=CompatStatus.OK, system="snes")
    t1 = tile_from_report(r1)
    t2 = tile_from_report(r2)
    assert t1 is not None and t2 is not None
    assert t1.id != t2.id
    assert t1.id == "arcade-sf2" and t2.id == "snes-sf2"


def test_wall_from_scan_assigns_unique_ids(tmp_path: Path):
    rom_root = tmp_path / "roms"
    (rom_root / "arcade").mkdir(parents=True)
    (rom_root / "snes").mkdir(parents=True)
    cores_dir = tmp_path / "cores"
    cores_dir.mkdir()
    bios_dir = tmp_path / "bios"
    bios_dir.mkdir()
    (rom_root / "arcade" / "sf2.zip").write_bytes(b"\x00" * 64)
    (rom_root / "snes" / "sf2.sfc").write_bytes(b"\x00" * 64)
    (cores_dir / "mame2003_plus_libretro.so").write_bytes(b"\x00")
    (cores_dir / "snes9x_libretro.so").write_bytes(b"\x00")

    vm = wall_from_scan(rom_root, cores_dir, bios_dir)
    ids = [t.id for t in vm.tiles]
    assert len(ids) == 2
    assert len(set(ids)) == len(ids)


# --- Edge 2: Empty system on flagged tile ---


def test_flagged_tile_with_none_system():
    report = CompatReport(candidate=_candidate("mystery.gba"), status=CompatStatus.MISSING_CORE, system=None)
    tile = tile_from_report(report)
    assert tile is not None
    assert tile.system == ""
    assert tile.playable is False
    assert tile.status_detail == "MISSING_CORE"
    assert "\u26a0" not in tile.title


# --- Edge 3: Empty scan ---


def test_wall_from_scan_empty_dir(tmp_path: Path):
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    cores_dir = tmp_path / "cores"
    cores_dir.mkdir()
    bios_dir = tmp_path / "bios"
    bios_dir.mkdir()
    vm = wall_from_scan(rom_root, cores_dir, bios_dir)
    assert vm.tiles == []
    assert vm.columns == 3


# --- Edge 4: All flagged (no playable tiles) ---


def test_all_flagged_still_produces_tiles(tmp_path: Path):
    rom_root = tmp_path / "roms"
    rom_root.mkdir()
    cores_dir = tmp_path / "cores"
    cores_dir.mkdir()
    bios_dir = tmp_path / "bios"
    bios_dir.mkdir()
    (rom_root / "game1.sfc").write_bytes(b"\x00" * 64)
    (rom_root / "game2.z64").write_bytes(b"\x00" * 64)
    (rom_root / "game3.gba").write_bytes(b"\x00" * 64)

    vm = wall_from_scan(rom_root, cores_dir, bios_dir)
    assert len(vm.tiles) == 3
    assert all(not t.playable for t in vm.tiles)
    assert all("\u26a0" not in t.title for t in vm.tiles)


# --- Edge 5: Title prettify edge cases ---


def test_title_prettify_mixed_separators():
    report = CompatReport(
        candidate=_candidate("Final_Fantasy-VII.sfc"), status=CompatStatus.MISSING_CORE, system="snes"
    )
    tile = tile_from_report(report)
    assert tile is not None
    assert "Final Fantasy Vii" in tile.title
    assert "\u26a0" not in tile.title


def test_title_prettify_pure_number():
    report = CompatReport(candidate=_candidate("1942.zip"), status=CompatStatus.OK, system="arcade")
    tile = tile_from_report(report)
    assert tile is not None
    assert tile.title == "1942"


def test_title_prettify_already_capitalized():
    report = CompatReport(candidate=_candidate("StreetFighterII.sfc"), status=CompatStatus.OK, system="snes")
    tile = tile_from_report(report)
    assert tile is not None
    assert tile.title == "Streetfighterii"


# --- Edge 6: Fixture tree contract ---


def test_fixture_tree_contract(tmp_path: Path):
    rom, cores, bios = create_fixture_tree(tmp_path)
    vm = wall_from_scan(rom, cores, bios)
    ok = [t for t in vm.tiles if t.playable]
    flagged = [t for t in vm.tiles if not t.playable]
    assert len(ok) >= 2, f"Expected >=2 playable, got {len(ok)}: {[t.title for t in ok]}"
    assert len(flagged) >= 2, f"Expected >=2 non-playable, got {len(flagged)}: {[t.title for t in flagged]}"
    assert all("\u26a0" not in t.title for t in vm.tiles)
