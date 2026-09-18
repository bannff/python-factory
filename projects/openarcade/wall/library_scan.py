"""Library scanner — PURE ROM classification. IO lives at the edge (callers walk dirs)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Per-system ROM extension table. Lowercase, includes .zip (common compressed ROM).
SYSTEM_EXTENSIONS: dict[str, frozenset[str]] = {
    "snes": frozenset({".sfc", ".smc", ".zip"}),
    "nes": frozenset({".nes", ".zip"}),
    "n64": frozenset({".z64", ".n64", ".v64", ".zip"}),
    "gba": frozenset({".gba", ".zip"}),
    "gbc": frozenset({".gbc", ".zip"}),
    "gb": frozenset({".gb", ".zip"}),
    "genesis": frozenset({".md", ".bin", ".gen", ".zip"}),
    "megadrive": frozenset({".md", ".bin", ".gen", ".zip"}),
    "psx": frozenset({".chd", ".cue", ".bin", ".zip"}),
    "arcade": frozenset({".zip", ".chd"}),
    "mame": frozenset({".zip", ".chd"}),
    "pce": frozenset({".pce", ".zip"}),
    "segacd": frozenset({".chd", ".cue", ".bin"}),
    "saturn": frozenset({".chd", ".cue", ".bin"}),
    "gc": frozenset({".iso", ".gcm", ".chd"}),
    "wii": frozenset({".iso", ".wbfs", ".chd"}),
    "nds": frozenset({".nds", ".zip"}),
    "psp": frozenset({".iso", ".cso", ".chd"}),
}


@dataclass(frozen=True)
class RomCandidate:
    """A ROM file found during scan."""

    id: str  # f"{system}-{stem}".lower()
    title: str  # stem (filename without extension)
    system: str  # normalized lowercase
    rom_path: str  # RELATIVE (e.g. ./filename.ext) -- gamelist convention
    status: str  # "matched" | "metadata_only" | "unmatched"


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning a directory for ROMs."""

    system: str
    candidates: list[RomCandidate]
    matched: int
    metadata_only: int
    unmatched: int


def classify_files(
    filenames: list[str],
    *,
    system: str,
) -> list[RomCandidate]:
    """PURE: classify a flat list of filenames by system extension table.

    filenames: just the basename (e.g. "game.sfc"), NOT full paths.
    Returns RomCandidate list with relative paths (./filename).
    Deduplicates by rom_path (first occurrence wins).
    """
    extensions = SYSTEM_EXTENSIONS.get(system.lower())
    if extensions is None:
        return []

    seen: set[str] = set()
    candidates: list[RomCandidate] = []
    for name in sorted(filenames):
        p = Path(name)
        if p.suffix.lower() not in extensions:
            continue
        rel_path = f"./{p.name}"
        if rel_path in seen:
            continue
        seen.add(rel_path)
        stem = p.stem
        candidates.append(RomCandidate(
            id=f"{system.lower()}-{stem}".lower(),
            title=stem,
            system=system.lower(),
            rom_path=rel_path,
            status="unmatched",  # default; upgraded by build_gamelist_entries
        ))
    return candidates


def build_gamelist_entries(
    candidates: list[RomCandidate],
    *,
    existing_ids: frozenset[str] | None = None,
    existing_art_ids: frozenset[str] | None = None,
) -> list[RomCandidate]:
    """PURE: classify candidates against existing library state.

    existing_ids: set of GameTile.id values already in gamelist (have metadata).
    existing_art_ids: subset of existing_ids that also have local cover art.

    Returns new list with status upgraded:
      - "matched": in gamelist AND has local art
      - "metadata_only": in gamelist but no local art
      - "unmatched": not in gamelist at all (new ROM)
    """
    _existing_ids = existing_ids or frozenset()
    _existing_art = existing_art_ids or frozenset()
    result: list[RomCandidate] = []
    for c in candidates:
        if c.id in _existing_art:
            status = "matched"
        elif c.id in _existing_ids:
            status = "metadata_only"
        else:
            status = "unmatched"
        result.append(RomCandidate(
            id=c.id,
            title=c.title,
            system=c.system,
            rom_path=c.rom_path,
            status=status,
        ))
    return result


def scan_directory(
    directory: Path,
    *,
    system: str,
    existing_ids: frozenset[str] | None = None,
    existing_art_ids: frozenset[str] | None = None,
) -> ScanResult:
    """IO EDGE: walk directory, classify contents against existing library.

    Reads filenames from dir (single-level, no recursion).
    Pure classification delegated to classify_files + build_gamelist_entries.
    """
    if not directory.is_dir():
        return ScanResult(system=system, candidates=[], matched=0, metadata_only=0, unmatched=0)

    filenames = [f.name for f in directory.iterdir() if f.is_file()]
    raw = classify_files(filenames, system=system)
    classified = build_gamelist_entries(
        raw, existing_ids=existing_ids, existing_art_ids=existing_art_ids,
    )

    matched = sum(1 for c in classified if c.status == "matched")
    metadata_only = sum(1 for c in classified if c.status == "metadata_only")
    unmatched = sum(1 for c in classified if c.status == "unmatched")

    return ScanResult(
        system=system,
        candidates=classified,
        matched=matched,
        metadata_only=metadata_only,
        unmatched=unmatched,
    )
