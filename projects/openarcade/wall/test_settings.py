"""Tests for B23 — nav-rail Settings screen (global runahead + settings_view)."""

from pathlib import Path

import pytest

from wall.config_service import save_global_runahead, load_global_runahead
from wall.navigator import Navigator
from wall.models import GameTile, WallViewModel
from wall import chrome as CH
from factory.arcade_config.runtime.models import RunAheadConfig


# --- Helpers ---


def _make_nav(tmp_path: Path) -> Navigator:
    tile = GameTile(id="sf2", title="Street Fighter II", system="SNES", art_url="", core="snes9x")
    vm = WallViewModel(tiles=[tile])
    return Navigator(vm, config_dir=tmp_path)


def _walk_text(control, collected: list[str] | None = None) -> list[str]:
    """Recursively collect all ft.Text values from a control tree."""
    import flet as ft
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


# --- Global Runahead Persistence ---


class TestSaveGlobalRunahead:
    """save_global_runahead writes base_dir/global.cfg."""

    def test_enabled_writes_true(self, tmp_path: Path) -> None:
        path = save_global_runahead(True, base_dir=tmp_path)
        content = path.read_text()
        assert 'run_ahead_enabled = "true"' in content
        assert 'run_ahead_frames = "1"' in content

    def test_disabled_writes_false(self, tmp_path: Path) -> None:
        path = save_global_runahead(False, base_dir=tmp_path)
        content = path.read_text()
        assert 'run_ahead_enabled = "false"' in content

    def test_path_is_global_cfg(self, tmp_path: Path) -> None:
        path = save_global_runahead(True, base_dir=tmp_path)
        assert path.name == "global.cfg"
        assert path.parent == tmp_path

    def test_no_real_retroarch_path(self, tmp_path: Path) -> None:
        path = save_global_runahead(True, base_dir=tmp_path)
        assert ".config/retroarch" not in str(path)


class TestLoadGlobalRunahead:
    """load_global_runahead reads back or returns None."""

    def test_round_trip_enabled(self, tmp_path: Path) -> None:
        save_global_runahead(True, base_dir=tmp_path)
        result = load_global_runahead(base_dir=tmp_path)
        assert result == RunAheadConfig(enabled=True, frames=1)

    def test_round_trip_disabled_returns_config_not_none(self, tmp_path: Path) -> None:
        save_global_runahead(False, base_dir=tmp_path)
        result = load_global_runahead(base_dir=tmp_path)
        assert result is not None
        assert result == RunAheadConfig(enabled=False, frames=1)

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert load_global_runahead(base_dir=tmp_path) is None

    def test_malformed_degrades_to_safe_default(self, tmp_path: Path) -> None:
        (tmp_path / "global.cfg").write_text("garbage data\n")
        result = load_global_runahead(base_dir=tmp_path)
        assert result == RunAheadConfig(enabled=False, frames=1)

    def test_present_disabled_returns_runconfig_not_none(self, tmp_path: Path) -> None:
        """Explicit enabled=False in file must return RunAheadConfig, not None."""
        (tmp_path / "global.cfg").write_text('run_ahead_enabled = "false"\nrun_ahead_frames = "1"\n')
        result = load_global_runahead(base_dir=tmp_path)
        assert result is not None
        assert result.enabled is False


# --- Settings View Builder ---


class TestSettingsView:
    """settings_view renders Video / Audio / Latency sections + About text."""

    def _render(self, global_settings_vm=None, config_dir_text="/tmp/cfg") -> list[str]:
        from wall.global_settings_vm import build_global_settings_vm
        vm = global_settings_vm or build_global_settings_vm({})
        view = CH.settings_view(
            global_settings_vm=vm,
            on_setting_change=lambda k, v: None,
            config_dir_text=config_dir_text,
        )
        return _walk_text(view)

    def test_title_present(self) -> None:
        texts = self._render()
        assert "Settings" in texts

    def test_video_section_present(self) -> None:
        texts = self._render()
        assert "Video" in texts
        assert "Aspect Ratio" in texts

    def test_audio_section_present(self) -> None:
        texts = self._render()
        assert "Audio" in texts
        assert "Volume (dB)" in texts

    def test_latency_section_present(self) -> None:
        texts = self._render()
        assert "Latency" in texts
        assert "Run-Ahead Frames" in texts

    def test_no_coming_soon_sections(self) -> None:
        texts = self._render()
        assert "Coming soon" not in texts

    def test_about_section_shows_config_dir(self) -> None:
        texts = self._render(config_dir_text="/my/config")
        assert any("/my/config" in t for t in texts)

    def test_about_section_shows_version(self) -> None:
        texts = self._render()
        assert any("0.1.0" in t for t in texts)

    def test_vsync_default_true_toggle(self) -> None:
        """VSync defaults to enabled (toggle=true)."""
        from wall.global_settings_vm import build_global_settings_vm
        vm = build_global_settings_vm({})
        view = CH.settings_view(
            global_settings_vm=vm,
            on_setting_change=lambda k, v: None,
            config_dir_text="x",
        )
        import flet as ft
        switches = []
        def _find_switches(ctrl):
            if isinstance(ctrl, ft.Switch):
                switches.append(ctrl)
            for c in getattr(ctrl, "controls", []) or []:
                _find_switches(c)
            if getattr(ctrl, "content", None):
                _find_switches(ctrl.content)
        _find_switches(view)
        # VSync defaults true -> at least one switch should be True
        assert any(s.value is True for s in switches)

    def test_no_vm_shows_placeholder(self) -> None:
        view = CH.settings_view(
            global_settings_vm=None,
            on_setting_change=None,
            config_dir_text="x",
        )
        texts = _walk_text(view)
        assert "No config directory configured" in texts


# --- Navigator Integration ---


class TestNavigatorSettings:
    """Navigator._on_nav_select routes to settings and back."""

    def test_nav_to_settings_shows_settings_content(self, tmp_path: Path) -> None:
        nav = _make_nav(tmp_path)
        nav._on_nav_select("settings")

        texts = _walk_text(nav._switcher.content)
        assert "Settings" in texts
        assert any("About" in t for t in texts)

    def test_nav_to_library_shows_wall(self, tmp_path: Path) -> None:
        nav = _make_nav(tmp_path)
        nav._on_nav_select("settings")
        nav._on_nav_select("library")

        texts = _walk_text(nav._switcher.content)
        # Wall shows game title
        assert "Street Fighter II" in texts

    def test_current_screen_tracks_route(self, tmp_path: Path) -> None:
        nav = _make_nav(tmp_path)
        assert nav._state.current_screen == "library"
        nav._on_nav_select("settings")
        assert nav._state.current_screen == "settings"
        nav._on_nav_select("library")
        assert nav._state.current_screen == "library"

    def test_global_setting_change_writes_file(self, tmp_path: Path) -> None:
        nav = _make_nav(tmp_path)
        nav._on_nav_select("settings")
        nav._on_global_setting_change("video_smooth", "true")

        from wall.config_service import _load_existing
        from factory.arcade_config.runtime.resolver import override_path
        from factory.arcade_config.runtime.models import Scope
        path = override_path(tmp_path, Scope.GLOBAL, kind="cfg")
        content = _load_existing(path)
        assert content["video_smooth"] == "true"

    def test_global_setting_change_noop_without_config_dir(self) -> None:
        tile = GameTile(id="sf2", title="Street Fighter II", system="SNES", art_url="", core="snes9x")
        vm = WallViewModel(tiles=[tile])
        nav = Navigator(vm, config_dir=None)
        # Should not raise
        nav._on_global_setting_change("video_smooth", "true")
