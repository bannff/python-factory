"""Tests for Agent Slice 1 — library grounding.

Asserts:
- list_games returns ONLY curated/playable tiles (art_url non-empty + playable=True)
- search_games also respects the curated filter
- library_summary returns correct counts matching the curated set
- library_summary tool is registered on the server
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wall.models import GameTile
from control_plane.library_tools import _is_curated, register
from control_plane.context import ServerContext
from control_plane.server import build_server
from factory.mcp_utils.runtime.tool_catalog import ToolCatalog


# ---------------------------------------------------------------------------
# Fixtures: mixed tiles (curated + non-curated)
# ---------------------------------------------------------------------------

def _make_tile(
    id: str,
    title: str,
    system: str = "SNES",
    art_url: str = "",
    playable: bool = True,
    rom_path: str = "/roms/test.sfc",
) -> GameTile:
    return GameTile(
        id=id,
        title=title,
        system=system,
        art_url=art_url,
        playable=playable,
        rom_path=rom_path,
    )


# 5 curated (art + playable) + 4 non-curated
MIXED_TILES = [
    _make_tile("snes-mario", "Super Mario World", art_url="snes/mario.png"),
    _make_tile("snes-zelda", "Zelda: LTTP", art_url="snes/zelda.png"),
    _make_tile("snes-metroid", "Super Metroid", art_url="snes/metroid.png"),
    _make_tile("n64-mario64", "Super Mario 64", system="N64", art_url="n64/mario64.png"),
    _make_tile("n64-zelda64", "Zelda: OoT", system="N64", art_url="n64/zelda64.png"),
    # --- non-curated below ---
    _make_tile("snes-noart", "No Art Game", art_url=""),  # missing art
    _make_tile("snes-norom", "No ROM", art_url="snes/norom.png", playable=False),  # unplayable
    _make_tile("snes-both", "Both Missing", art_url="", playable=False),  # both
    _make_tile("snes-emptyart", "Empty Art", art_url=""),  # empty string art
]


@pytest.fixture()
def ctx() -> ServerContext:
    return ServerContext(
        tiles=list(MIXED_TILES),
        system="snes",
        media_root=Path("/fake/media"),
        roms_root=Path("/fake/roms"),
        launcher=None,
        transport_factory=None,
    )


@pytest.fixture()
def mcp_server(ctx: ServerContext) -> ToolCatalog:
    mcp = ToolCatalog("test-openarcade")
    register(mcp, context=ctx)
    return mcp


def _get_tool(mcp_server: ToolCatalog, name: str):
    tools = asyncio.run(mcp_server.list_tools())
    return next((t for t in tools if t.name == name), None)


# ---------------------------------------------------------------------------
# _is_curated unit tests
# ---------------------------------------------------------------------------

class TestIsCurated:
    def test_curated_with_art_and_playable(self):
        t = _make_tile("x", "X", art_url="snes/x.png", playable=True)
        assert _is_curated(t) is True

    def test_not_curated_missing_art(self):
        t = _make_tile("x", "X", art_url="", playable=True)
        assert _is_curated(t) is False

    def test_not_curated_not_playable(self):
        t = _make_tile("x", "X", art_url="snes/x.png", playable=False)
        assert _is_curated(t) is False

    def test_not_curated_both_missing(self):
        t = _make_tile("x", "X", art_url="", playable=False)
        assert _is_curated(t) is False


# ---------------------------------------------------------------------------
# list_games grounding
# ---------------------------------------------------------------------------

class TestListGamesGrounding:
    def test_returns_only_curated_entries(self, mcp_server):
        tool = _get_tool(mcp_server, "list_games")
        result = tool.fn()
        assert len(result) == 5  # exactly the 5 curated tiles
        ids = {g["id"] for g in result}
        assert ids == {"snes-mario", "snes-zelda", "snes-metroid", "n64-mario64", "n64-zelda64"}

    def test_excludes_tiles_without_art(self, mcp_server):
        tool = _get_tool(mcp_server, "list_games")
        result = tool.fn()
        ids = {g["id"] for g in result}
        assert "snes-noart" not in ids
        assert "snes-emptyart" not in ids

    def test_excludes_unplayable_tiles(self, mcp_server):
        tool = _get_tool(mcp_server, "list_games")
        result = tool.fn()
        ids = {g["id"] for g in result}
        assert "snes-norom" not in ids
        assert "snes-both" not in ids


# ---------------------------------------------------------------------------
# search_games grounding
# ---------------------------------------------------------------------------

class TestSearchGamesGrounding:
    def test_search_returns_only_curated(self, mcp_server):
        """Even when query matches a non-curated tile title, it's excluded."""
        tool = _get_tool(mcp_server, "search_games")
        # "No Art Game" matches "art" but is non-curated
        result = tool.fn(query="mario")
        ids = {g["id"] for g in result}
        assert "snes-mario" in ids
        assert "n64-mario64" in ids

    def test_search_excludes_non_curated_match(self, mcp_server):
        tool = _get_tool(mcp_server, "search_games")
        # "No Art Game" would match "No" but it's non-curated
        result = tool.fn(query="No")
        ids = {g["id"] for g in result}
        assert "snes-noart" not in ids
        assert "snes-norom" not in ids


# ---------------------------------------------------------------------------
# library_summary
# ---------------------------------------------------------------------------

class TestLibrarySummary:
    def test_returns_correct_total(self, mcp_server):
        tool = _get_tool(mcp_server, "library_summary")
        result = tool.fn()
        assert result["total_curated_games"] == 5

    def test_returns_correct_systems(self, mcp_server):
        tool = _get_tool(mcp_server, "library_summary")
        result = tool.fn()
        assert result["systems"] == ["N64", "SNES"]

    def test_returns_correct_per_system_counts(self, mcp_server):
        tool = _get_tool(mcp_server, "library_summary")
        result = tool.fn()
        assert result["per_system"] == {"N64": 2, "SNES": 3}

    def test_counts_match_list_games(self, mcp_server):
        """library_summary.total must equal len(list_games())."""
        list_tool = _get_tool(mcp_server, "list_games")
        summary_tool = _get_tool(mcp_server, "library_summary")
        games = list_tool.fn()
        summary = summary_tool.fn()
        assert summary["total_curated_games"] == len(games)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class TestLibrarySummaryRegistration:
    def test_library_summary_registered(self, mcp_server):
        tools = asyncio.run(mcp_server.list_tools())
        tool_names = {t.name for t in tools}
        assert "library_summary" in tool_names


# ---------------------------------------------------------------------------
# Full server integration (tmp_path)
# ---------------------------------------------------------------------------

class TestFullServerGrounding:
    """Integration: build_server with mixed data, verify grounding."""

    @pytest.fixture()
    def grounded_server(self, tmp_path):
        """Build server with a gamelist containing curated + uncurated games."""
        gamelist = tmp_path / "gamelists" / "snes" / "gamelist.xml"
        gamelist.parent.mkdir(parents=True)
        gamelist.write_text(
            '<?xml version="1.0"?>\n<gameList>\n'
            '  <game><path>./roms/curated.sfc</path><name>Curated Game</name>'
            '    <image>./images/curated.png</image></game>\n'
            '  <game><path>./roms/uncurated.sfc</path><name>Uncurated Game</name></game>\n'
            '</gameList>\n'
        )
        # Create cover art for 'curated' only
        img_dir = tmp_path / "snes" / "images"
        img_dir.mkdir(parents=True)
        (img_dir / "curated.png").write_bytes(b"PNG")

        # Create ROM for 'curated' only
        roms_dir = tmp_path / "snes" / "roms"
        roms_dir.mkdir(parents=True)
        (roms_dir / "curated.sfc").write_bytes(b"ROM")

        return build_server(
            gamelist_path=gamelist,
            system="snes",
            media_root=tmp_path,
            roms_root=roms_dir,
        )

    def test_list_games_returns_only_curated(self, grounded_server):
        tool = _get_tool(grounded_server, "list_games")
        result = tool.fn()
        # Only "Curated Game" has art + ROM
        assert len(result) == 1
        assert result[0]["title"] == "Curated Game"

    def test_library_summary_matches(self, grounded_server):
        tool = _get_tool(grounded_server, "library_summary")
        result = tool.fn()
        assert result["total_curated_games"] == 1
        assert result["per_system"] == {"SNES": 1}
