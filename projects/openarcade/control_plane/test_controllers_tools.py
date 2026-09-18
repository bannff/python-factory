"""Tests for f385v: Controllers MCP tools — get_remap, set_remap.

Behavior-named, AAA structure. Validates:
- get_remap returns resolved 16-row VM for a game
- set_remap writes SPARSE .rmp (only changed key present)
- set_remap rejects invalid button/target
- no-clobber: written path under overrides dir, not real config
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from factory.arcade_config.runtime.input_remaps import RETROPAD_BUTTON_ORDER
from wall.config_service import save_input_remap, load_input_remaps


# --- Fixtures ---


@pytest.fixture()
def remap_dir():
    """Temporary override dir for remap writes."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # Create a minimal system config so resolve_core works
        cfg_root = base / "retroarch_cfg" / "snes"
        cfg_root.mkdir(parents=True)
        (cfg_root / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')
        # Global cfg (needed for controls resolution path)
        all_cfg = base / "retroarch_cfg" / "all"
        all_cfg.mkdir(parents=True)
        (all_cfg / "retroarch.cfg").write_text("run_ahead_enabled = false\n")
        yield base


@pytest.fixture()
def make_context(remap_dir):
    """Build a minimal ServerContext with one SNES game tile."""
    from wall.models import GameTile
    from control_plane.context import ServerContext

    tile = GameTile(
        id="super-mario",
        title="Super Mario World",
        system="snes",
        art_url="",
        rom_path="/roms/snes/smw.sfc",
        core="lr-snes9x2002",
    )

    return ServerContext(
        tiles=[tile],
        system="snes",
        media_root=remap_dir,
        roms_root=remap_dir / "snes",
        launcher=None,
        transport_factory=None,
    )


@pytest.fixture()
def tools(make_context):
    """Build a ToolCatalog server and return tool function lookup."""
    import asyncio
    from factory.mcp_utils.runtime.tool_catalog import ToolCatalog
    from control_plane.controllers_tools import register

    mcp = ToolCatalog("test-controllers")
    register(mcp, context=make_context)

    def get_tool(name: str):
        tool_list = asyncio.run(mcp.list_tools())
        t = next((t for t in tool_list if t.name == name), None)
        assert t is not None, f"Tool {name} not found"
        return t

    return get_tool


# --- get_remap ---


class TestGetRemap:
    def test_returns_all_16_rows_at_identity(self, tools):
        """get_remap for a game with no overrides returns 16 identity rows."""
        get_remap = tools("get_remap")
        result = get_remap.fn(game_id="super-mario")

        assert "error" not in result
        assert result["game_id"] == "super-mario"
        rows = result["rows"]
        assert len(rows) == 16
        # All identity (no overrides yet)
        for row in rows:
            assert row["button"] == row["current_target"]
            assert len(row["choices"]) == 16

    def test_returns_error_for_unknown_game(self, tools):
        """get_remap rejects unknown game_id with clear error."""
        get_remap = tools("get_remap")
        result = get_remap.fn(game_id="nonexistent")

        assert "error" in result
        assert "not found" in result["error"].lower()


# --- set_remap ---


class TestSetRemap:
    def test_writes_sparse_rmp_only_changed_key(self, tools, remap_dir):
        """set_remap writes only the changed button (sparse .rmp)."""
        set_remap = tools("set_remap")
        result = set_remap.fn(game_id="super-mario", button="a", target="b")

        assert "error" not in result
        assert result["button"] == "a"
        assert result["target"] == "b"
        written_path = Path(result["written_path"])
        assert written_path.exists()

        # SPARSE: only 1 key written
        content = written_path.read_text()
        lines = [l for l in content.strip().splitlines() if l.strip()]
        assert len(lines) == 1
        assert "input_player1_a" in lines[0]

    def test_rejects_invalid_button(self, tools):
        """set_remap returns error for invalid button name."""
        set_remap = tools("set_remap")
        result = set_remap.fn(game_id="super-mario", button="turbo_fire", target="a")

        assert "error" in result
        assert "invalid button" in result["error"].lower()

    def test_rejects_invalid_target(self, tools):
        """set_remap returns error for invalid target name."""
        set_remap = tools("set_remap")
        result = set_remap.fn(game_id="super-mario", button="a", target="mega_punch")

        assert "error" in result
        assert "invalid target" in result["error"].lower()

    def test_no_clobber_writes_under_overrides(self, tools, remap_dir):
        """Written path is under retroarch_overrides, never retroarch_cfg."""
        set_remap = tools("set_remap")
        result = set_remap.fn(game_id="super-mario", button="x", target="y")

        written_path = Path(result["written_path"])
        assert "retroarch_overrides" in str(written_path)
        assert "retroarch_cfg" not in str(written_path)

    def test_identity_remap_removes_key(self, tools, remap_dir):
        """Setting button->itself (identity) removes the key from .rmp."""
        set_remap = tools("set_remap")
        # First write a non-identity
        set_remap.fn(game_id="super-mario", button="a", target="b")
        # Now set identity
        result = set_remap.fn(game_id="super-mario", button="a", target="a")

        assert "error" not in result
        written_path = Path(result["written_path"])
        # File should not exist (all keys removed = deleted)
        assert not written_path.exists()

    def test_returns_error_for_unknown_game(self, tools):
        """set_remap rejects unknown game_id."""
        set_remap = tools("set_remap")
        result = set_remap.fn(game_id="bogus", button="a", target="b")

        assert "error" in result
        assert "not found" in result["error"].lower()
