"""Tests for dge52: Core Options — schema, merge, VM, persistence, UI row."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# --- Layer 1: Schema registry ---


def test_snes9x_schema_has_real_options():
    """Schema contains well-known snes9x libretro options."""
    from factory.arcade_config.runtime.schemas.snes9x import SNES9X_CORE_OPTIONS

    assert "snes9x_region" in SNES9X_CORE_OPTIONS
    assert "snes9x_blargg" in SNES9X_CORE_OPTIONS
    label, choices = SNES9X_CORE_OPTIONS["snes9x_region"]
    assert label == "Console Region"
    assert "NTSC" in choices
    assert "PAL" in choices


def test_core_option_schemas_registry_maps_core_names():
    """Registry maps known snes9x core names to the snes9x schema."""
    from factory.arcade_config.runtime.schemas import CORE_OPTION_SCHEMAS

    assert "lr-snes9x2002" in CORE_OPTION_SCHEMAS
    assert "snes9x_libretro" in CORE_OPTION_SCHEMAS


# --- Layer 3: build_core_options partitions curated vs raw ---


def test_build_core_options_partitions_curated_vs_raw():
    """Curated keys -> CoreOption, uncurated -> RawOption."""
    from factory.arcade_config.runtime.core_options import build_core_options

    schema = {
        "snes9x_region": ("Console Region", ("Auto", "NTSC", "PAL")),
    }
    raw = {"snes9x_region": "NTSC", "some_unknown_key": "foo"}

    curated, raw_opts = build_core_options(raw, schema)

    assert len(curated) == 1
    assert curated[0].key == "snes9x_region"
    assert curated[0].value == "NTSC"
    assert curated[0].allowed == ("Auto", "NTSC", "PAL")

    assert len(raw_opts) == 1
    assert raw_opts[0].key == "some_unknown_key"
    assert raw_opts[0].value == "foo"


def test_build_core_options_appends_live_value_when_missing_from_allowed():
    """If disk value is not in curated allowed, append it — never raise."""
    from factory.arcade_config.runtime.core_options import build_core_options

    schema = {
        "snes9x_region": ("Console Region", ("Auto", "NTSC", "PAL")),
    }
    raw = {"snes9x_region": "SECAM"}  # Not in allowed

    curated, _ = build_core_options(raw, schema)

    assert curated[0].value == "SECAM"
    assert "SECAM" in curated[0].allowed
    # Original choices still present
    assert "Auto" in curated[0].allowed


def test_build_core_options_empty_raw_shows_schema_defaults():
    """Empty raw -> every schema option rendered at its default (first choice), no raw."""
    from factory.arcade_config.runtime.core_options import build_core_options

    curated, raw_opts = build_core_options({}, {"k": ("L", ("a", "b"))})
    assert len(curated) == 1
    assert curated[0].key == "k"
    assert curated[0].value == "a"  # libretro default = first allowed choice
    assert curated[0].allowed == ("a", "b")
    assert raw_opts == []


# --- Layer 4: VM marks curated editable + raw read-only ---


def test_core_options_vm_curated_is_editable():
    """Curated options in the VM are marked editable=True."""
    from factory.arcade_config.runtime.models import CoreOption, RawOption
    from wall.core_options_vm import core_options_vm_from_options

    curated = [CoreOption(key="snes9x_region", value="NTSC", allowed=("Auto", "NTSC", "PAL"))]
    raw = [RawOption(key="unknown_opt", value="bar")]

    vm = core_options_vm_from_options(curated, raw, schema={
        "snes9x_region": ("Console Region", ("Auto", "NTSC", "PAL")),
    })

    assert vm.curated[0].editable is True
    assert vm.curated[0].label == "Console Region"
    assert vm.curated[0].choices == ("Auto", "NTSC", "PAL")


def test_core_options_vm_raw_is_readonly():
    """Uncurated options in the VM are marked editable=False."""
    from factory.arcade_config.runtime.models import CoreOption, RawOption
    from wall.core_options_vm import core_options_vm_from_options

    vm = core_options_vm_from_options(
        [],
        [RawOption(key="snes9x_magic", value="42")],
    )

    assert vm.uncurated[0].editable is False
    assert vm.uncurated[0].value == "42"


# --- Layer 6: save_core_option writes .opt override merged ---


def test_save_core_option_creates_opt_file():
    """save_core_option creates a .opt file with the option persisted."""
    from wall.config_service import save_core_option, load_core_options

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_core_option("game1", "lr-snes9x2002", "snes9x_region", "PAL", base_dir=base)

        loaded = load_core_options("game1", "lr-snes9x2002", base_dir=base)
        assert loaded["snes9x_region"] == "PAL"


def test_save_core_option_merges_preserving_other_keys():
    """Writing one key preserves other keys already in the .opt file."""
    from wall.config_service import save_core_option, load_core_options

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        save_core_option("game1", "lr-snes9x2002", "snes9x_region", "PAL", base_dir=base)
        save_core_option("game1", "lr-snes9x2002", "snes9x_blargg", "rgb", base_dir=base)

        loaded = load_core_options("game1", "lr-snes9x2002", base_dir=base)
        assert loaded["snes9x_region"] == "PAL"
        assert loaded["snes9x_blargg"] == "rgb"


# --- Layer 5: UI component row type contracts ---


def test_editable_dropdown_row_exposes_on_change():
    """editable_dropdown_row returns a Row with a Dropdown that fires on_change."""
    import flet as ft
    from wall.components import editable_dropdown_row

    calls: list[str] = []
    row = editable_dropdown_row(
        "Region",
        "NTSC",
        ("Auto", "NTSC", "PAL"),
        on_change=lambda v: calls.append(v),
        tooltip="Console Region",
    )

    assert isinstance(row, ft.Row)
    # Find the Dropdown control
    dropdown = None
    for ctrl in row.controls:
        if isinstance(ctrl, ft.Dropdown):
            dropdown = ctrl
            break
    assert dropdown is not None
    assert dropdown.value == "NTSC"
    assert len(dropdown.options) == 3


def test_readonly_value_row_has_no_callback():
    """readonly_value_row returns a Row with no interactive controls."""
    import flet as ft
    from wall.components import readonly_value_row

    row = readonly_value_row("Unknown Opt", "bar", tooltip="test_key")
    assert isinstance(row, ft.Row)
    # No Dropdown, Switch, or other interactive control
    for ctrl in row.controls:
        assert not isinstance(ctrl, (ft.Dropdown, ft.Switch))
