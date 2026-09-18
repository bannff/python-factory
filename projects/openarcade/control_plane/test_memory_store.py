"""Tests for LocalJsonMemoryStore — boundary tests only.

Verifies: add→search round-trip, persistence across instances, corrupt/missing
file resilience, search ranking, and MemoryManager attachment.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from control_plane.memory_store import LocalJsonMemoryStore, _load_entries, _save_entries


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@pytest.fixture
def tmp_store(tmp_path: Path) -> LocalJsonMemoryStore:
    """Store backed by a temp file (no side effects)."""
    return LocalJsonMemoryStore(path=tmp_path / "memory.json")


# ---------------------------------------------------------------------------
# add → search round-trip
# ---------------------------------------------------------------------------


class TestAddSearchRoundTrip:
    def test_add_returns_id(self, tmp_store: LocalJsonMemoryStore):
        entry_id = _run(tmp_store.add("I love shoot-em-ups"))
        assert isinstance(entry_id, str)
        assert len(entry_id) > 0

    def test_added_entry_is_searchable(self, tmp_store: LocalJsonMemoryStore):
        _run(tmp_store.add("My favorite genre is platformers"))
        results = _run(tmp_store.search("platformers"))
        assert len(results) == 1
        assert "platformers" in results[0].content

    def test_no_match_returns_empty(self, tmp_store: LocalJsonMemoryStore):
        _run(tmp_store.add("I like racing games"))
        results = _run(tmp_store.search("puzzle"))
        assert results == []

    def test_empty_query_returns_empty(self, tmp_store: LocalJsonMemoryStore):
        _run(tmp_store.add("anything"))
        results = _run(tmp_store.search(""))
        assert results == []
        results = _run(tmp_store.search("   "))
        assert results == []

    def test_multiple_entries_searchable(self, tmp_store: LocalJsonMemoryStore):
        _run(tmp_store.add("Favorite game: Super Metroid"))
        _run(tmp_store.add("Favorite genre: platformers"))
        _run(tmp_store.add("Least favorite: sports games"))
        results = _run(tmp_store.search("favorite"))
        # All three match "favorite"
        assert len(results) == 3


# ---------------------------------------------------------------------------
# Persistence across instances
# ---------------------------------------------------------------------------


class TestPersistence:
    def test_survives_new_instance(self, tmp_path: Path):
        """Proves data persists to disk and a NEW instance reads it back."""
        file = tmp_path / "memory.json"
        store1 = LocalJsonMemoryStore(path=file)
        _run(store1.add("Remember: I prefer 4:3 aspect ratio"))

        # New instance, same path — must find the entry
        store2 = LocalJsonMemoryStore(path=file)
        results = _run(store2.search("aspect ratio"))
        assert len(results) == 1
        assert "4:3" in results[0].content

    def test_file_written_as_valid_json(self, tmp_store: LocalJsonMemoryStore):
        _run(tmp_store.add("test content"))
        raw = tmp_store._path.read_text(encoding="utf-8")
        data = json.loads(raw)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["content"] == "test content"
        assert "id" in data[0]
        assert "created_at" in data[0]


# ---------------------------------------------------------------------------
# Corrupt / missing file resilience
# ---------------------------------------------------------------------------


class TestResilience:
    def test_missing_file_returns_empty(self, tmp_path: Path):
        store = LocalJsonMemoryStore(path=tmp_path / "nonexistent.json")
        results = _run(store.search("anything"))
        assert results == []

    def test_corrupt_json_returns_empty(self, tmp_path: Path):
        file = tmp_path / "memory.json"
        file.write_text("{invalid json!!", encoding="utf-8")
        store = LocalJsonMemoryStore(path=file)
        results = _run(store.search("anything"))
        assert results == []

    def test_wrong_type_in_json_returns_empty(self, tmp_path: Path):
        file = tmp_path / "memory.json"
        file.write_text('{"not": "a list"}', encoding="utf-8")
        store = LocalJsonMemoryStore(path=file)
        results = _run(store.search("anything"))
        assert results == []

    def test_add_after_corrupt_file_recovers(self, tmp_path: Path):
        """Add should work even if file was corrupt — starts fresh."""
        file = tmp_path / "memory.json"
        file.write_text("CORRUPTED!", encoding="utf-8")
        store = LocalJsonMemoryStore(path=file)
        entry_id = _run(store.add("fresh start"))
        assert entry_id
        results = _run(store.search("fresh"))
        assert len(results) == 1

    def test_missing_directory_created_on_add(self, tmp_path: Path):
        deep_path = tmp_path / "a" / "b" / "c" / "memory.json"
        store = LocalJsonMemoryStore(path=deep_path)
        _run(store.add("deep dir entry"))
        assert deep_path.exists()


# ---------------------------------------------------------------------------
# Search ranking
# ---------------------------------------------------------------------------


class TestSearchRanking:
    def test_more_relevant_entry_ranked_first(self, tmp_store: LocalJsonMemoryStore):
        _run(tmp_store.add("I sometimes play puzzle games"))
        _run(tmp_store.add("puzzle puzzle puzzle is my life"))
        results = _run(tmp_store.search("puzzle"))
        # The one with more occurrences ranks higher
        assert "my life" in results[0].content

    def test_max_search_results_respected(self, tmp_path: Path):
        file = tmp_path / "memory.json"
        store = LocalJsonMemoryStore(path=file)
        store.max_search_results = 2
        for i in range(10):
            _run(store.add(f"entry {i} about cats"))
        results = _run(store.search("cats"))
        assert len(results) == 2

    def test_metadata_preserved(self, tmp_store: LocalJsonMemoryStore):
        _run(tmp_store.add("prefer scanlines shader", metadata={"source": "user"}))
        results = _run(tmp_store.search("scanlines"))
        assert results[0].metadata == {"source": "user"}


# ---------------------------------------------------------------------------
# MemoryManager attachment (boundary: Agent accepts it without error)
# ---------------------------------------------------------------------------


class TestMemoryManagerIntegration:
    def test_memory_manager_constructs_with_store(self, tmp_store: LocalJsonMemoryStore):
        from strands.memory import MemoryManager

        mm = MemoryManager(
            stores=[tmp_store],
            add_tool_config=True,
            search_tool_config=True,
            injection=True,
        )
        # MemoryManager is a Plugin — has tools and hooks
        assert mm.name == "strands:memory-manager"
        # Tools should include add_memory and search_memory
        tool_names = [t.tool_name for t in mm.tools]
        assert "add_memory" in tool_names
        assert "search_memory" in tool_names

    def test_agent_accepts_memory_manager(self, tmp_store: LocalJsonMemoryStore):
        """Agent(..., memory_manager=...) should not raise."""
        from strands import Agent
        from strands.memory import MemoryManager

        mm = MemoryManager(
            stores=[tmp_store],
            add_tool_config=True,
            search_tool_config=True,
            injection=True,
        )
        # Use a mock model to avoid needing real credentials
        mock_model = MagicMock()
        mock_model.get_config.return_value = {"model_id": "test"}
        agent = Agent(
            model=mock_model,
            tools=[],
            system_prompt="test",
            memory_manager=mm,
        )
        assert agent.memory_manager is mm


# ---------------------------------------------------------------------------
# Protocol attrs
# ---------------------------------------------------------------------------


class TestProtocolAttrs:
    def test_store_attrs(self, tmp_store: LocalJsonMemoryStore):
        assert tmp_store.name == "user_memory"
        assert tmp_store.writable is True
        assert tmp_store.extraction is False
        assert tmp_store.max_search_results == 5
        assert tmp_store.description is not None
