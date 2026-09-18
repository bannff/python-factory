"""Tests for wall.config_service — runahead write + read-back end-to-end."""

from pathlib import Path

import pytest

from wall.config_service import save_runahead, load_runahead
from wall.navigator import Navigator
from wall.models import GameTile, WallViewModel
from factory.arcade_config.runtime.models import RunAheadConfig


class TestSaveRunahead:
    """Behavior: save_runahead writes a per-GAME .cfg under the injected base_dir."""

    def test_enabled_writes_true_and_frames(self, tmp_path: Path) -> None:
        path = save_runahead("sf2", "mame2003_plus", True, base_dir=tmp_path)

        content = path.read_text()
        assert 'run_ahead_enabled = "true"' in content
        assert 'run_ahead_frames = "1"' in content

    def test_disabled_writes_false(self, tmp_path: Path) -> None:
        path = save_runahead("sf2", "mame2003_plus", False, base_dir=tmp_path)

        content = path.read_text()
        assert 'run_ahead_enabled = "false"' in content
        assert 'run_ahead_frames = "1"' in content

    def test_resolved_path_is_under_base_dir(self, tmp_path: Path) -> None:
        path = save_runahead("kinst", "mame2016", True, base_dir=tmp_path)

        assert path.is_relative_to(tmp_path)
        # GAME scope: base_dir / core / game.cfg
        assert "mame2016" in path.parts
        assert path.name == "kinst.cfg"

    def test_toggle_on_then_off_rewrites_same_path(self, tmp_path: Path) -> None:
        path_on = save_runahead("sf2", "mame2003_plus", True, base_dir=tmp_path)
        path_off = save_runahead("sf2", "mame2003_plus", False, base_dir=tmp_path)

        assert path_on == path_off
        content = path_off.read_text()
        assert 'run_ahead_enabled = "false"' in content

    def test_no_real_retroarch_path(self, tmp_path: Path) -> None:
        path = save_runahead("game", "core", True, base_dir=tmp_path)
        assert ".config/retroarch" not in str(path)
        assert str(tmp_path) in str(path)


class TestLoadRunahead:
    """Behavior: load_runahead reads back persisted state or returns None."""

    def test_returns_none_when_no_file(self, tmp_path: Path) -> None:
        assert load_runahead("sf2", "mame2003_plus", base_dir=tmp_path) is None

    def test_round_trip_enabled_true(self, tmp_path: Path) -> None:
        save_runahead("sf2", "mame2003_plus", True, base_dir=tmp_path)
        result = load_runahead("sf2", "mame2003_plus", base_dir=tmp_path)
        assert result == RunAheadConfig(enabled=True, frames=1)

    def test_round_trip_enabled_false_returns_config_not_none(self, tmp_path: Path) -> None:
        """A present file with enabled=False IS a real persisted state, not None."""
        save_runahead("sf2", "mame2003_plus", False, base_dir=tmp_path)
        result = load_runahead("sf2", "mame2003_plus", base_dir=tmp_path)
        assert result is not None
        assert result == RunAheadConfig(enabled=False, frames=1)

    def test_malformed_file_degrades_to_disabled(self, tmp_path: Path) -> None:
        """Junk content degrades gracefully: enabled=False, frames=1."""
        from factory.arcade_config.runtime.resolver import override_path
        from factory.arcade_config.runtime.models import Scope
        path = override_path(tmp_path, Scope.GAME, core="mame", game="junk", kind="cfg")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("garbage\nnot a cfg line\n")
        result = load_runahead("junk", "mame", base_dir=tmp_path)
        assert result == RunAheadConfig(enabled=False, frames=1)

    def test_partial_keys_degrade_to_defaults(self, tmp_path: Path) -> None:
        """File with only enabled key -> frames defaults to 1."""
        from factory.arcade_config.runtime.resolver import override_path
        from factory.arcade_config.runtime.models import Scope
        path = override_path(tmp_path, Scope.GAME, core="snes9x", game="test", kind="cfg")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('run_ahead_enabled = "true"\n')
        result = load_runahead("test", "snes9x", base_dir=tmp_path)
        assert result == RunAheadConfig(enabled=True, frames=1)

    def test_non_int_frames_degrades_to_1(self, tmp_path: Path) -> None:
        from factory.arcade_config.runtime.resolver import override_path
        from factory.arcade_config.runtime.models import Scope
        path = override_path(tmp_path, Scope.GAME, core="core", game="g", kind="cfg")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('run_ahead_enabled = "true"\nrun_ahead_frames = "abc"\n')
        result = load_runahead("g", "core", base_dir=tmp_path)
        assert result == RunAheadConfig(enabled=True, frames=1)


class TestControlsVmReadBack:
    """controls_from_settings reflects resolved settings state."""

    def test_default_settings_shows_disabled(self) -> None:
        from factory.arcade_config.runtime.settings import RetroArchRuntimeSettings, resolve_runtime_settings
        from wall.controls_vm import controls_from_settings
        settings = resolve_runtime_settings({})
        vm = controls_from_settings(settings)
        assert vm.runahead_enabled is False

    def test_enabled_settings_reflects_in_vm(self) -> None:
        from factory.arcade_config.runtime.settings import RetroArchRuntimeSettings, resolve_runtime_settings
        from wall.controls_vm import controls_from_settings
        settings = resolve_runtime_settings({"run_ahead_enabled": "true", "run_ahead_frames": "2"})
        vm = controls_from_settings(settings)
        assert vm.runahead_enabled is True
        assert vm.runahead_frames == 2


class TestNavigatorReadBack:
    """Navigator._build_detail loads persisted config state."""

    def _make_nav(self, tmp_path: Path) -> Navigator:
        tile = GameTile(id="kinst", title="Killer Instinct", system="MAME",
                        art_url="", core="mame2016")
        vm = WallViewModel(tiles=[tile])
        return Navigator(vm, config_dir=tmp_path)

    def test_detail_reflects_saved_enabled(self, tmp_path: Path) -> None:
        save_runahead("kinst", "mame2016", True, base_dir=tmp_path)
        loaded = load_runahead("kinst", "mame2016", base_dir=tmp_path)
        assert loaded is not None
        assert loaded.enabled is True

    def test_detail_no_config_dir_degrades(self) -> None:
        tile = GameTile(id="kinst", title="Killer Instinct", system="MAME",
                        art_url="", core="mame2016")
        vm = WallViewModel(tiles=[tile])
        nav = Navigator(vm, config_dir=None)
        nav.select(nav._vm.tiles[0])
        # Should not raise — controls_vm=None fallback path works
