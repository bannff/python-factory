"""Fixture ROM tree for dev/testing. Creates real file structure curator can scan."""

from pathlib import Path


def create_fixture_tree(base: Path) -> tuple[Path, Path, Path]:
    """Build a ROM tree + cores_dir + bios_dir under base.

    Returns (rom_root, cores_dir, bios_dir).
    Guarantees: >=3 OK tiles (showcase covers) and >=1 MISSING_CORE tile.
    """
    rom_root = base / "roms"
    cores_dir = base / "cores"
    bios_dir = base / "bios"
    rom_root.mkdir(parents=True)
    cores_dir.mkdir()
    bios_dir.mkdir()

    # OK: SNES showcase — street_fighter_ii, mortal_kombat, killer_instinct
    (rom_root / "street_fighter_ii.sfc").write_bytes(b"\x00" * 64)
    (rom_root / "mortal_kombat.sfc").write_bytes(b"\x00" * 64)
    (rom_root / "killer_instinct.sfc").write_bytes(b"\x00" * 64)
    (cores_dir / "snes9x_libretro.so").write_bytes(b"\x00")

    # OK: GBA — core mgba present, bios present
    (rom_root / "metroid-fusion.gba").write_bytes(b"\x00" * 64)
    (cores_dir / "mgba_libretro.so").write_bytes(b"\x00")
    (bios_dir / "gba_bios.bin").write_bytes(b"\x00" * 16)

    # MISSING_CORE: N64 — no mupen64plus_next core file
    (rom_root / "goldeneye_007.z64").write_bytes(b"\x00" * 64)

    # MISSING_CORE: NES — no mesen core file
    (rom_root / "super_mario_bros.nes").write_bytes(b"\x00" * 64)

    return rom_root, cores_dir, bios_dir
