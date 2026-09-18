"""Tests for control_plane.information_query — behavior-named, AAA structure."""

from pathlib import Path

import pytest

from wall.models import GameTile
from control_plane.information_query import get_system_info, _parse_retroarch_version


def _tile(system: str = "snes", art: str = "", title: str = "Game") -> GameTile:
    return GameTile(id=f"{system}-{title.lower()}", title=title, system=system, art_url=art)


@pytest.fixture()
def tmp_media(tmp_path: Path) -> Path:
    """Set up a minimal media_root with layered cfgs."""
    cfg_root = tmp_path / "retroarch_cfg"
    (cfg_root / "all").mkdir(parents=True)
    (cfg_root / "all" / "retroarch.cfg").write_text("# RetroArch 1.17.0\nvideo_smooth = false\n")
    (cfg_root / "snes").mkdir()
    (cfg_root / "snes" / "retroarch.cfg").write_text("shader = crt-pi\n")
    (cfg_root / "snes" / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')
    # Game-level override
    overrides = tmp_path / "retroarch_overrides" / "snes"
    overrides.mkdir(parents=True)
    (overrides / "some_game.cfg").write_text("run_ahead_enabled = true\n")
    return tmp_path


class TestGetSystemInfoReturnsHonestFields:
    def test_returns_core_and_game_count(self, tmp_media: Path):
        tiles = [_tile("snes", title="A"), _tile("snes", title="B"), _tile("n64", title="C")]
        result = get_system_info(tiles, tmp_media, system="snes")
        assert result["system"] == "snes"
        assert result["game_count"] == 2
        assert result["core"] == "lr-snes9x2002"

    def test_returns_supported_extensions(self, tmp_media: Path):
        tiles = [_tile("snes")]
        result = get_system_info(tiles, tmp_media, system="snes")
        assert ".sfc" in result["supported_extensions"]
        assert ".smc" in result["supported_extensions"]
        assert ".zip" in result["supported_extensions"]

    def test_returns_art_coverage(self, tmp_media: Path):
        tiles = [
            _tile("snes", art="http://art/1.png", title="A"),
            _tile("snes", art="", title="B"),
            _tile("snes", art="http://art/3.png", title="C"),
        ]
        result = get_system_info(tiles, tmp_media, system="snes")
        assert result["art_coverage"] == "2/3"

    def test_returns_config_layers_present(self, tmp_media: Path):
        tiles = [_tile("snes")]
        result = get_system_info(tiles, tmp_media, system="snes")
        assert "global" in result["config_layers_present"]
        assert "system" in result["config_layers_present"]
        assert "game" in result["config_layers_present"]

    def test_returns_override_dir(self, tmp_media: Path):
        tiles = [_tile("snes")]
        result = get_system_info(tiles, tmp_media, system="snes")
        assert "retroarch_overrides" in result["override_dir"]

    def test_returns_retroarch_version_when_parseable(self, tmp_media: Path):
        tiles = [_tile("snes")]
        result = get_system_info(tiles, tmp_media, system="snes")
        assert result["retroarch_version"] == "1.17.0"

    def test_returns_systems_list(self, tmp_media: Path):
        tiles = [_tile("snes", title="A"), _tile("n64", title="B")]
        result = get_system_info(tiles, tmp_media, system="snes")
        assert "n64" in result["systems"]
        assert "snes" in result["systems"]


class TestOmitsUnsourceableFields:
    def test_no_fake_keys_present(self, tmp_media: Path):
        tiles = [_tile("snes")]
        result = get_system_info(tiles, tmp_media, system="snes")
        forbidden = {"firmware", "cpu", "host", "playtime", "last_played", "perf_counters", "core_version"}
        assert forbidden.isdisjoint(result.keys())


class TestDefaultSystem:
    def test_none_system_uses_default(self, tmp_media: Path):
        tiles = [_tile("snes", title="A"), _tile("n64", title="B")]
        result = get_system_info(tiles, tmp_media, system=None, default_system="snes")
        assert result["system"] == "snes"
        assert result["game_count"] == 1


class TestGameCountPerSystem:
    def test_counts_only_matching_system(self, tmp_media: Path):
        tiles = [_tile("snes", title="A"), _tile("snes", title="B"), _tile("n64", title="C")]
        result = get_system_info(tiles, tmp_media, system="n64")
        assert result["game_count"] == 1


class TestParseRetroArchVersion:
    def test_parses_standard_header(self, tmp_path: Path):
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("# RetroArch 1.19.1\nvideo_smooth = false\n")
        assert _parse_retroarch_version(cfg) == "1.19.1"

    def test_returns_empty_for_no_header(self, tmp_path: Path):
        cfg = tmp_path / "retroarch.cfg"
        cfg.write_text("video_smooth = false\n")
        assert _parse_retroarch_version(cfg) == ""

    def test_returns_empty_for_missing_file(self, tmp_path: Path):
        cfg = tmp_path / "nonexistent.cfg"
        assert _parse_retroarch_version(cfg) == ""

    def test_omits_version_key_when_not_parseable(self, tmp_path: Path):
        """When version can't be parsed, the key should not appear in results."""
        media = tmp_path / "media"
        cfg_root = media / "retroarch_cfg"
        (cfg_root / "all").mkdir(parents=True)
        (cfg_root / "all" / "retroarch.cfg").write_text("video_smooth = false\n")
        (media / "retroarch_overrides").mkdir()
        tiles = [_tile("snes")]
        result = get_system_info(tiles, media, system="snes")
        assert "retroarch_version" not in result
