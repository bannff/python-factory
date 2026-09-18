"""Tests for control_plane.library_manager_tools — MCP tool registration and behavior."""

import asyncio
from pathlib import Path

import pytest
from factory.mcp_utils.runtime.tool_catalog import ToolCatalog

from wall.models import GameTile
from control_plane.context import ServerContext
from control_plane.library_manager_tools import register


def _make_context(tiles: list[GameTile] | None = None, media_root: Path | None = None) -> ServerContext:
    """Build a minimal ServerContext for testing."""
    return ServerContext(
        tiles=tiles or [],
        system="snes",
        media_root=media_root or Path("/tmp/fake_media"),
        roms_root=Path("/tmp/fake_roms"),
        launcher=None,
        transport_factory=None,
    )


def _make_tile(id: str, art_url: str = "") -> GameTile:
    return GameTile(id=id, title=id, system="SNES", art_url=art_url)


def _get_tool(mcp: ToolCatalog, name: str):
    """Get a tool by name from the server."""
    tools = asyncio.run(mcp.list_tools())
    return next((t for t in tools if t.name == name), None)


class TestScanDirectoryTool:
    """scan_directory MCP tool preview behavior."""

    def test_scan_returns_counts(self, tmp_path):
        """scan_directory returns matched/unmatched/metadata_only counts."""
        (tmp_path / "zelda.sfc").write_bytes(b"")
        (tmp_path / "mario.sfc").write_bytes(b"")
        (tmp_path / "ignore.txt").write_bytes(b"")

        tiles = [_make_tile("snes-zelda", art_url="snes/boxart/zelda.png")]
        ctx = _make_context(tiles=tiles, media_root=tmp_path)

        mcp = ToolCatalog("test")
        register(mcp, context=ctx)

        tool = _get_tool(mcp, "scan_directory")
        assert tool is not None
        result = tool.fn(path=str(tmp_path))
        assert result["total"] == 2
        assert result["matched"] == 1  # zelda (has art)
        assert result["unmatched"] == 1  # mario (new)

    def test_scan_nonexistent_returns_error(self):
        """scan_directory returns error for nonexistent path."""
        ctx = _make_context()
        mcp = ToolCatalog("test")
        register(mcp, context=ctx)

        tool = _get_tool(mcp, "scan_directory")
        result = tool.fn(path="/nonexistent/path")
        assert "error" in result


class TestImportGamesTool:
    """import_games MCP tool write behavior."""

    def test_import_writes_new_entries(self, tmp_path):
        """import_games writes only unmatched ROMs to gamelist."""
        roms_dir = tmp_path / "roms"
        roms_dir.mkdir()
        (roms_dir / "new_game.sfc").write_bytes(b"")

        media_root = tmp_path / "media"
        media_root.mkdir()

        ctx = _make_context(tiles=[], media_root=media_root)
        mcp = ToolCatalog("test")
        register(mcp, context=ctx)

        tool = _get_tool(mcp, "import_games")
        assert tool is not None
        result = tool.fn(path=str(roms_dir))
        assert result["imported_count"] == 1
        assert "gamelist.xml" in result["gamelist_path"]

        # Verify the file was written
        gl = Path(result["gamelist_path"])
        assert gl.exists()
        assert "./new_game.sfc" in gl.read_text()

    def test_import_no_new_roms(self, tmp_path):
        """import_games returns 0 when all ROMs already in library."""
        roms_dir = tmp_path / "roms"
        roms_dir.mkdir()
        (roms_dir / "zelda.sfc").write_bytes(b"")

        tiles = [_make_tile("snes-zelda")]
        ctx = _make_context(tiles=tiles, media_root=tmp_path)
        mcp = ToolCatalog("test")
        register(mcp, context=ctx)

        tool = _get_tool(mcp, "import_games")
        result = tool.fn(path=str(roms_dir))
        assert result["imported_count"] == 0
        assert "already in gamelist" in result["message"]
