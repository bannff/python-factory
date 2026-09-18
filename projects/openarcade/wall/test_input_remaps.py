"""Tests for febou: Input Remap — model validation, builder, VM, persistence, UI row."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# --- Layer 1: InputRemap rejects invalid target ---


def test_input_remap_rejects_invalid_retropad_button():
    """InputRemap raises ValueError for unknown retropad_button."""
    from factory.arcade_config.runtime.models import InputRemap

    with pytest.raises(ValueError, match="Unknown RetroPad button"):
        InputRemap(retropad_button="bogus", target="a")


def test_input_remap_rejects_invalid_target():
    """InputRemap raises ValueError for invalid target button."""
    from factory.arcade_config.runtime.models import InputRemap

    with pytest.raises(ValueError, match="Invalid remap target"):
        InputRemap(retropad_button="a", target="invalid_button")


def test_input_remap_accepts_valid_identity():
    """InputRemap accepts valid button->button identity mapping."""
    from factory.arcade_config.runtime.models import InputRemap

    remap = InputRemap(retropad_button="a", target="b")
    assert remap.retropad_button == "a"
    assert remap.target == "b"


# --- Layer 2: build_input_remaps ---


def test_build_input_remaps_yields_all_16_at_identity_when_raw_empty():
    """Empty raw -> all 16 buttons at identity (button maps to itself)."""
    from factory.arcade_config.runtime.input_remaps import build_input_remaps, RETROPAD_BUTTON_ORDER

    remaps = build_input_remaps({})

    assert len(remaps) == 16
    for remap in remaps:
        assert remap.retropad_button == remap.target  # identity
    # Ordering matches canonical
    assert [r.retropad_button for r in remaps] == list(RETROPAD_BUTTON_ORDER)


def test_build_input_remaps_live_override_wins():
    """Live override from .rmp replaces identity default for that button."""
    from factory.arcade_config.runtime.input_remaps import build_input_remaps

    raw = {"input_player1_a": "b", "input_player1_x": "y"}
    remaps = build_input_remaps(raw)

    remap_dict = {r.retropad_button: r.target for r in remaps}
    assert remap_dict["a"] == "b"
    assert remap_dict["x"] == "y"
    # Others still identity
    assert remap_dict["start"] == "start"
    assert remap_dict["l"] == "l"


def test_build_input_remaps_invalid_target_falls_back_to_identity():
    """Invalid target in raw falls back to identity (graceful, no crash)."""
    from factory.arcade_config.runtime.input_remaps import build_input_remaps

    raw = {"input_player1_a": "totally_invalid"}
    remaps = build_input_remaps(raw)

    remap_dict = {r.retropad_button: r.target for r in remaps}
    assert remap_dict["a"] == "a"  # fallback to identity


# --- Layer 3: InputRemapVM ---


def test_input_remap_vm_builds_all_rows():
    """VM has a row per remap with label, target, and full choices."""
    from factory.arcade_config.runtime.models import InputRemap
    from factory.arcade_config.runtime.input_remaps import RETROPAD_BUTTON_ORDER
    from wall.input_remap_vm import input_remap_vm_from_remaps

    remaps = [InputRemap(retropad_button=b, target=b) for b in RETROPAD_BUTTON_ORDER]
    vm = input_remap_vm_from_remaps(remaps)

    assert len(vm.rows) == 16
    for row in vm.rows:
        assert row.choices == RETROPAD_BUTTON_ORDER
        assert row.label == row.button.upper()


# --- Layer 4: save_input_remap writes sparse ---


def test_save_input_remap_writes_non_identity():
    """Non-identity remap is written to .rmp file."""
    from wall.config_service import save_input_remap, load_input_remaps

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_input_remap("game1", "lr-snes9x2002", "a", "b", base_dir=base)

        loaded = load_input_remaps("game1", "lr-snes9x2002", base_dir=base)
        assert loaded["input_player1_a"] == "b"


def test_save_input_remap_identity_not_written():
    """Identity remap (button == target) removes key from file."""
    from wall.config_service import save_input_remap, load_input_remaps

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Write a non-identity first
        save_input_remap("game1", "lr-snes9x2002", "a", "b", base_dir=base)
        assert "input_player1_a" in load_input_remaps("game1", "lr-snes9x2002", base_dir=base)

        # Now set back to identity
        save_input_remap("game1", "lr-snes9x2002", "a", "a", base_dir=base)
        loaded = load_input_remaps("game1", "lr-snes9x2002", base_dir=base)
        assert "input_player1_a" not in loaded


def test_save_input_remap_preserves_other_keys():
    """Writing one remap preserves other remap keys in the .rmp file."""
    from wall.config_service import save_input_remap, load_input_remaps

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_input_remap("game1", "lr-snes9x2002", "a", "b", base_dir=base)
        save_input_remap("game1", "lr-snes9x2002", "x", "y", base_dir=base)

        loaded = load_input_remaps("game1", "lr-snes9x2002", base_dir=base)
        assert loaded["input_player1_a"] == "b"
        assert loaded["input_player1_x"] == "y"


def test_save_input_remap_round_trip():
    """Write non-identity -> build_input_remaps shows override; identity -> shows identity."""
    from factory.arcade_config.runtime.input_remaps import build_input_remaps
    from wall.config_service import save_input_remap, load_input_remaps

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_input_remap("game1", "lr-snes9x2002", "a", "x", base_dir=base)

        raw = load_input_remaps("game1", "lr-snes9x2002", base_dir=base)
        remaps = build_input_remaps(raw)
        remap_dict = {r.retropad_button: r.target for r in remaps}
        assert remap_dict["a"] == "x"
        assert remap_dict["b"] == "b"  # identity (not in file)


# --- Layer 5: UI component row type contracts ---


def test_controls_panel_with_input_remap_vm_renders_dropdowns():
    """controls_panel with input_remap_vm and on_remap_change renders Dropdown rows."""
    import flet as ft
    from factory.arcade_config.runtime.models import InputRemap
    from factory.arcade_config.runtime.input_remaps import RETROPAD_BUTTON_ORDER
    from wall.input_remap_vm import input_remap_vm_from_remaps
    from wall.controls_vm import ControlsVM
    from wall.components import controls_panel

    remaps = [InputRemap(retropad_button=b, target=b) for b in RETROPAD_BUTTON_ORDER]
    vm = input_remap_vm_from_remaps(remaps)

    controls_vm_obj = ControlsVM(
        runahead_enabled=False,
        runahead_frames=1,
        shader_enabled=False,
        shader_name="",
        video_smooth=False,
        core="lr-snes9x2002",
        remap_rows=None,
    )

    calls: list[tuple[str, str]] = []
    panel = controls_panel(
        controls_vm_obj,
        input_remap_vm=vm,
        on_remap_change=lambda btn, tgt: calls.append((btn, tgt)),
    )

    assert isinstance(panel, ft.Column)
    # Should contain Dropdown controls for remaps
    all_dropdowns = []
    for ctrl in panel.controls:
        if isinstance(ctrl, ft.Column):
            for sub in ctrl.controls:
                if isinstance(sub, ft.Row):
                    for c in sub.controls:
                        if isinstance(c, ft.Dropdown):
                            all_dropdowns.append(c)
    assert len(all_dropdowns) == 16  # one per button
