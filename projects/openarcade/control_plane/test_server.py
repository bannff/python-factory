"""Behavior tests for control_plane.server — uses real SNES gamelist + Pi configs."""

import asyncio
from pathlib import Path

import pytest

from control_plane.server import build_server


_GAMELIST = Path("/tmp/oa_arcade/gamelists/snes/gamelist.xml")
_MEDIA_ROOT = Path("/tmp/oa_arcade")
_SYSTEM = "snes"


@pytest.fixture()
def server():
    """Build a real server against the SNES gamelist on disk."""
    if not _GAMELIST.exists():
        pytest.skip("SNES gamelist not on disk")
    return build_server(gamelist_path=_GAMELIST, system=_SYSTEM, media_root=_MEDIA_ROOT)


def _get_tool(server, name: str):
    """Get a FunctionTool by name from the FastMCP server."""
    tools = asyncio.run(server.list_tools())
    return next((t for t in tools if t.name == name), None)


class TestToolRegistration:
    def test_all_tools_registered(self, server):
        """21 tools: library(4) + launch(1) + settings(4) + systems(1) + controllers(2) + library_manager(2) + information(1) + cores(2) + assistant(2) + curation(1) + knowledge(1)."""
        tools = asyncio.run(server.list_tools())
        tool_names = {t.name for t in tools}
        expected = {
            "list_games", "search_games", "get_game", "library_summary",
            "launch_game",
            "get_global_settings", "set_setting", "get_controls", "set_runahead",
            "list_systems",
            "get_remap", "set_remap",
            "scan_directory", "import_games",
            "get_system_info",
            "list_cores", "install_core_tool",
            "get_assistant_config", "set_assistant_config",
            "curate_art",
            "knowledge_search",
        }
        assert tool_names == expected


class TestListGames:
    def test_returns_nonempty_dicts_with_required_keys(self, server):
        tool = _get_tool(server, "list_games")
        result = tool.fn()
        assert len(result) > 0
        first = result[0]
        assert "id" in first
        assert "title" in first
        assert "system" in first


class TestSearchGames:
    def test_search_narrows_results(self, server):
        all_games = _get_tool(server, "list_games").fn()
        if len(all_games) == 0:
            pytest.skip("No curated games on disk — cannot test search narrowing")
        # Pick a title word from a known curated game
        first_title = all_games[0]["title"]
        word = first_title.split()[0]
        results = _get_tool(server, "search_games").fn(query=word)
        assert len(results) > 0
        assert len(results) <= len(all_games)
        assert all(word.lower() in g["title"].lower() for g in results)


class TestGetControls:
    def test_returns_real_snes_settings(self, server):
        tool = _get_tool(server, "get_controls")
        result = tool.fn()
        assert result["shader_name"] == "crt-pi"
        assert result["run_ahead_enabled"] is False
        assert result["core"] == "lr-snes9x2002"
        assert "video_smooth" in result


class TestGetGlobalSettings:
    """get_global_settings returns the same resolved data as get_controls."""

    def test_returns_real_snes_settings(self, server):
        tool = _get_tool(server, "get_global_settings")
        result = tool.fn()
        assert result["core"] == "lr-snes9x2002"
        assert result["shader_name"] == "crt-pi"
        assert "run_ahead_enabled" in result

    def test_returns_dict_with_all_keys(self, server):
        tool = _get_tool(server, "get_global_settings")
        result = tool.fn()
        expected_keys = {"core", "run_ahead_enabled", "run_ahead_frames", "shader_enabled", "shader_name", "video_smooth"}
        assert expected_keys == set(result.keys())


class TestSetSetting:
    """set_setting writes a global override and never clobbers retroarch_cfg."""

    @pytest.fixture()
    def minimal_server(self, tmp_path):
        gamelist = tmp_path / "gamelists" / "snes" / "gamelist.xml"
        gamelist.parent.mkdir(parents=True)
        gamelist.write_text(
            '<?xml version="1.0"?>\n<gameList>\n'
            '  <game id="./roms/test.sfc" source="screenscraper.fr">\n'
            '    <path>./roms/test.sfc</path>\n'
            '    <name>Test Game</name>\n'
            '  </game>\n'
            '</gameList>\n'
        )
        cfg_dir = tmp_path / "retroarch_cfg" / "snes"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')
        return build_server(gamelist_path=gamelist, system="snes", media_root=tmp_path)

    def test_set_setting_writes_override(self, minimal_server, tmp_path):
        tool = _get_tool(minimal_server, "set_setting")
        result = tool.fn(key="video_smooth", value="true")
        assert result["key"] == "video_smooth"
        assert result["value"] == "true"
        written = Path(result["written_path"])
        assert written.exists()
        assert "retroarch_overrides" in str(written)
        assert "retroarch_cfg" not in str(written)

    def test_set_setting_no_clobber_invariant(self, minimal_server, tmp_path):
        """Override path must not contain '.config/retroarch' (the no-clobber test)."""
        tool = _get_tool(minimal_server, "set_setting")
        result = tool.fn(key="audio_volume", value="5")
        written = Path(result["written_path"])
        assert ".config/retroarch" not in str(written)

    def test_set_setting_merges_keys(self, minimal_server, tmp_path):
        """Multiple set_setting calls merge rather than clobber."""
        tool = _get_tool(minimal_server, "set_setting")
        tool.fn(key="video_smooth", value="true")
        tool.fn(key="audio_volume", value="3")
        written = Path(tool.fn(key="video_vsync", value="false")["written_path"])
        content = written.read_text()
        assert "video_smooth" in content
        assert "audio_volume" in content
        assert "video_vsync" in content


class TestListSystems:
    """list_systems returns the sorted distinct systems in the library."""

    def test_returns_nonempty_list(self, server):
        tool = _get_tool(server, "list_systems")
        result = tool.fn()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_returns_sorted_strings(self, server):
        tool = _get_tool(server, "list_systems")
        result = tool.fn()
        assert result == sorted(result)
        assert all(isinstance(s, str) for s in result)


class TestSetRunahead:
    """Behavior: set_runahead writes a per-game override under retroarch_overrides."""

    @pytest.fixture()
    def minimal_server(self, tmp_path):
        gamelist = tmp_path / "gamelists" / "snes" / "gamelist.xml"
        gamelist.parent.mkdir(parents=True)
        gamelist.write_text(
            '<?xml version="1.0"?>\n<gameList>\n'
            '  <game id="./roms/test.sfc" source="screenscraper.fr">\n'
            '    <path>./roms/test.sfc</path>\n'
            '    <name>Test Game</name>\n'
            '  </game>\n'
            '</gameList>\n'
        )
        cfg_dir = tmp_path / "retroarch_cfg" / "snes"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')
        return build_server(gamelist_path=gamelist, system="snes", media_root=tmp_path)

    def test_set_runahead_tool_registered(self, server):
        tools = asyncio.run(server.list_tools())
        tool_names = {t.name for t in tools}
        assert "set_runahead" in tool_names

    def test_set_runahead_enable_writes_override(self, minimal_server, tmp_path):
        tool = _get_tool(minimal_server, "set_runahead")
        result = tool.fn(game_id="test.sfc", enabled=True)
        assert result["game_id"] == "test.sfc"
        assert result["run_ahead_enabled"] is True
        assert result["core"] == "lr-snes9x2002"
        written = Path(result["written_path"])
        assert written.exists()
        assert "retroarch_overrides" in str(written)
        assert "retroarch_cfg" not in str(written)
        content = written.read_text()
        assert 'run_ahead_enabled = "true"' in content

    def test_set_runahead_disable_writes_false(self, minimal_server, tmp_path):
        tool = _get_tool(minimal_server, "set_runahead")
        result = tool.fn(game_id="test.sfc", enabled=False)
        assert result["run_ahead_enabled"] is False
        written = Path(result["written_path"])
        assert written.exists()
        content = written.read_text()
        assert 'run_ahead_enabled = "false"' in content
