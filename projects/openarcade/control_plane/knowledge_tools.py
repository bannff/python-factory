"""Knowledge tools — read-only knowledge base search.

Exposes a single MCP tool (knowledge_search) that performs keyword/substring
scoring over a corpus of flat markdown files. Pure, deterministic, no network.

Upgrade path: swap _score_document for embedding cosine-similarity without
changing the MCP contract (query: str, limit: int) -> list[dict].
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import ServerContext


# Corpus location: docs/knowledge/ relative to the project root
_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "docs" / "knowledge"


def _load_corpus(knowledge_dir: Path) -> list[dict[str, str]]:
    """Load all .md files recursively from the knowledge dir.

    Returns list of {"title": <stem>, "path": <relative>, "body": <content>}.
    """
    if not knowledge_dir.is_dir():
        return []
    docs: list[dict[str, str]] = []
    for md_file in sorted(knowledge_dir.rglob("*.md")):
        body = md_file.read_text(encoding="utf-8", errors="replace")
        relative = str(md_file.relative_to(knowledge_dir))
        # Title = first H1 line if present, else stem
        title = md_file.stem.replace("-", " ").title()
        for line in body.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        docs.append({"title": title, "path": relative, "body": body})
    return docs


def _score_document(doc: dict[str, str], terms: list[str]) -> float:
    """Score a document against query terms. Higher = more relevant.

    Scoring strategy (simple, deterministic):
    - Each term that appears in the title gets +3 points per occurrence.
    - Each term that appears in the body gets +1 point per occurrence.
    - Case-insensitive.
    - Final score normalized by number of terms (so multi-word queries don't
      inflate scores vs single-word).
    """
    if not terms:
        return 0.0
    title_lower = doc["title"].lower()
    body_lower = doc["body"].lower()
    score = 0.0
    for term in terms:
        # Title matches weighted 3x
        score += title_lower.count(term) * 3.0
        # Body matches
        score += body_lower.count(term) * 1.0
    return score / len(terms)


def _extract_snippet(body: str, terms: list[str], max_len: int = 200) -> str:
    """Extract a relevant snippet around the first matching term."""
    body_lower = body.lower()
    best_pos = -1
    for term in terms:
        pos = body_lower.find(term)
        if pos != -1:
            best_pos = pos
            break
    if best_pos == -1:
        # Fallback: first max_len chars
        return body[:max_len].strip()
    # Center snippet around the match
    start = max(0, best_pos - 60)
    end = min(len(body), best_pos + max_len - 60)
    snippet = body[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(body):
        snippet = snippet + "..."
    return snippet


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register knowledge tools (knowledge_search)."""
    corpus = _load_corpus(_KNOWLEDGE_DIR)

    @mcp.tool()
    def knowledge_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search the OpenArcade knowledge base for emulator/core/ROM/how-to info.

        Returns the top-N matching documents ranked by relevance.
        Each result has: title, path (relative to knowledge/), snippet.
        """
        if not query.strip():
            return []
        terms = [t.lower() for t in query.strip().split() if t]
        scored = []
        for doc in corpus:
            score = _score_document(doc, terms)
            if score > 0:
                scored.append((score, doc))
        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[dict[str, Any]] = []
        for score, doc in scored[:limit]:
            results.append({
                "title": doc["title"],
                "path": doc["path"],
                "snippet": _extract_snippet(doc["body"], terms),
            })
        return results
