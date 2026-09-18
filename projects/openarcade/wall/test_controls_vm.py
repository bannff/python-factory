"""Tests for controls_vm (pure VM builder) and controls_panel (Flet builder)."""

from __future__ import annotations

import flet as ft
import pytest

from factory.arcade_config.runtime.settings import RetroArchRuntimeSettings, resolve_runtime_settings

from wall.controls_vm import ControlsVM, controls_from_settings
from wall.components import controls_panel, detail_tabs
from wall.models import GameTile


# --- Fixtures ---


def _settings(**overrides) -> RetroArchRuntimeSettings:
    defaults = dict(
        core="lr-snes9x2002",
        run_ahead_enabled=False,
        run_ahead_frames=1,
        shader_enabled=False,
        shader_name="",
        video_smooth=False,
    )
    defaults.update(overrides)
    return RetroArchRuntimeSettings(**defaults)


def _make_game(**kwargs) -> GameTile:
    defaults = dict(
        id="test-1", title="Test", system="SNES", rom_path="/roms/test.zip",
        playable=True, art_url=None, description=None, players=None,
        genre=None, category=None, screenshots=(), developer=None,
        publisher=None, release_date=None, rating=None,
        last_played=None, play_count=None, status_detail=None,
    )
    defaults.update(kwargs)
    return GameTile(**defaults)


# --- controls_from_settings tests ---


class TestControlsFromSettings:
    def test_threads_all_fields(self):
        s = _settings(run_ahead_enabled=True, run_ahead_frames=3, shader_enabled=True, shader_name="crt-pi", video_smooth=True)
        vm = controls_from_settings(s)
        assert vm.runahead_enabled is True
        assert vm.runahead_frames == 3
        assert vm.shader_enabled is True
        assert vm.shader_name == "crt-pi"
        assert vm.video_smooth is True
        assert vm.core == "lr-snes9x2002"

    def test_default_remap_none(self):
        vm = controls_from_settings(_settings())
        assert vm.remap_rows is None

    def test_explicit_remaps_threaded(self):
        remaps = (("a", "b"), ("x", "y"))
        vm = controls_from_settings(_settings(), remaps=remaps)
        assert vm.remap_rows == remaps


# --- controls_panel rendering tests ---


def _walk_text(control: ft.Control) -> list[str]:
    """Recursively collect all ft.Text.value strings."""
    texts: list[str] = []
    if isinstance(control, ft.Text) and control.value:
        texts.append(control.value)
    for attr in ("controls", "content"):
        child = getattr(control, attr, None)
        if child is None:
            continue
        if isinstance(child, list):
            for c in child:
                texts.extend(_walk_text(c))
        elif isinstance(child, ft.Control):
            texts.extend(_walk_text(child))
    return texts


class TestControlsPanel:
    def test_renders_runahead_off(self):
        vm = controls_from_settings(_settings(run_ahead_enabled=False))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Run-Ahead" in texts
        assert "Off" in texts

    def test_renders_runahead_on_with_frames(self):
        vm = controls_from_settings(_settings(run_ahead_enabled=True, run_ahead_frames=2))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "On \u2013 2 frames" in texts

    def test_renders_runahead_singular_frame(self):
        vm = controls_from_settings(_settings(run_ahead_enabled=True, run_ahead_frames=1))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "On \u2013 1 frame" in texts

    def test_renders_shader_name_when_enabled(self):
        vm = controls_from_settings(_settings(shader_enabled=True, shader_name="crt-pi"))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Shader" in texts
        assert "crt-pi" in texts

    def test_renders_shader_off(self):
        vm = controls_from_settings(_settings(shader_enabled=False))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Off" in texts

    def test_renders_video_smoothing(self):
        vm = controls_from_settings(_settings(video_smooth=True))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Video Smoothing" in texts
        assert "On" in texts

    def test_renders_core_when_present(self):
        vm = controls_from_settings(_settings(core="lr-snes9x2002"))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Core" in texts
        assert "lr-snes9x2002" in texts

    def test_omits_core_row_when_empty(self):
        vm = controls_from_settings(_settings(core=""))
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Core" not in texts

    def test_default_layout_when_no_remaps(self):
        vm = controls_from_settings(_settings())
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Default RetroPad layout" in texts

    def test_handoff_row_present(self):
        vm = controls_from_settings(_settings())
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Advanced \u2013 Open RetroArch Menu" in texts

    def test_no_fake_switch(self):
        """Fake ft.Switch must be gone."""
        vm = controls_from_settings(_settings())
        panel = controls_panel(vm)

        def _find_switch(ctrl: ft.Control) -> bool:
            if isinstance(ctrl, ft.Switch):
                return True
            for attr in ("controls", "content"):
                child = getattr(ctrl, attr, None)
                if child is None:
                    continue
                if isinstance(child, list):
                    for c in child:
                        if _find_switch(c):
                            return True
                elif isinstance(child, ft.Control):
                    if _find_switch(child):
                        return True
            return False

        assert not _find_switch(panel)

    def test_no_coming_soon(self):
        """'Coming soon' must not appear for real settings."""
        vm = controls_from_settings(_settings())
        panel = controls_panel(vm)
        texts = _walk_text(panel)
        assert "Coming soon" not in texts


# --- detail_tabs integration ---


class TestDetailTabs:
    def test_controls_tab_shows_real_values(self):
        game = _make_game()
        vm = controls_from_settings(_settings(shader_enabled=True, shader_name="crt-pi"))
        tabs = detail_tabs(game, active_tab="controls", controls_vm=vm)
        texts = _walk_text(tabs)
        assert "crt-pi" in texts
        assert "Run-Ahead" in texts
        assert "Advanced \u2013 Open RetroArch Menu" in texts

    def test_controls_tab_no_vm_uses_fallback(self):
        game = _make_game()
        tabs = detail_tabs(game, active_tab="controls")
        texts = _walk_text(tabs)
        assert "Run-Ahead" in texts
        assert "Off" in texts

    def test_description_tab_unchanged(self):
        game = _make_game(description="A great game")
        tabs = detail_tabs(game, active_tab="description")
        texts = _walk_text(tabs)
        assert "A great game" in texts
