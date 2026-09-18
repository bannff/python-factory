"""Pure query functions for settings and systems derivation.

Shared by BOTH the MCP tools and the UI layer. No fastmcp, no flet imports.
Dependency direction: pure core <- tools; pure core <- ui.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from factory.arcade_config.interface import parse_cfg, resolve_runtime_settings

from wall.filters import derive_systems
from wall.models import GameTile


# ---------------------------------------------------------------------------
# Core resolution (DRY — used by settings_tools, launch_tools, controls_tools)
# ---------------------------------------------------------------------------


def resolve_core(system: str, media_root: Path) -> str:
    """Resolve the default emulator core for a system from emulators.cfg.

    Returns an empty string when the cfg is absent (no crash).
    """
    emu_path = media_root / "retroarch_cfg" / system.lower() / "emulators.cfg"
    if not emu_path.exists():
        return ""
    for line in emu_path.read_text(errors="replace").splitlines():
        if line.startswith("default"):
            parts = line.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip('"')
    return ""


# ---------------------------------------------------------------------------
# Global settings query
# ---------------------------------------------------------------------------


def get_global_settings(system: str, media_root: Path) -> dict[str, Any]:
    """Resolve RetroArch global runtime settings from layered cfgs.

    Returns a plain dict. If cfgs are absent, returns honest defaults (no crash).
    Same data the Settings screen renders.
    """
    cfg_root = media_root / "retroarch_cfg"
    global_cfg_path = cfg_root / "all" / "retroarch.cfg"

    global_cfg: dict[str, str] = {}
    if global_cfg_path.exists():
        global_cfg = parse_cfg(global_cfg_path.read_text(errors="replace"))

    system_key = system.lower()
    system_cfg: dict[str, str] = {}
    system_cfg_path = cfg_root / system_key / "retroarch.cfg"
    if system_cfg_path.exists():
        system_cfg = parse_cfg(system_cfg_path.read_text(errors="replace"))

    core = resolve_core(system, media_root)

    settings = resolve_runtime_settings(global_cfg, system_cfg, core=core)
    return {
        "core": settings.core,
        "run_ahead_enabled": settings.run_ahead_enabled,
        "run_ahead_frames": settings.run_ahead_frames,
        "shader_enabled": settings.shader_enabled,
        "shader_name": settings.shader_name,
        "video_smooth": settings.video_smooth,
    }


# ---------------------------------------------------------------------------
# Systems derivation
# ---------------------------------------------------------------------------


def list_systems(tiles: list[GameTile]) -> list[str]:
    """Sorted distinct systems present in the tile library.

    Delegates to the pure derive_systems (same source the Systems screen uses).
    """
    return derive_systems(tiles)
