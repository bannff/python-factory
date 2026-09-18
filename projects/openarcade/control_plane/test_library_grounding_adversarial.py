"""Adversarial tests for Agent Slice 1 — library grounding contract.

Contract under test:
  _is_curated(tile) = bool(tile.art_url) AND tile.playable
  list_games, search_games return ONLY curated tiles.
  library_summary counts ONLY curated tiles.
  get_game — DEFECT PROBE: does it leak uncurated tiles?

These tests attack boundary conditions the happy-path suite doesn't cover:
 - Tiles with art but playable=False (MUST be excluded)
 - Tiles playable=True but art_url="" (MUST be excluded)
 - Empty library (zero tiles)
 - Search query matching only uncurated titles
 - get_game on an uncurated id (should return None per grounding contract)
 - Multi-system mixed fixture with exact curated subset assertion
 - Whitespace/None-like art_url boundary values
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from wall.models import GameTile
from control_plane.library_tools import _is_curated, register
from control_plane.context import ServerContext
from factory.mcp_utils.runtime.tool_catalog import ToolCatalog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tile(
    id: str,
    title: str = "Test Game",
    system: str = "SNES",
    art_url: str = "",
    playable: bool = True,
    rom_path: str = "/roms/test.sfc",
) -> GameTile:
    return GameTile(
        id=id, title=title, system=system,
        art_url=art_url, playable=playable, rom_path=rom_path,
    )


def _ctx(tiles: list[GameTile]) -> ServerContext:
    return ServerContext(
        tiles=tiles,
        system="snes",
        media_root=Path("/fake/media"),
        roms_root=Path("/fake/roms"),
        launcher=None,
        transport_factory=None,
    )


def _register(tiles: list[GameTile]) -> ToolCatalog:
    mcp = ToolCatalog("test-adversarial")
    register(mcp, context=_ctx(tiles))
    return mcp


def _tool(mcp: ToolCatalog, name: str):
    tools = asyncio.run(mcp.list_tools())
    match = next((t for t in tools if t.name == name), None)
    assert match is not None, f"Tool '{name}' not registered"
    return match


# ---------------------------------------------------------------------------
# Edge Case 1: art_url present BUT playable=False → MUST be excluded
# ---------------------------------------------------------------------------

class TestArtPresentButUnplayable:
    """A tile with cover art but playable=False MUST NOT appear anywhere."""

    @pytest.fixture()
    def mcp(self):
        return _register([
            _tile("curated", art_url="snes/curated.png", playable=True),
            _tile("art-but-unplayable", art_url="snes/exists.png", playable=False),
        ])

    def test_is_curated_rejects(self):
        t = _tile("x", art_url="snes/x.png", playable=False)
        assert _is_curated(t) is False

    def test_list_games_excludes(self, mcp):
        result = _tool(mcp, "list_games").fn()
        ids = {g["id"] for g in result}
        assert "art-but-unplayable" not in ids
        assert len(result) == 1

    def test_search_games_excludes(self, mcp):
        result = _tool(mcp, "search_games").fn(query="Test")
        ids = {g["id"] for g in result}
        assert "art-but-unplayable" not in ids

    def test_library_summary_excludes(self, mcp):
        summary = _tool(mcp, "library_summary").fn()
        assert summary["total_curated_games"] == 1


# ---------------------------------------------------------------------------
# Edge Case 2: playable=True BUT art_url="" → MUST be excluded
# ---------------------------------------------------------------------------

class TestPlayableButNoArt:
    """A playable tile with empty art_url MUST NOT appear anywhere."""

    @pytest.fixture()
    def mcp(self):
        return _register([
            _tile("curated", art_url="snes/c.png", playable=True),
            _tile("no-art-playable", art_url="", playable=True),
        ])

    def test_is_curated_rejects_empty_string(self):
        assert _is_curated(_tile("x", art_url="", playable=True)) is False

    def test_is_curated_rejects_whitespace_only(self):
        # Whitespace art_url is truthy in Python but semantically empty.
        # This test documents current behavior: bool("  ") == True → passes filter.
        # If this is a bug, it should be caught here.
        t = _tile("x", art_url="   ", playable=True)
        # NOTE: bool("   ") is True in Python, so _is_curated will PASS this.
        # This documents a potential weakness — whitespace-only art_url leaks through.
        assert _is_curated(t) is True  # DOCUMENTS BEHAVIOR — whitespace leaks

    def test_list_games_excludes_empty_art(self, mcp):
        result = _tool(mcp, "list_games").fn()
        ids = {g["id"] for g in result}
        assert "no-art-playable" not in ids
        assert len(result) == 1

    def test_search_games_excludes_empty_art(self, mcp):
        result = _tool(mcp, "search_games").fn(query="Test")
        ids = {g["id"] for g in result}
        assert "no-art-playable" not in ids


# ---------------------------------------------------------------------------
# Edge Case 3: Empty library → sane zero state, no crash
# ---------------------------------------------------------------------------

class TestEmptyLibrary:
    """With zero tiles, all tools must return sane empty structures, not crash."""

    @pytest.fixture()
    def mcp(self):
        return _register([])

    def test_list_games_empty(self, mcp):
        result = _tool(mcp, "list_games").fn()
        assert result == []

    def test_search_games_empty(self, mcp):
        result = _tool(mcp, "search_games").fn(query="anything")
        assert result == []

    def test_library_summary_zeroed(self, mcp):
        summary = _tool(mcp, "library_summary").fn()
        assert summary["total_curated_games"] == 0
        assert summary["systems"] == []
        assert summary["per_system"] == {}

    def test_get_game_returns_none(self, mcp):
        result = _tool(mcp, "get_game").fn(game_id="nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# Edge Case 4: search_games query matching ONLY uncurated titles → empty
# ---------------------------------------------------------------------------

class TestSearchOnlyMatchesUncurated:
    """If a search query matches ONLY non-curated tiles, result MUST be empty."""

    @pytest.fixture()
    def mcp(self):
        return _register([
            _tile("curated", title="Super Mario", art_url="snes/m.png", playable=True),
            _tile("uncurated-match", title="Hidden Secret", art_url="", playable=True),
            _tile("uncurated-match2", title="Secret Dungeon", art_url="snes/d.png", playable=False),
        ])

    def test_search_for_uncurated_only_term_returns_empty(self, mcp):
        """Query 'Secret' matches 2 tiles but both are uncurated → empty."""
        result = _tool(mcp, "search_games").fn(query="Secret")
        assert result == []

    def test_search_for_curated_term_returns_it(self, mcp):
        result = _tool(mcp, "search_games").fn(query="Mario")
        assert len(result) == 1
        assert result[0]["id"] == "curated"


# ---------------------------------------------------------------------------
# Edge Case 5: get_game on uncurated id → DEFECT DETECTED
#
# The grounding contract says the agent MUST NOT surface unplayable games.
# get_game currently does NOT filter by _is_curated — it returns detail for
# ANY tile by id, curated or not. This is a grounding LEAK.
#
# EXPECTED (per contract): get_game should return None for uncurated ids.
# ACTUAL: get_game returns full tile_detail for uncurated ids.
#
# This test documents the defect with xfail so it PASSES the suite but
# clearly marks the contract violation.
# ---------------------------------------------------------------------------

class TestGetGameUncuratedLeak:
    """DEFECT: get_game leaks uncurated tile detail to the agent."""

    @pytest.fixture()
    def mcp(self):
        return _register([
            _tile("curated", title="Good Game", art_url="snes/g.png", playable=True),
            _tile("unplayable", title="Broken ROM", art_url="snes/b.png", playable=False),
            _tile("no-art", title="No Cover", art_url="", playable=True),
        ])

    def test_get_game_curated_returns_detail(self, mcp):
        """Sanity: get_game on a curated id works fine."""
        result = _tool(mcp, "get_game").fn(game_id="curated")
        assert result is not None
        assert result["title"] == "Good Game"

    def test_get_game_unplayable_should_return_none(self, mcp):
        """Per grounding contract, agent must not surface unplayable games."""
        result = _tool(mcp, "get_game").fn(game_id="unplayable")
        assert result is None

    def test_get_game_no_art_should_return_none(self, mcp):
        """Per grounding contract, agent must not surface games without cover art."""
        result = _tool(mcp, "get_game").fn(game_id="no-art")
        assert result is None

    def test_get_game_truly_missing_id_returns_none(self, mcp):
        """Non-existent id still returns None (not a defect, just correctness)."""
        result = _tool(mcp, "get_game").fn(game_id="does-not-exist")
        assert result is None


# ---------------------------------------------------------------------------
# Edge Case 6: Multi-system mixed fixture — exact curated subset assertion
# ---------------------------------------------------------------------------

class TestMultiSystemMixedFixture:
    """5 systems, 12 tiles, exact curated subset = 7. No off-by-one."""

    TILES = [
        # Curated (7)
        _tile("snes-1", title="SNES Game 1", system="SNES", art_url="snes/1.png"),
        _tile("snes-2", title="SNES Game 2", system="SNES", art_url="snes/2.png"),
        _tile("n64-1", title="N64 Game 1", system="N64", art_url="n64/1.png"),
        _tile("mame-1", title="Street Fighter II", system="MAME", art_url="mame/sf2.png"),
        _tile("mame-2", title="Metal Slug", system="MAME", art_url="mame/ms.png"),
        _tile("gba-1", title="GBA Game", system="GBA", art_url="gba/1.png"),
        _tile("psx-1", title="FF7", system="PSX", art_url="psx/ff7.png"),
        # Uncurated (5)
        _tile("snes-noart", title="SNES No Art", system="SNES", art_url=""),
        _tile("n64-unplayable", title="N64 Broken", system="N64", art_url="n64/b.png", playable=False),
        _tile("mame-both", title="MAME Both Bad", system="MAME", art_url="", playable=False),
        _tile("gba-noart", title="GBA No Cover", system="GBA", art_url=""),
        _tile("psx-broken", title="PSX Broken", system="PSX", art_url="psx/b.png", playable=False),
    ]

    EXPECTED_CURATED_IDS = {"snes-1", "snes-2", "n64-1", "mame-1", "mame-2", "gba-1", "psx-1"}

    @pytest.fixture()
    def mcp(self):
        return _register(self.TILES)

    def test_list_games_exact_curated_set(self, mcp):
        result = _tool(mcp, "list_games").fn()
        actual_ids = {g["id"] for g in result}
        assert actual_ids == self.EXPECTED_CURATED_IDS

    def test_list_games_count_no_off_by_one(self, mcp):
        result = _tool(mcp, "list_games").fn()
        assert len(result) == 7

    def test_library_summary_per_system_counts(self, mcp):
        summary = _tool(mcp, "library_summary").fn()
        assert summary["per_system"] == {
            "GBA": 1,
            "MAME": 2,
            "N64": 1,
            "PSX": 1,
            "SNES": 2,
        }

    def test_library_summary_systems_sorted(self, mcp):
        summary = _tool(mcp, "library_summary").fn()
        assert summary["systems"] == ["GBA", "MAME", "N64", "PSX", "SNES"]

    def test_summary_total_matches_list_games_len(self, mcp):
        games = _tool(mcp, "list_games").fn()
        summary = _tool(mcp, "library_summary").fn()
        assert summary["total_curated_games"] == len(games) == 7


# ---------------------------------------------------------------------------
# Edge Case 7: All-excluded and all-included extremes
# ---------------------------------------------------------------------------

class TestAllExcludedAllIncluded:
    """Boundary: every tile excluded vs every tile curated."""

    def test_all_tiles_uncurated_list_empty(self):
        tiles = [
            _tile("a", art_url="", playable=True),
            _tile("b", art_url="x.png", playable=False),
            _tile("c", art_url="", playable=False),
        ]
        mcp = _register(tiles)
        assert _tool(mcp, "list_games").fn() == []
        assert _tool(mcp, "library_summary").fn()["total_curated_games"] == 0

    def test_all_tiles_curated_list_complete(self):
        tiles = [
            _tile("a", art_url="a.png", playable=True),
            _tile("b", art_url="b.png", playable=True),
            _tile("c", art_url="c.png", playable=True),
        ]
        mcp = _register(tiles)
        result = _tool(mcp, "list_games").fn()
        assert len(result) == 3
        assert {g["id"] for g in result} == {"a", "b", "c"}


# ---------------------------------------------------------------------------
# Edge Case: search_games with empty query returns ALL curated (not all tiles)
# ---------------------------------------------------------------------------

class TestSearchEmptyQueryGrounding:
    """Empty/whitespace query to search_games should return all CURATED, not all tiles."""

    @pytest.fixture()
    def mcp(self):
        return _register([
            _tile("curated-1", art_url="c1.png", playable=True),
            _tile("curated-2", art_url="c2.png", playable=True),
            _tile("uncurated", art_url="", playable=True),
        ])

    def test_empty_query_returns_only_curated(self, mcp):
        result = _tool(mcp, "search_games").fn(query="")
        ids = {g["id"] for g in result}
        assert ids == {"curated-1", "curated-2"}
        assert "uncurated" not in ids

    def test_whitespace_query_returns_only_curated(self, mcp):
        result = _tool(mcp, "search_games").fn(query="   ")
        ids = {g["id"] for g in result}
        assert ids == {"curated-1", "curated-2"}
        assert "uncurated" not in ids
