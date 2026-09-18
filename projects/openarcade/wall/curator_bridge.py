"""Bridge: curator compat reports -> wall view-model."""

from pathlib import Path

from factory.curator.interface import CompatReport, CompatStatus, check_compatibility, scan_rom_directory

from .art_resolver import box_art_url
from .models import GameTile, WallViewModel

# Interim dev art-name data; the Phase-3 scraper replaces this by populating
# GameTile.art_name at scan time (same as description/year/etc.). Keyed by
# normalized title. Region tags vary per title and cannot be derived from the stem.
_ART_NAMES: dict[str, str] = {
    "street fighter ii": "Street Fighter II (USA)",
    "mortal kombat": "Mortal Kombat (USA)",
    "killer instinct": "Killer Instinct (USA)",
    "metroid fusion": "Metroid Fusion (USA)",
    "goldeneye 007": "GoldenEye 007 (USA)",
    "super mario bros": "Super Mario Bros. (World)",
}


def tile_from_report(report: CompatReport) -> GameTile | None:
    """Map a compat report -> GameTile, or None to skip. Pure."""
    if report.status == CompatStatus.UNKNOWN_SYSTEM:
        return None
    stem = report.candidate.path.stem
    title = stem.replace("_", " ").replace("-", " ").title()
    system = (report.system or "").upper()
    playable = report.status == CompatStatus.OK
    art_name = _ART_NAMES.get(title.lower())
    return GameTile(
        id=f"{(report.system or 'unknown')}-{stem}".lower(),
        title=title,
        system=system,
        art_url=box_art_url(system, art_name),
        art_name=art_name,
        playable=playable,
        status_detail=None if playable else report.status.value,
        rom_path=str(report.candidate.path),
        core=report.core_hint,
    )


def wall_from_scan(rom_root: Path, cores_dir: Path, bios_dir: Path, *, columns: int = 3) -> WallViewModel:
    """Scan rom_root via curator and produce a WallViewModel."""
    tiles: list[GameTile] = []
    for cand in scan_rom_directory(rom_root):
        t = tile_from_report(check_compatibility(cand, cores_dir, bios_dir))
        if t is not None:
            tiles.append(t)
    return WallViewModel(tiles=tiles, columns=columns)
