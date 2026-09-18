"""Controllers tools — get_remap, set_remap.

register() wires these onto the passed FastMCP instance.
Pure core shared by UI + assistant; no UI/Flet imports.
"""

from __future__ import annotations

from typing import Any

from factory.arcade_config.runtime.input_remaps import RETROPAD_BUTTON_ORDER
from factory.arcade_config.runtime.models import RETROPAD_BUTTONS

from wall.config_service import save_input_remap, load_input_remaps
from wall.retroarch_config import RetroArchConfig

from .context import ServerContext
from .settings_query import resolve_core


def _find_tile(tiles: list, game_id: str):
    """Find a GameTile by id. Returns None if not found."""
    return next((t for t in tiles if t.id == game_id), None)


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register controller remap tools (get_remap, set_remap)."""
    from pathlib import Path

    system = context.system
    media_root = context.media_root
    tiles = context.tiles

    ra_config = RetroArchConfig(media_root=media_root, config_dir=media_root / "retroarch_overrides")

    @mcp.tool()
    def get_remap(game_id: str) -> dict[str, Any]:
        """Get the resolved input remap for a game (all 16 RetroPad buttons).

        Returns rows with button, label, current_target, and available choices.
        Each row represents one RetroPad button and its effective target mapping.
        """
        tile = _find_tile(tiles, game_id)
        if tile is None:
            return {"error": f"Game not found: {game_id}"}

        vm = ra_config.resolve_input_remap_vm(tile)
        if vm is None:
            return {"error": f"Cannot resolve remaps for game: {game_id} (no core found)"}

        return {
            "game_id": game_id,
            "rows": [
                {
                    "button": row.button,
                    "label": row.label,
                    "current_target": row.current_target,
                    "choices": list(row.choices),
                }
                for row in vm.rows
            ],
        }

    @mcp.tool()
    def set_remap(game_id: str, button: str, target: str) -> dict[str, Any]:
        """Set a single input remap for a game (RetroPad button -> target).

        Validates button and target against the 16 canonical RetroPad buttons.
        Writes a SPARSE .rmp override (only changed binds; identity = delete key).
        Never clobbers pulled/real cfgs — writes under the overrides dir.
        """
        # Validate button
        if button not in RETROPAD_BUTTONS:
            return {
                "error": f"Invalid button: {button!r}. "
                f"Valid RetroPad buttons: {sorted(RETROPAD_BUTTONS)}",
            }

        # Validate target
        if target not in RETROPAD_BUTTONS:
            return {
                "error": f"Invalid target: {target!r}. "
                f"Valid RetroPad buttons: {sorted(RETROPAD_BUTTONS)}",
            }

        tile = _find_tile(tiles, game_id)
        if tile is None:
            return {"error": f"Game not found: {game_id}"}

        core = ra_config.resolve_core_for_game(tile)
        if not core:
            return {"error": f"Cannot resolve core for game: {game_id}"}

        override_base = media_root / "retroarch_overrides"
        path = save_input_remap(game_id, core, button, target, base_dir=override_base)

        return {
            "game_id": game_id,
            "button": button,
            "target": target,
            "written_path": str(path),
        }
