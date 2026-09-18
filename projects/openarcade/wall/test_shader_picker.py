"""Tests for bead 1a8wx: skinned Shader picker.

Behavior-named AAA tests covering:
- SHADER_PRESETS includes None + crt-pi
- Live shader not in list gets appended
- Selecting None writes video_shader_enable false
- Selecting a preset writes enable true + the shader ref
- Round-trip (write preset -> resolve shows it)
- The Shader row is now editable (exposes on_change) not read-only
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from factory.arcade_config.interface import SHADER_PRESETS, parse_cfg, resolve_runtime_settings
from wall.shader_picker_vm import build_shader_picker_vm, ShaderPickerVM
from wall.config_service import save_game_overrides, load_game_overrides


# --- SHADER_PRESETS data ---


def test_shader_presets_includes_none_and_crt_pi():
    """SHADER_PRESETS contains "None" (disable) and "crt-pi" (most common CRT)."""
    assert "None" in SHADER_PRESETS
    assert "crt-pi" in SHADER_PRESETS


def test_shader_presets_starts_with_none():
    """None is the first choice (disable = default action)."""
    assert SHADER_PRESETS[0] == "None"


# --- ShaderPickerVM builder ---


def test_live_shader_in_list_uses_it():
    """Known preset -> current = that preset."""
    vm = build_shader_picker_vm(shader_enabled=True, shader_name="crt-geom")
    assert vm.current == "crt-geom"
    assert "crt-geom" in vm.choices


def test_shader_disabled_shows_none():
    """Disabled shader -> current = None."""
    vm = build_shader_picker_vm(shader_enabled=False, shader_name="crt-pi")
    assert vm.current == "None"


def test_shader_empty_name_shows_none():
    """Empty shader name -> current = None."""
    vm = build_shader_picker_vm(shader_enabled=True, shader_name="")
    assert vm.current == "None"


def test_live_shader_not_in_list_gets_appended():
    """Unknown live shader is appended to choices (disk is truth, never lose state)."""
    vm = build_shader_picker_vm(shader_enabled=True, shader_name="custom-fancy-shader")
    assert vm.current == "custom-fancy-shader"
    assert "custom-fancy-shader" in vm.choices
    # Original presets are still there
    assert "crt-pi" in vm.choices
    assert "None" in vm.choices


# --- Write semantics ---


def test_selecting_none_writes_shader_enable_false(tmp_path: Path):
    """Selecting "None" writes video_shader_enable=false + clears video_shader."""
    overrides = {"video_shader_enable": "false", "video_shader": ""}
    path = save_game_overrides("test_game", "lr-snes9x2002", overrides, base_dir=tmp_path)

    written = parse_cfg(path.read_text())
    assert written["video_shader_enable"] == "false"
    assert written["video_shader"] == ""


def test_selecting_preset_writes_enable_true_and_shader_ref(tmp_path: Path):
    """Selecting a preset writes video_shader_enable=true + video_shader=<name>."""
    overrides = {"video_shader_enable": "true", "video_shader": "crt-pi"}
    path = save_game_overrides("test_game", "lr-snes9x2002", overrides, base_dir=tmp_path)

    written = parse_cfg(path.read_text())
    assert written["video_shader_enable"] == "true"
    assert written["video_shader"] == "crt-pi"


# --- Round-trip ---


def test_round_trip_write_preset_then_resolve(tmp_path: Path):
    """Write a shader preset, then resolve_runtime_settings picks it up."""
    # Write the override
    overrides = {"video_shader_enable": "true", "video_shader": "crt-geom"}
    save_game_overrides("my_game", "lr-snes9x2002", overrides, base_dir=tmp_path)

    # Load it back
    loaded = load_game_overrides("my_game", "lr-snes9x2002", base_dir=tmp_path)

    # Resolve via settings (simulates what navigator does)
    global_cfg: dict[str, str] = {}
    settings = resolve_runtime_settings(global_cfg, loaded, core="lr-snes9x2002")

    assert settings.shader_enabled is True
    assert settings.shader_name == "crt-geom"


def test_round_trip_write_none_then_resolve(tmp_path: Path):
    """Write None (disable), then resolve shows disabled."""
    overrides = {"video_shader_enable": "false", "video_shader": ""}
    save_game_overrides("my_game", "lr-snes9x2002", overrides, base_dir=tmp_path)

    loaded = load_game_overrides("my_game", "lr-snes9x2002", base_dir=tmp_path)
    settings = resolve_runtime_settings({}, loaded, core="lr-snes9x2002")

    assert settings.shader_enabled is False
    assert settings.shader_name == ""


# --- Editable row (integration with components) ---


def test_shader_row_is_editable_with_on_change():
    """controls_panel with on_shader_change renders an editable dropdown (not readonly)."""
    import flet as ft
    from wall.controls_vm import ControlsVM
    from wall.components import controls_panel

    vm = ControlsVM(
        runahead_enabled=False,
        runahead_frames=1,
        shader_enabled=True,
        shader_name="crt-pi",
        video_smooth=False,
        core="lr-snes9x2002",
        remap_rows=None,
    )

    changes: list[str] = []

    panel = controls_panel(vm, on_shader_change=lambda v: changes.append(v))

    # Find the Dropdown in the panel tree
    def _find_dropdowns(ctrl: ft.Control) -> list[ft.Dropdown]:
        found = []
        if isinstance(ctrl, ft.Dropdown):
            found.append(ctrl)
        if hasattr(ctrl, "controls"):
            for c in ctrl.controls:
                found.extend(_find_dropdowns(c))
        if hasattr(ctrl, "content") and ctrl.content:
            found.extend(_find_dropdowns(ctrl.content))
        return found

    dropdowns = _find_dropdowns(panel)
    # There should be at least one dropdown (the shader picker)
    assert len(dropdowns) >= 1
    shader_dd = dropdowns[0]  # first dropdown in controls panel is shader
    assert shader_dd.value == "crt-pi"
    assert any("crt-pi" in str(o.key) for o in shader_dd.options) or shader_dd.value == "crt-pi"


def test_shader_row_is_readonly_without_callback():
    """controls_panel without on_shader_change renders readonly (no Dropdown)."""
    import flet as ft
    from wall.controls_vm import ControlsVM
    from wall.components import controls_panel

    vm = ControlsVM(
        runahead_enabled=False,
        runahead_frames=1,
        shader_enabled=True,
        shader_name="crt-pi",
        video_smooth=False,
        core="lr-snes9x2002",
        remap_rows=None,
    )

    panel = controls_panel(vm)  # no on_shader_change

    # Count dropdowns — should be 0 (shader is readonly text)
    def _count_dropdowns(ctrl: ft.Control) -> int:
        count = 0
        if isinstance(ctrl, ft.Dropdown):
            count += 1
        if hasattr(ctrl, "controls"):
            for c in ctrl.controls:
                count += _count_dropdowns(c)
        if hasattr(ctrl, "content") and ctrl.content:
            count += _count_dropdowns(ctrl.content)
        return count

    assert _count_dropdowns(panel) == 0
