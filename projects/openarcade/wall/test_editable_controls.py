"""Tests for 36c2r: editable controls — generic seam, merge, type-level rows."""

from pathlib import Path

import pytest

from wall.config_service import (
    save_game_overrides,
    save_global_overrides,
    load_game_overrides,
    save_runahead,
    load_runahead,
)
from wall.controls_vm import ControlsVM, controls_from_settings
from wall.components import editable_toggle_row, readonly_value_row, controls_panel
from factory.arcade_config.runtime.models import RunAheadConfig


# ---------------------------------------------------------------------------
# Generic seam tests
# ---------------------------------------------------------------------------


class TestSaveGameOverrides:
    """save_game_overrides writes given keys under the per-game override path."""

    def test_writes_single_key(self, tmp_path: Path) -> None:
        path = save_game_overrides("sf2", "mame2003_plus", {"video_smooth": "true"}, base_dir=tmp_path)
        content = path.read_text()
        assert 'video_smooth = "true"' in content

    def test_writes_multiple_keys(self, tmp_path: Path) -> None:
        path = save_game_overrides(
            "sf2", "mame2003_plus",
            {"run_ahead_enabled": "true", "video_smooth": "false"},
            base_dir=tmp_path,
        )
        content = path.read_text()
        assert 'run_ahead_enabled = "true"' in content
        assert 'video_smooth = "false"' in content

    def test_path_is_under_base_dir(self, tmp_path: Path) -> None:
        path = save_game_overrides("kinst", "mame2016", {"video_smooth": "true"}, base_dir=tmp_path)
        assert path.is_relative_to(tmp_path)
        assert "mame2016" in path.parts
        assert path.name == "kinst.cfg"


class TestMergeOverrides:
    """Toggling one setting must NOT clobber a sibling key already present."""

    def test_merge_preserves_existing_keys(self, tmp_path: Path) -> None:
        # Write run_ahead first
        save_game_overrides("sf2", "mame", {"run_ahead_enabled": "true", "run_ahead_frames": "1"}, base_dir=tmp_path)
        # Then toggle video_smooth — run_ahead must survive
        path = save_game_overrides("sf2", "mame", {"video_smooth": "true"}, base_dir=tmp_path)
        content = path.read_text()
        assert 'run_ahead_enabled = "true"' in content
        assert 'run_ahead_frames = "1"' in content
        assert 'video_smooth = "true"' in content

    def test_merge_overwrites_same_key(self, tmp_path: Path) -> None:
        save_game_overrides("sf2", "mame", {"video_smooth": "true"}, base_dir=tmp_path)
        path = save_game_overrides("sf2", "mame", {"video_smooth": "false"}, base_dir=tmp_path)
        content = path.read_text()
        assert 'video_smooth = "false"' in content
        assert content.count("video_smooth") == 1  # no duplicates

    def test_load_game_overrides_returns_all_keys(self, tmp_path: Path) -> None:
        save_game_overrides("sf2", "mame", {"run_ahead_enabled": "true", "video_smooth": "false"}, base_dir=tmp_path)
        loaded = load_game_overrides("sf2", "mame", base_dir=tmp_path)
        assert loaded == {"run_ahead_enabled": "true", "video_smooth": "false"}

    def test_load_game_overrides_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        loaded = load_game_overrides("nope", "core", base_dir=tmp_path)
        assert loaded == {}


class TestSaveRunaheadDelegation:
    """save_runahead still works correctly through the generic seam."""

    def test_enabled_writes_true_and_frames(self, tmp_path: Path) -> None:
        path = save_runahead("sf2", "mame2003_plus", True, base_dir=tmp_path)
        content = path.read_text()
        assert 'run_ahead_enabled = "true"' in content
        assert 'run_ahead_frames = "1"' in content

    def test_disabled_writes_false(self, tmp_path: Path) -> None:
        path = save_runahead("sf2", "mame2003_plus", False, base_dir=tmp_path)
        content = path.read_text()
        assert 'run_ahead_enabled = "false"' in content

    def test_round_trip_preserved(self, tmp_path: Path) -> None:
        save_runahead("sf2", "mame2003_plus", True, base_dir=tmp_path)
        result = load_runahead("sf2", "mame2003_plus", base_dir=tmp_path)
        assert result == RunAheadConfig(enabled=True, frames=1)

    def test_runahead_merges_with_existing_video_smooth(self, tmp_path: Path) -> None:
        """If video_smooth was already written, save_runahead must NOT clobber it."""
        save_game_overrides("sf2", "mame2003_plus", {"video_smooth": "true"}, base_dir=tmp_path)
        save_runahead("sf2", "mame2003_plus", True, base_dir=tmp_path)
        from factory.arcade_config.runtime.serializers import parse_cfg
        from factory.arcade_config.runtime.resolver import override_path
        from factory.arcade_config.runtime.models import Scope
        path = override_path(tmp_path, Scope.GAME, core="mame2003_plus", game="sf2", kind="cfg")
        pairs = parse_cfg(path.read_text())
        assert pairs["video_smooth"] == "true"
        assert pairs["run_ahead_enabled"] == "true"


# ---------------------------------------------------------------------------
# Type-level row tests
# ---------------------------------------------------------------------------


class TestEditableVsReadonlyRows:
    """Type-level distinction: editable rows have callback, read-only rows cannot."""

    def test_editable_toggle_row_has_switch(self) -> None:
        import flet as ft
        called = []
        row = editable_toggle_row("Run-Ahead", True, on_change=lambda v: called.append(v))
        # Should have a Switch in the controls
        switches = [c for c in row.controls if isinstance(c, ft.Switch)]
        assert len(switches) == 1
        assert switches[0].value is True

    def test_readonly_value_row_has_no_switch(self) -> None:
        import flet as ft
        row = readonly_value_row("Shader", "crt-pi")
        switches = [c for c in row.controls if isinstance(c, ft.Switch)]
        assert len(switches) == 0

    def test_controls_panel_with_callbacks_has_switches(self) -> None:
        import flet as ft
        from factory.arcade_config.runtime.settings import RetroArchRuntimeSettings
        settings = RetroArchRuntimeSettings(
            core="lr-snes9x", run_ahead_enabled=False, run_ahead_frames=1,
            shader_enabled=True, shader_name="crt-pi", video_smooth=False,
        )
        vm = controls_from_settings(settings)
        panel = controls_panel(
            vm,
            on_runahead_toggle=lambda v: None,
            on_video_smooth_toggle=lambda v: None,
        )
        # Should have exactly 2 switches (Run-Ahead + Video Smoothing)
        all_switches = _find_switches(panel)
        assert len(all_switches) == 2

    def test_controls_panel_without_callbacks_has_no_switches(self) -> None:
        import flet as ft
        from factory.arcade_config.runtime.settings import RetroArchRuntimeSettings
        settings = RetroArchRuntimeSettings(
            core="lr-snes9x", run_ahead_enabled=True, run_ahead_frames=1,
            shader_enabled=True, shader_name="crt-pi", video_smooth=True,
        )
        vm = controls_from_settings(settings)
        panel = controls_panel(vm)
        all_switches = _find_switches(panel)
        assert len(all_switches) == 0


# ---------------------------------------------------------------------------
# VM reflects merged override
# ---------------------------------------------------------------------------


class TestVmReflectsMergedOverride:
    """After writing, re-resolving the VM must reflect the new state."""

    def test_vm_reflects_video_smooth_after_write(self, tmp_path: Path) -> None:
        from factory.arcade_config.runtime.settings import resolve_runtime_settings
        from factory.arcade_config.runtime.serializers import parse_cfg

        # Base: video_smooth=false
        base_cfg = {"video_smooth": "false", "run_ahead_enabled": "false"}
        # Write override: video_smooth=true
        save_game_overrides("sf2", "mame", {"video_smooth": "true"}, base_dir=tmp_path)
        overrides = load_game_overrides("sf2", "mame", base_dir=tmp_path)

        merged = {**base_cfg, **overrides}
        settings = resolve_runtime_settings(merged)
        vm = controls_from_settings(settings)
        assert vm.video_smooth is True

    def test_vm_reflects_runahead_after_write(self, tmp_path: Path) -> None:
        from factory.arcade_config.runtime.settings import resolve_runtime_settings

        base_cfg = {"run_ahead_enabled": "false"}
        save_game_overrides("sf2", "mame", {"run_ahead_enabled": "true", "run_ahead_frames": "1"}, base_dir=tmp_path)
        overrides = load_game_overrides("sf2", "mame", base_dir=tmp_path)

        merged = {**base_cfg, **overrides}
        settings = resolve_runtime_settings(merged)
        vm = controls_from_settings(settings)
        assert vm.runahead_enabled is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_switches(control) -> list:
    """Recursively find all ft.Switch instances in a Flet control tree."""
    import flet as ft
    found = []
    if isinstance(control, ft.Switch):
        found.append(control)
    if hasattr(control, "controls"):
        for c in (control.controls or []):
            found.extend(_find_switches(c))
    if hasattr(control, "content") and control.content:
        found.extend(_find_switches(control.content))
    return found
