"""Adversarial tests for LocalJsonMemoryStore — QA breaker suite.

Targets: persistence across instances, corrupt file resilience, path-traversal
security, unicode/emoji, special chars, empty queries, concurrency race,
MemoryManager integration, MCPClient/to_thread coexistence.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from control_plane.memory_store import LocalJsonMemoryStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    return tmp_path / "memory.json"


@pytest.fixture
def store(store_path: Path) -> LocalJsonMemoryStore:
    return LocalJsonMemoryStore(path=store_path)


# ---------------------------------------------------------------------------
# 1. Persistence — survives restart (new instance reads old data)
# ---------------------------------------------------------------------------


class TestPersistenceAcrossInstances:
    @pytest.mark.asyncio
    async def test_add_in_one_instance_found_in_another(self, store_path: Path):
        s1 = LocalJsonMemoryStore(path=store_path)
        entry_id = await s1.add("Remember: CRT shader preferred")
        assert entry_id  # non-empty id

        # Completely new instance — simulates process restart
        s2 = LocalJsonMemoryStore(path=store_path)
        results = await s2.search("CRT shader")
        assert len(results) == 1
        assert "CRT shader" in results[0].content

    @pytest.mark.asyncio
    async def test_multiple_adds_all_survive(self, store_path: Path):
        s1 = LocalJsonMemoryStore(path=store_path)
        await s1.add("entry alpha")
        await s1.add("entry bravo")
        await s1.add("entry charlie")

        s2 = LocalJsonMemoryStore(path=store_path)
        raw = json.loads(store_path.read_text(encoding="utf-8"))
        assert len(raw) == 3
        results = await s2.search("entry")
        assert len(results) == 3


# ---------------------------------------------------------------------------
# 2. Corrupt file — no crash, graceful degradation
# ---------------------------------------------------------------------------


class TestCorruptFile:
    @pytest.mark.asyncio
    async def test_not_json_at_all(self, store_path: Path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("this is not json {{{{", encoding="utf-8")
        s = LocalJsonMemoryStore(path=store_path)
        results = await s.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_json_but_not_a_list(self, store_path: Path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text('{"key": "value", "nested": {}}', encoding="utf-8")
        s = LocalJsonMemoryStore(path=store_path)
        results = await s.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_truncated_json(self, store_path: Path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text('[{"content": "hello", "id": "abc"', encoding="utf-8")
        s = LocalJsonMemoryStore(path=store_path)
        results = await s.search("hello")
        assert results == []  # corrupt → empty, no crash

    @pytest.mark.asyncio
    async def test_empty_file(self, store_path: Path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("", encoding="utf-8")
        s = LocalJsonMemoryStore(path=store_path)
        results = await s.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_null_bytes(self, store_path: Path):
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_bytes(b"\x00\x00\x00\x00")
        s = LocalJsonMemoryStore(path=store_path)
        results = await s.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_add_recovers_after_corruption(self, store_path: Path):
        """After a corrupt file, add() should still work (starts fresh list)."""
        store_path.parent.mkdir(parents=True, exist_ok=True)
        store_path.write_text("GARBAGE!", encoding="utf-8")
        s = LocalJsonMemoryStore(path=store_path)
        entry_id = await s.add("recovery content")
        assert entry_id
        results = await s.search("recovery")
        assert len(results) == 1


# ---------------------------------------------------------------------------
# 3. Missing file / directory — graceful empty, add creates it
# ---------------------------------------------------------------------------


class TestMissingFileDir:
    @pytest.mark.asyncio
    async def test_missing_file_search_returns_empty(self, tmp_path: Path):
        s = LocalJsonMemoryStore(path=tmp_path / "does_not_exist.json")
        results = await s.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_missing_deep_dir_add_creates(self, tmp_path: Path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "memory.json"
        s = LocalJsonMemoryStore(path=deep)
        eid = await s.add("deep dive")
        assert eid
        assert deep.exists()
        data = json.loads(deep.read_text(encoding="utf-8"))
        assert len(data) == 1


# ---------------------------------------------------------------------------
# 4. Empty / whitespace query → []
# ---------------------------------------------------------------------------


class TestEmptyQuery:
    @pytest.mark.asyncio
    async def test_empty_string(self, store: LocalJsonMemoryStore):
        await store.add("something")
        assert await store.search("") == []

    @pytest.mark.asyncio
    async def test_whitespace_only(self, store: LocalJsonMemoryStore):
        await store.add("something")
        assert await store.search("   ") == []
        assert await store.search("\t\n") == []

    @pytest.mark.asyncio
    async def test_single_space(self, store: LocalJsonMemoryStore):
        await store.add("something")
        assert await store.search(" ") == []


# ---------------------------------------------------------------------------
# 5. Special characters — no crash, round-trips correctly, JSON stays valid
# ---------------------------------------------------------------------------


class TestSpecialChars:
    PAYLOADS = [
        'c++ [!] .* regex?',
        'path/to/../../etc/passwd',
        '"quotes" and \'single\'',
        'newline\nembedded\ttab',
        'null\x00byte',  # embedded NUL
        '<script>alert("xss")</script>',
        '${VARIABLE} $(command) `backtick`',
        "a" * 10000,  # very long content
        '{"inject": true}',  # JSON-like content
        'key=value&another=pair',
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", PAYLOADS, ids=[p[:30] for p in PAYLOADS])
    async def test_add_search_roundtrip(self, store: LocalJsonMemoryStore, payload: str):
        eid = await store.add(payload)
        assert eid  # got an id back

        # File is valid JSON after add
        raw = store._path.read_text(encoding="utf-8")
        data = json.loads(raw)  # must not raise
        assert isinstance(data, list)

        # Search for a fragment — shouldn't crash
        fragment = payload[:10] if len(payload) > 10 else payload
        await store.search(fragment)  # no crash is the assertion

    @pytest.mark.asyncio
    async def test_special_chars_in_query_no_crash(self, store: LocalJsonMemoryStore):
        await store.add("normal content here")
        weird_queries = [
            '.*+?[]{}()|\\^$',
            '\x00\x01\x02',
            'a' * 5000,
            '{"evil": true}',
        ]
        for q in weird_queries:
            # Must not raise
            await store.search(q)


# ---------------------------------------------------------------------------
# 6. Unicode / emoji — ensure_ascii=False means they persist as-is
# ---------------------------------------------------------------------------


class TestUnicode:
    @pytest.mark.asyncio
    async def test_emoji_content_roundtrips(self, store: LocalJsonMemoryStore):
        await store.add("🎮 I love retro games! 🕹️✨")
        results = await store.search("retro")
        assert len(results) == 1
        assert "🎮" in results[0].content
        assert "🕹️" in results[0].content

    @pytest.mark.asyncio
    async def test_cjk_content(self, store: LocalJsonMemoryStore):
        await store.add("我喜欢玩超级马里奥")
        results = await store.search("马里奥")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_mixed_scripts(self, store: LocalJsonMemoryStore):
        await store.add("العربية + עברית + 日本語 + emoji 🔥")
        results = await store.search("emoji")
        assert len(results) == 1
        assert "🔥" in results[0].content

    @pytest.mark.asyncio
    async def test_emoji_stored_raw_not_escaped(self, store: LocalJsonMemoryStore):
        await store.add("🎮 game")
        raw = store._path.read_text(encoding="utf-8")
        # ensure_ascii=False means emoji is raw, not \\uXXXX
        assert "🎮" in raw
        assert "\\u" not in raw or "\\u0" not in raw  # no ascii escape for emoji


# ---------------------------------------------------------------------------
# 7. add() returns a usable ID
# ---------------------------------------------------------------------------


class TestAddReturnsId:
    @pytest.mark.asyncio
    async def test_id_is_uuid_format(self, store: LocalJsonMemoryStore):
        import uuid

        eid = await store.add("test")
        # Should be parseable as UUID
        parsed = uuid.UUID(eid)
        assert str(parsed) == eid

    @pytest.mark.asyncio
    async def test_ids_are_unique(self, store: LocalJsonMemoryStore):
        ids = set()
        for i in range(50):
            eid = await store.add(f"entry {i}")
            ids.add(eid)
        assert len(ids) == 50  # all unique


# ---------------------------------------------------------------------------
# 8. SECURITY — path traversal impossible, no eval/exec
# ---------------------------------------------------------------------------


class TestSecurity:
    @pytest.mark.asyncio
    async def test_content_cannot_influence_file_path(self, store: LocalJsonMemoryStore):
        """Content with path-traversal attempts stays in the configured file."""
        evil_payloads = [
            "../../etc/shadow",
            "../../../tmp/evil.json",
            "/etc/passwd\x00.json",
            "..\\..\\windows\\system32",
        ]
        original_path = store._path
        for payload in evil_payloads:
            await store.add(payload)
            # Path must not have changed
            assert store._path == original_path
            # File must exist only at the configured location
            assert original_path.exists()

    @pytest.mark.asyncio
    async def test_metadata_cannot_influence_file_path(self, store: LocalJsonMemoryStore):
        """Metadata with evil keys/values stays sandboxed."""
        await store.add("safe", metadata={
            "path": "/etc/shadow",
            "__file__": "/tmp/evil",
            "..": "traversal",
        })
        assert store._path.exists()
        data = json.loads(store._path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["metadata"]["path"] == "/etc/shadow"  # stored as data, not path

    def test_no_eval_or_exec_in_source(self):
        """Source must never use eval/exec on content."""
        import inspect
        from control_plane import memory_store

        source = inspect.getsource(memory_store)
        # These would be catastrophic if content reached them
        assert "eval(" not in source
        assert "exec(" not in source
        assert "compile(" not in source
        assert "subprocess" not in source
        assert "__import__" not in source

    @pytest.mark.asyncio
    async def test_config_dir_env_override_only_affects_dir(
        self, tmp_path: Path, monkeypatch
    ):
        """OPENARCADE_CONFIG_DIR only controls the dir, not injectable via content."""
        custom_dir = tmp_path / "custom_config"
        monkeypatch.setenv("OPENARCADE_CONFIG_DIR", str(custom_dir))
        # Fresh store with default path (uses env)
        from control_plane.memory_store import _memory_file

        assert _memory_file().parent == custom_dir


# ---------------------------------------------------------------------------
# 9. MemoryManager + Agent integration (boundary mock model)
# ---------------------------------------------------------------------------


class TestMemoryManagerAgent:
    @pytest.mark.asyncio
    async def test_memory_manager_tools_register(self, store: LocalJsonMemoryStore):
        """MemoryManager adds search_memory and add_memory tools."""
        from strands.memory import MemoryManager

        mm = MemoryManager(
            stores=[store],
            add_tool_config=True,
            search_tool_config=True,
            injection=True,
        )
        tool_names = [t.tool_name for t in mm.tools]
        assert "add_memory" in tool_names
        assert "search_memory" in tool_names

    @pytest.mark.asyncio
    async def test_agent_with_memory_manager_does_not_raise(
        self, store: LocalJsonMemoryStore
    ):
        """Agent accepts MemoryManager without crashing. Mock model at boundary."""
        from strands import Agent
        from strands.memory import MemoryManager

        mm = MemoryManager(
            stores=[store],
            add_tool_config=True,
            search_tool_config=True,
            injection=True,
        )
        mock_model = MagicMock()
        mock_model.get_config.return_value = {"model_id": "test"}

        # Must not raise
        agent = Agent(
            model=mock_model,
            tools=[],
            system_prompt="test",
            memory_manager=mm,
        )
        assert agent.memory_manager is mm

    @pytest.mark.asyncio
    async def test_memory_manager_does_not_break_mcp_sync_context(
        self, store: LocalJsonMemoryStore
    ):
        """MemoryManager with injection=True shouldn't conflict with
        MCPClient's sync context manager / asyncio.to_thread pattern.

        This verifies the Strands MemoryManager is compatible with running
        inside asyncio.to_thread (the strands_assistant pattern).
        """
        from strands import Agent
        from strands.memory import MemoryManager

        mm = MemoryManager(
            stores=[store],
            add_tool_config=True,
            injection=True,
        )
        mock_model = MagicMock()
        mock_model.get_config.return_value = {"model_id": "test"}

        # Simulate the to_thread pattern: create Agent inside a thread
        def _in_thread():
            agent = Agent(
                model=mock_model,
                tools=[],
                system_prompt="test",
                memory_manager=mm,
            )
            return agent

        agent = await asyncio.to_thread(_in_thread)
        assert agent.memory_manager is mm


# ---------------------------------------------------------------------------
# 10. CONCURRENCY — read-modify-write race condition analysis
# ---------------------------------------------------------------------------


class TestConcurrencyRace:
    @pytest.mark.asyncio
    async def test_concurrent_thread_adds_lose_no_entries(self, store_path: Path):
        """Regression guard: concurrent adds from worker threads (the real
        strands to_thread path) must NOT drop entries or crash.

        Before the fix this lost entries (unlocked read-modify-write) and
        crashed with FileNotFoundError (shared '.tmp'). The module _WRITE_LOCK
        + per-write unique tmp make it safe.
        """
        NUM_THREADS = 10
        WRITES_PER = 5
        errors: list[str] = []

        def writer(wid: int) -> None:
            s = LocalJsonMemoryStore(path=store_path)
            for i in range(WRITES_PER):
                try:
                    asyncio.run(s.add(f"writer-{wid}-entry-{i}"))
                except Exception as exc:  # crash under race = defect
                    errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=writer, args=(w,)) for w in range(NUM_THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"concurrent adds crashed: {errors[:3]}"
        data = json.loads(store_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == NUM_THREADS * WRITES_PER, "entries lost under concurrency"

    @pytest.mark.asyncio
    async def test_concurrent_adds_never_corrupt_json(self, store_path: Path):
        """Even under races, the JSON file must always remain valid."""
        NUM_WRITERS = 20

        async def writer(wid: int):
            s = LocalJsonMemoryStore(path=store_path)
            for i in range(10):
                await s.add(f"concurrent-{wid}-{i}")
                await asyncio.sleep(0)

        tasks = [asyncio.create_task(writer(w)) for w in range(NUM_WRITERS)]
        await asyncio.gather(*tasks)

        # File must be valid JSON regardless of race outcome
        raw = store_path.read_text(encoding="utf-8")
        data = json.loads(raw)  # Must NOT raise
        assert isinstance(data, list)
        # Every entry must have required fields
        for entry in data:
            assert isinstance(entry.get("content"), str)
            assert isinstance(entry.get("id"), str)


# ---------------------------------------------------------------------------
# 11. Edge cases: protocol attrs, initialize(), options param
# ---------------------------------------------------------------------------


class TestProtocolEdgeCases:
    @pytest.mark.asyncio
    async def test_initialize_creates_dir(self, tmp_path: Path):
        deep = tmp_path / "init_test" / "sub" / "memory.json"
        s = LocalJsonMemoryStore(path=deep)
        await s.initialize()
        assert deep.parent.exists()

    @pytest.mark.asyncio
    async def test_search_options_param_accepted(self, store: LocalJsonMemoryStore):
        """search() accepts options=... without crashing (protocol compat)."""
        await store.add("test")
        # options is unused but must not crash
        results = await store.search("test", options={"limit": 3})
        assert len(results) >= 1
        results = await store.search("test", options=None)
        assert len(results) >= 1

    def test_protocol_attrs_correct(self, store: LocalJsonMemoryStore):
        assert store.name == "user_memory"
        assert store.writable is True
        assert store.extraction is False
        assert store.max_search_results == 5
        assert isinstance(store.description, str)
        assert len(store.description) > 10
