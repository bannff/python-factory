"""Behavior tests for knowledge_tools — keyword/substring search over corpus."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from control_plane.server import build_server
from control_plane.knowledge_tools import _load_corpus, _score_document, _KNOWLEDGE_DIR


_GAMELIST = Path("/tmp/oa_arcade/gamelists/snes/gamelist.xml")
_MEDIA_ROOT = Path("/tmp/oa_arcade")
_SYSTEM = "snes"


@pytest.fixture()
def server():
    """Build a real server (skips if gamelist not on disk)."""
    if not _GAMELIST.exists():
        pytest.skip("SNES gamelist not on disk")
    return build_server(gamelist_path=_GAMELIST, system=_SYSTEM, media_root=_MEDIA_ROOT)


def _get_tool(server, name: str):
    tools = asyncio.run(server.list_tools())
    return next((t for t in tools if t.name == name), None)


class TestCorpusLoading:
    """Ensure the knowledge dir loads correctly."""

    def test_corpus_loads_nonempty(self):
        """Real corpus (docs/knowledge/) has >=5 docs."""
        corpus = _load_corpus(_KNOWLEDGE_DIR)
        assert len(corpus) >= 5

    def test_corpus_docs_have_required_keys(self):
        corpus = _load_corpus(_KNOWLEDGE_DIR)
        for doc in corpus:
            assert "title" in doc
            assert "path" in doc
            assert "body" in doc
            assert len(doc["body"]) > 0


class TestScoring:
    """Unit tests for the scoring function (pure, no I/O)."""

    def test_title_match_scores_higher(self):
        """A term matching the title should score higher than one only in body."""
        doc_title = {"title": "SNES Core Guide", "body": "some info here", "path": "x.md"}
        doc_body = {"title": "General Info", "body": "snes is a great system for retro", "path": "y.md"}
        score_title = _score_document(doc_title, ["snes"])
        score_body = _score_document(doc_body, ["snes"])
        assert score_title > score_body

    def test_no_match_returns_zero(self):
        doc = {"title": "Dreamcast Guide", "body": "flycast is the core", "path": "z.md"}
        assert _score_document(doc, ["zzzyyyxxx"]) == 0.0

    def test_empty_terms_returns_zero(self):
        doc = {"title": "Anything", "body": "content", "path": "a.md"}
        assert _score_document(doc, []) == 0.0


class TestKnowledgeSearch:
    """Integration tests — knowledge_search tool via the real corpus."""

    def test_snes_core_returns_systems_or_cores_doc(self):
        """Query 'snes core' should return a doc with system→core mapping info."""
        corpus = _load_corpus(_KNOWLEDGE_DIR)
        # Simulate what the tool does
        terms = ["snes", "core"]
        scored = []
        for doc in corpus:
            score = _score_document(doc, terms)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        assert len(scored) > 0
        top = scored[0][1]
        # Top result should be systems.md or cores.md (both have snes + core info)
        assert "systems" in top["path"].lower() or "cores" in top["path"].lower()

    def test_no_match_returns_empty(self):
        corpus = _load_corpus(_KNOWLEDGE_DIR)
        terms = ["zzzyyynonexistent"]
        scored = [(s, d) for d in corpus if (s := _score_document(d, terms)) > 0]
        assert scored == []

    def test_exact_topic_ranks_above_incidental(self):
        """'rom naming' should rank rom-naming.md above docs that merely mention 'rom'."""
        corpus = _load_corpus(_KNOWLEDGE_DIR)
        terms = ["rom", "naming"]
        scored = []
        for doc in corpus:
            score = _score_document(doc, terms)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        assert len(scored) >= 2
        top = scored[0][1]
        assert "rom-naming" in top["path"].lower() or "rom naming" in top["title"].lower()


class TestToolRegistration:
    """Ensure knowledge_search is registered on the server."""

    def test_knowledge_search_registered(self, server):
        tool = _get_tool(server, "knowledge_search")
        assert tool is not None

    def test_tool_count_includes_knowledge(self, server):
        """Total tool count should be 21 (previous 20 + knowledge_search)."""
        tools = asyncio.run(server.list_tools())
        assert len(tools) == 21
