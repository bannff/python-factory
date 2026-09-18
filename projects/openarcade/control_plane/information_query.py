"""Pure query functions for the Information shell screen.

Assembles ONLY honestly-sourced fields from existing data.
Shared by BOTH the MCP tool and the UI layer. No fastmcp, no flet imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wall.library_scan import SYSTEM_EXTENSIONS
from wall.models import GameTile

from .settings_query import list_systems, resolve_core


def get_system_info(
    tiles: list[GameTile],
    media_root: Path,
    system: str | None = None,
    *,
    default_system: str = "",
) -> dict[str, Any]:
    """Assemble honest system information from existing data.

    Only fields that can be truthfully derived from available sources.
    Never invents: core version, firmware, CPU/host probes, playtime, perf counters.

    Args:
        tiles: full tile library.
        media_root: root config/media path.
        system: system to report on (None -> default_system).
        default_system: fallback when system is None.
    """
    effective_system = system or default_system
    systems = list_systems(tiles)

    # Game count for the effective system
    system_tiles = [t for t in tiles if t.system.lower() == effective_system.lower()]
    game_count = len(system_tiles)

    # Resolved core
    core = resolve_core(effective_system, media_root)

    # Supported extensions
    extensions = sorted(SYSTEM_EXTENSIONS.get(effective_system.lower(), frozenset()))

    # Art coverage: tiles with non-empty art_url
    tiles_with_art = sum(1 for t in system_tiles if t.art_url)
    art_coverage = f"{tiles_with_art}/{game_count}" if game_count > 0 else "0/0"

    # Config provenance: which override layers exist on disk
    cfg_root = media_root / "retroarch_cfg"
    override_root = media_root / "retroarch_overrides"
    layers_present: list[str] = []
    global_cfg = cfg_root / "all" / "retroarch.cfg"
    if global_cfg.exists():
        layers_present.append("global")
    system_cfg = cfg_root / effective_system.lower() / "retroarch.cfg"
    if system_cfg.exists():
        layers_present.append("system")
    # Game-level: any file in overrides/<system>/
    game_override_dir = override_root / effective_system.lower()
    if game_override_dir.is_dir() and any(game_override_dir.iterdir()):
        layers_present.append("game")

    override_dir = str(override_root)

    # RetroArch version: attempt parse from global cfg header comment
    retroarch_version = _parse_retroarch_version(global_cfg)

    result: dict[str, Any] = {
        "system": effective_system,
        "systems": systems,
        "game_count": game_count,
        "core": core or "unknown",
        "supported_extensions": extensions,
        "art_coverage": art_coverage,
        "config_layers_present": layers_present,
        "override_dir": override_dir,
    }

    if retroarch_version:
        result["retroarch_version"] = retroarch_version

    return result


def _parse_retroarch_version(cfg_path: Path) -> str:
    """Try to extract RetroArch version from cfg header comment.

    RetroArch cfgs sometimes start with: # RetroArch 1.17.0
    Returns empty string if not parseable (honest omission).
    """
    if not cfg_path.exists():
        return ""
    try:
        with cfg_path.open(errors="replace") as f:
            for line in f:
                stripped = line.strip()
                if not stripped.startswith("#"):
                    break  # Only check leading comments
                lower = stripped.lower()
                if "retroarch" in lower:
                    # Try to extract version after "retroarch"
                    parts = stripped.split()
                    for i, part in enumerate(parts):
                        if part.lower() == "retroarch" and i + 1 < len(parts):
                            candidate = parts[i + 1].strip("v").strip(",")
                            # Basic version check: starts with digit
                            if candidate and candidate[0].isdigit():
                                return candidate
    except OSError:
        pass
    return ""
