"""Local JSON-backed memory store — MemoryStore protocol implementation.

Persists user memories (prefs, favorites, notes) to a JSON file in the
OpenArcade config dir (~/.config/openarcade/memory.json). Survives restarts.

Scoring: lightweight case-insensitive keyword/substring matching (same spirit
as knowledge_tools). No embedding model required — keeps it local + offline.

SECURITY: content treated as untrusted data; only json.dump/load used (no
eval/exec). Path confined to config dir (no traversal from content).
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from strands.memory.types import MemoryEntry

# Serializes read-modify-write across concurrent add() calls (even from
# different store instances / worker threads pointing at the same file), so
# interleaved adds can't drop entries.
_WRITE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Config dir (reuses assistant_config_service pattern)
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    """Resolve config directory (env override or ~/.config/openarcade/)."""
    env = os.environ.get("OPENARCADE_CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "openarcade"


def _memory_file() -> Path:
    return _config_dir() / "memory.json"


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _load_entries(path: Path) -> list[dict[str, Any]]:
    """Load entries from JSON file. Returns empty list on missing/corrupt file."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return []


def _save_entries(path: Path, entries: list[dict[str, Any]]) -> None:
    """Persist entries to JSON file atomically (write-tmp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique temp name per write so concurrent writers never clobber each
    # other's tmp (the shared '.tmp' caused a FileNotFoundError race).
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Scoring (same spirit as knowledge_tools._score_document)
# ---------------------------------------------------------------------------


def _score_entry(content_lower: str, terms: list[str]) -> float:
    """Score an entry against query terms. Higher = more relevant."""
    if not terms:
        return 0.0
    score = 0.0
    for term in terms:
        score += content_lower.count(term)
    return score / len(terms)


# ---------------------------------------------------------------------------
# LocalJsonMemoryStore — implements strands.memory.types.MemoryStore protocol
# ---------------------------------------------------------------------------


class LocalJsonMemoryStore:
    """File-backed memory store for user preferences and notes.

    Attributes match the MemoryStore protocol.
    """

    name: str = "user_memory"
    description: str | None = (
        "Remembers user preferences, favorite games/genres, and personal notes "
        "across sessions. Stored locally on this device."
    )
    max_search_results: int | None = 5
    writable: bool = True
    extraction: bool = False  # No background LLM extraction; explicit add only.

    def __init__(self, *, path: Path | None = None) -> None:
        """Initialize store with optional path override (for testing)."""
        self._path = path or _memory_file()

    async def search(
        self, query: str, options: Any | None = None
    ) -> list[MemoryEntry]:
        """Search stored memories by keyword/substring relevance."""
        entries = _load_entries(self._path)
        if not query.strip():
            return []

        terms = [t.lower() for t in query.strip().split() if t]
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in entries:
            content = entry.get("content", "")
            score = _score_entry(content.lower(), terms)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        limit = self.max_search_results or 5
        results: list[MemoryEntry] = []
        for _score, entry in scored[:limit]:
            results.append(
                MemoryEntry(
                    content=entry["content"],
                    store_name=self.name,
                    metadata=entry.get("metadata"),
                )
            )
        return results

    async def add(
        self, content: str, metadata: dict[str, Any] | None = None
    ) -> str:
        """Add a memory entry. Persists immediately. Returns the entry id."""
        entry_id = str(uuid.uuid4())
        entry: dict[str, Any] = {
            "id": entry_id,
            "content": content,
            "created_at": time.time(),
        }
        if metadata:
            entry["metadata"] = metadata

        # Serialize the read-modify-write so concurrent adds can't drop entries.
        with _WRITE_LOCK:
            entries = _load_entries(self._path)
            entries.append(entry)
            _save_entries(self._path, entries)
        return entry_id

    async def initialize(self) -> None:
        """Ensure config dir exists (lazy creation)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
