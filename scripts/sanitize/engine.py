"""Fail-closed transform tiers for public-mirror sanitization."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .safety import confined, validate_policy_paths
from .text import rename_symbols, scrub_prose


class PolicyError(RuntimeError):
    """Raised when policy anchors no longer match the source tree."""


@dataclass
class Report:
    deleted: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    patched: list[str] = field(default_factory=list)
    renamed: dict[str, int] = field(default_factory=dict)
    scrubbed: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def delete_paths(tree: Path, policy: dict[str, Any], report: Report) -> None:
    for relative in policy.get("delete_paths", []) or []:
        target = confined(tree, relative.rstrip("/"))
        if not target.exists():
            report.errors.append(f"delete_paths: missing (already gone?) {relative}")
            continue
        shutil.rmtree(target) if target.is_dir() else target.unlink()
        report.deleted.append(relative)
    for relative in policy.get("delete_exact", []) or []:
        target = confined(tree, relative)
        if target.exists():
            target.unlink()
            report.deleted.append(relative)


def replace_files(tree: Path, replacements: Path, policy: dict[str, Any],
                  report: Report) -> None:
    for relative in policy.get("replace_files", []) or []:
        source = confined(replacements, relative)
        if not source.is_file():
            raise PolicyError(f"replace_files: no replacement authored for {relative}")
        destination = confined(tree, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        report.replaced.append(relative)


def _apply_edit(text: str, edit: dict[str, Any], relative: str, index: int) -> str:
    mode, old = edit.get("mode"), edit["old"]
    if mode == "delete_lines":
        pattern = re.compile(old)
        lines = text.splitlines(keepends=True)
        kept = [line for line in lines if not pattern.search(line)]
        removed = len(lines) - len(kept)
        minimum = int(edit.get("min_matches", 1))
        if removed < minimum:
            raise PolicyError(
                f"patches: delete_lines matched {removed} line(s) in {relative} "
                f"(edit #{index}), expected at least {minimum}: {old!r}"
            )
        return "".join(kept)
    if mode in {"regex", "regex_all"}:
        count_limit = 0 if mode == "regex_all" else 1
        output, count = re.subn(old, edit["new"], text, count=count_limit, flags=re.S)
        minimum = int(edit.get("min_matches", 1))
        if count < minimum:
            raise PolicyError(
                f"patches: regex anchor matched {count} time(s) in {relative} "
                f"(edit #{index}), expected at least {minimum}: {old!r}"
            )
        return output
    if old not in text:
        raise PolicyError(
            f"patches: anchor not found in {relative} (edit #{index}): {old!r}"
        )
    return text.replace(old, edit["new"], 1)


def apply_patches(tree: Path, policy: dict[str, Any], report: Report) -> None:
    for entry in policy.get("patches", []) or []:
        relative = entry["path"]
        path = confined(tree, relative)
        if not path.is_file():
            raise PolicyError(f"patches: target file missing: {relative}")
        text = path.read_text(encoding="utf-8")
        for index, edit in enumerate(entry.get("edits", [])):
            text = _apply_edit(text, edit, relative, index)
        path.write_text(text, encoding="utf-8")
        report.patched.append(relative)


def strip_pyproject_bricks(tree: Path, policy: dict[str, Any],
                           report: Report) -> None:
    structural = policy["structural"]
    patterns = [re.compile(rf"components/{re.escape(name)}/")
                for name in structural["strip_brick_maps"]]
    for relative in structural["pyproject_files"]:
        path = confined(tree, relative)
        if not path.is_file():
            raise PolicyError(f"strip_pyproject_bricks: missing {relative}")
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [line for line in lines if not any(rx.search(line) for rx in patterns)]
        path.write_text("".join(kept), encoding="utf-8")
        report.patched.append(f"{relative} (-{len(lines) - len(kept)} brick map lines)")


def transform(tree: Path, replacements: Path, policy: dict[str, Any]) -> Report:
    """Validate all paths once, then apply tiers in policy order."""
    validate_policy_paths(policy, tree, replacements)
    report = Report()
    delete_paths(tree, policy, report)
    replace_files(tree, replacements, policy, report)
    apply_patches(tree, policy, report)
    rename_symbols(tree, policy, report)
    scrub_prose(tree, policy, report)
    strip_pyproject_bricks(tree, policy, report)
    return report
