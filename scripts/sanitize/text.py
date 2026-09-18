"""Token-aware identifier renames and prose-only scrubbing."""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path
from typing import Any

from .safety import iter_files

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", ".next",
              ".pytest_cache", ".ruff_cache", ".hypothesis", ".mypy_cache"}


def rename_python_identifiers(src: str, mapping: dict[str, str]) -> tuple[str, int]:
    """Rename Python NAME tokens while preserving strings and comments."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return src, 0
    lines = src.splitlines(keepends=True)
    edits: list[tuple[int, int, int, str]] = []
    for token in tokens:
        if token.type != tokenize.NAME or token.string not in mapping:
            continue
        (start_row, start_col), (end_row, end_col) = token.start, token.end
        if start_row == end_row:
            edits.append((start_row - 1, start_col, end_col, mapping[token.string]))
    for row, start, end, replacement in sorted(edits, reverse=True):
        lines[row] = lines[row][:start] + replacement + lines[row][end:]
    return "".join(lines), len(edits)


def rename_symbols(tree: Path, policy: dict[str, Any], report: Any) -> None:
    """Rename Python identifiers only; JS/TS code is intentionally untouched."""
    mapping: dict[str, str] = policy.get("rename_symbols") or {}
    if not mapping:
        return
    for path in iter_files(tree, skip_dirs=_SKIP_DIRS):
        if path.suffix != ".py":
            continue
        source = path.read_text(encoding="utf-8")
        output, count = rename_python_identifiers(source, mapping)
        if count:
            path.write_text(output, encoding="utf-8")
            report.renamed[str(path.relative_to(tree))] = count


def scrub_prose(tree: Path, policy: dict[str, Any], report: Any) -> None:
    config = policy.get("scrub_prose") or {}
    extensions = set(config.get("extensions", []))
    names = set(config.get("filenames", []))
    patterns: list[tuple[re.Pattern[str], str]] = []
    for term in config.get("terms", []) or []:
        source = re.escape(term["from"])
        patterns.append((re.compile(rf"(?<![A-Za-z0-9_]){source}(?![A-Za-z0-9_])"),
                         term["to"]))
    for term in config.get("regex_terms", []) or []:
        patterns.append((re.compile(term["pattern"]), term["to"]))
    for path in iter_files(tree, skip_dirs=_SKIP_DIRS):
        if path.suffix not in extensions and path.name not in names:
            continue
        source = path.read_text(encoding="utf-8")
        output, total = source, 0
        for pattern, replacement in patterns:
            output, count = pattern.subn(replacement, output)
            total += count
        if total:
            path.write_text(output, encoding="utf-8")
            report.scrubbed[str(path.relative_to(tree))] = total
