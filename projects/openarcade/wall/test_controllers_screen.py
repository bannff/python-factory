"""Tests for f385v: Controllers nav screen in Navigator.

Validates:
- Nav to controllers shows the screen title
- Game picker renders with available games
- With a game selected, 16 dropdown rows render
- Without a game selected, honest empty state (picker prompt)
- Remap write goes to overrides dir (no-clobber)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import flet as ft
import pytest

from wall.navigator import Navigator
from wall.models import GameTile, WallViewModel
from wall.retroarch_config import RetroArchConfig
from wall import chrome as CH


# --- Helpers ---


def _make_controllers_nav(tmp_path: Path) -> Navigator:
    """Build a Navigator wired with RetroArchConfig for controller tests."""
    # Set up minimal config so resolve_core works
    cfg_root = tmp_path / "retroarch_cfg" / "snes"
    cfg_root.mkdir(parents=True)
    (cfg_root / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')
    all_cfg = tmp_path / "retroarch_cfg" / "all"
    all_cfg.mkdir(parents=True)
    (all_cfg / "retroarch.cfg").write_text("run_ahead_enabled = false\n")

    tile = GameTile(id="smw", title="Super Mario World", system="snes", art_url="", core="lr-snes9x2002")
    vm = WallViewModel(tiles=[tile])
    ra_config = RetroArchConfig(media_root=tmp_path, config_dir=tmp_path / "retroarch_overrides")
    return Navigator(vm, config_dir=tmp_path / "retroarch_overrides", media_root=tmp_path, retroarch_config=ra_config)


def _walk_text(control, collected: list[str] | None = None) -> list[str]:
    """Recursively collect all ft.Text values from a control tree."""
    if collected is None:
        collected = []
    if isinstance(control, ft.Text):
        collected.append(control.value or "")
    children = getattr(control, "controls", None) or []
    if isinstance(children, list):
        for c in children:
            _walk_text(c, collected)
    content = getattr(control, "content", None)
    if content is not None:
        _walk_text(content, collected)
    return collected


def _walk_dropdowns(control, collected: list[ft.Dropdown] | None = None) -> list[ft.Dropdown]:
    """Recursively collect all ft.Dropdown widgets."""
    if collected is None:
        collected = []
    if isinstance(control, ft.Dropdown):
        collected.append(control)
    children = getattr(control, "controls", None) or []
    if isinstance(children, list):
        for c in children:
            _walk_dropdowns(c, collected)
    content = getattr(control, "content", None)
    if content is not None:
        _walk_dropdowns(content, collected)
    return collected


# --- Tests ---


class TestControllersScreen:
    """Navigator Controllers screen renders correctly."""

    def test_nav_to_controllers_shows_title(self, tmp_path: Path) -> None:
        """Controllers screen shows the screen title."""
        nav = _make_controllers_nav(tmp_path)
        nav._on_nav_select("controllers")

        texts = _walk_text(nav._switcher.content)
        assert "Controllers" in texts

    def test_nav_to_controllers_shows_game_picker(self, tmp_path: Path) -> None:
        """Controllers screen has a game picker dropdown."""
        nav = _make_controllers_nav(tmp_path)
        nav._on_nav_select("controllers")

        dropdowns = _walk_dropdowns(nav._switcher.content)
        # At least one dropdown (the game picker)
        assert len(dropdowns) >= 1
        picker = dropdowns[0]
        assert picker.label == "Game"

    def test_without_game_shows_honest_empty_state(self, tmp_path: Path) -> None:
        """Without a game selected, shows instructional text (no fake rows)."""
        nav = _make_controllers_nav(tmp_path)
        nav._on_nav_select("controllers")

        texts = _walk_text(nav._switcher.content)
        assert any("select a game" in t.lower() for t in texts)

    def test_with_game_selected_shows_16_remap_dropdowns(self, tmp_path: Path) -> None:
        """With a game selected, renders 16 editable dropdown rows (one per button)."""
        nav = _make_controllers_nav(tmp_path)
        nav._on_nav_select("controllers")
        # Simulate game picker selection (sets selected, then rebuilds)
        nav._state.selected = nav._vm.tiles[0]
        nav._switcher.content = nav._build_controllers()

        dropdowns = _walk_dropdowns(nav._switcher.content)
        # 1 game picker + 16 remap dropdowns = 17
        assert len(dropdowns) == 17

    def test_remap_write_goes_to_overrides_dir(self, tmp_path: Path) -> None:
        """Changing a remap writes to retroarch_overrides (no-clobber)."""
        nav = _make_controllers_nav(tmp_path)
        nav._state.selected = nav._vm.tiles[0]

        # Simulate a remap write
        game = nav._vm.tiles[0]
        nav._ra_config.write_input_remap(game, "a", "b")

        # Verify it landed in overrides
        override_base = tmp_path / "retroarch_overrides"
        from wall.config_service import load_input_remaps
        loaded = load_input_remaps("smw", "lr-snes9x2002", base_dir=override_base)
        assert loaded["input_player1_a"] == "b"

        # Verify retroarch_cfg NOT touched
        cfg_files = list((tmp_path / "retroarch_cfg").rglob("*.rmp"))
        assert len(cfg_files) == 0


class TestControllersNavRailGrowth:
    """Nav rail includes Controllers entry."""

    def test_nav_items_includes_controllers(self) -> None:
        """NAV_ITEMS has a controllers entry with SPORTS_ESPORTS icon."""
        controllers_items = [i for i in CH.NAV_ITEMS if i.route_id == "controllers"]
        assert len(controllers_items) == 1
        assert controllers_items[0].icon == ft.Icons.SPORTS_ESPORTS
        assert controllers_items[0].label == "Controllers"

    def test_nav_rail_has_4_destinations(self, tmp_path: Path) -> None:
        """Nav rail renders 7 destinations (library, systems, import, controllers, cores, settings, info)."""
        nav = _make_controllers_nav(tmp_path)
        rail = nav._rail
        assert len(rail.destinations) == 8
