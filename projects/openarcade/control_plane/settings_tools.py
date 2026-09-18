"""Settings tools — get_global_settings, set_setting, get_controls, set_runahead.

register() wires these onto the passed FastMCP instance.
"""

from __future__ import annotations

from typing import Any

from wall.config_service import save_runahead, save_global_overrides

from .context import ServerContext
from .settings_query import get_global_settings as _get_global_settings, resolve_core


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register settings tools (get_global_settings, set_setting, get_controls, set_runahead)."""
    system = context.system
    media_root = context.media_root

    @mcp.tool()
    def get_global_settings() -> dict[str, Any]:
        """Get resolved RetroArch global runtime settings (layered: global+system cfgs)."""
        return _get_global_settings(system, media_root)

    @mcp.tool()
    def set_setting(key: str, value: str) -> dict[str, Any]:
        """Write a global RetroArch override setting (key=value).

        Writes under retroarch_overrides/global.cfg — NEVER clobbers
        the pulled read cfgs in retroarch_cfg.
        """
        override_base = media_root / "retroarch_overrides"
        path = save_global_overrides({key: value}, base_dir=override_base)
        return {
            "key": key,
            "value": value,
            "written_path": str(path),
        }

    @mcp.tool()
    def get_controls() -> dict[str, Any]:
        """Get resolved RetroArch runtime settings for this system (alias for get_global_settings)."""
        return _get_global_settings(system, media_root)

    @mcp.tool()
    def set_runahead(game_id: str, enabled: bool) -> dict[str, Any]:
        """Enable/disable run-ahead for a game by writing a per-game RetroArch override.

        Takes effect on next launch. Writes under retroarch_overrides (never clobbers
        the pulled read cfgs in retroarch_cfg).
        """
        core = resolve_core(system, media_root)
        override_base = media_root / "retroarch_overrides"
        path = save_runahead(game_id, core, enabled, base_dir=override_base)
        return {
            "game_id": game_id,
            "run_ahead_enabled": enabled,
            "core": core,
            "written_path": str(path),
        }
