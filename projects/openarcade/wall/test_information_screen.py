"""Tests for Information shell screen (navigator route 'information')."""

from pathlib import Path

import flet as ft

from wall.models import GameTile, WallViewModel
from wall.navigator import Navigator


def _tile(system: str = "snes", art: str = "", title: str = "Game") -> GameTile:
    return GameTile(id=f"{system}-{title.lower()}", title=title, system=system, art_url=art)


def _make_navigator(tmp_path: Path) -> Navigator:
    """Navigator with minimal real media_root for information_query."""
    cfg_root = tmp_path / "retroarch_cfg"
    (cfg_root / "all").mkdir(parents=True)
    (cfg_root / "all" / "retroarch.cfg").write_text("# RetroArch 1.17.0\nvideo_smooth = false\n")
    (cfg_root / "snes").mkdir()
    (cfg_root / "snes" / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')
    (tmp_path / "retroarch_overrides").mkdir()

    tiles = [_tile("snes", art="http://art.png", title="A"), _tile("snes", title="B")]
    vm = WallViewModel(tiles=tiles, columns=4)
    return Navigator(vm, media_root=tmp_path, config_dir=tmp_path)


class TestInformationScreen:
    def test_navigates_to_information_screen(self, tmp_path: Path):
        nav = _make_navigator(tmp_path)
        nav._on_nav_select("information")
        assert nav.state.current_screen == "information"

    def test_information_screen_returns_container(self, tmp_path: Path):
        nav = _make_navigator(tmp_path)
        content = nav._build_information()
        assert isinstance(content, ft.Container)

    def test_information_screen_shows_system_heading(self, tmp_path: Path):
        nav = _make_navigator(tmp_path)
        content = nav._build_information()
        # Dig into structure: Container > Column > [title, card]
        outer_col = content.content
        assert isinstance(outer_col, ft.Column)
        # Card is second control
        card = outer_col.controls[1]
        inner_col = card.content
        heading = inner_col.controls[0]
        assert "SNES" in heading.value
        assert "lr-snes9x2002" in heading.value

    def test_information_screen_does_not_import_mcp_server(self):
        """Verify the nav screen imports information_query, NOT control_plane.server."""
        import importlib
        import wall.navigator as nav_mod
        # Force re-import to trace
        source = Path(nav_mod.__file__).read_text()
        assert "from control_plane.server" not in source
        assert "import control_plane.server" not in source
        # information_query is the correct import
        assert "control_plane.information_query" in source
