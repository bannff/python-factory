"""Library Manager tools — scan_directory, import_games.

register() wires these onto the passed FastMCP instance.
Pure core shared by UI + assistant; no UI/Flet imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wall.library_scan import scan_directory as _scan_directory
from wall.library_import import write_gamelist
from wall.library_scan import RomCandidate

from .context import ServerContext


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register library manager tools (scan_directory, import_games)."""
    tiles = context.tiles
    system = context.system
    media_root = context.media_root

    # Pre-compute existing tile sets for classification
    _existing_ids = frozenset(t.id for t in tiles)
    _existing_art_ids = frozenset(t.id for t in tiles if t.art_url)

    @mcp.tool()
    def scan_directory(path: str) -> dict[str, Any]:
        """Scan a directory for ROMs (preview only — no writes).

        Classifies each ROM as matched (gamelist+art), metadata_only
        (gamelist, no art), or unmatched (new ROM).
        Returns summary counts and candidate list.
        """
        dir_path = Path(path)
        if not dir_path.is_dir():
            return {"error": f"Not a directory: {path}"}

        result = _scan_directory(
            dir_path,
            system=system,
            existing_ids=_existing_ids,
            existing_art_ids=_existing_art_ids,
        )

        return {
            "system": result.system,
            "total": len(result.candidates),
            "matched": result.matched,
            "metadata_only": result.metadata_only,
            "unmatched": result.unmatched,
            "candidates": [
                {
                    "id": c.id,
                    "title": c.title,
                    "rom_path": c.rom_path,
                    "status": c.status,
                }
                for c in result.candidates
            ],
        }

    @mcp.tool()
    def import_games(path: str, target_system: str | None = None) -> dict[str, Any]:
        """Scan a directory for ROMs and import new ones into the gamelist.

        Writes only genuinely new entries (no-clobber merge).
        Returns count of imported games and the gamelist path written.
        """
        dir_path = Path(path)
        if not dir_path.is_dir():
            return {"error": f"Not a directory: {path}"}

        effective_system = target_system or system

        result = _scan_directory(
            dir_path,
            system=effective_system,
            existing_ids=_existing_ids,
            existing_art_ids=_existing_art_ids,
        )

        # Only import unmatched and metadata_only (new ROMs)
        new_candidates = [c for c in result.candidates if c.status == "unmatched"]
        if not new_candidates:
            return {
                "imported_count": 0,
                "message": "No new ROMs to import — all already in gamelist.",
                "system": effective_system,
            }

        gamelist_path = media_root / "gamelists" / effective_system / "gamelist.xml"
        count = write_gamelist(new_candidates, gamelist_path, merge=True)

        return {
            "imported_count": count,
            "gamelist_path": str(gamelist_path),
            "system": effective_system,
        }
