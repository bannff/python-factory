"""Static drift checker for the public-repo sanitizer policy.

The sanitizer builds its working tree with ``git archive`` -- tracked files
only -- so a policy entry that names an untracked path, or an anchor that no
longer exists in the tree, rots silently. ``sanitize_public.py --dry-run``
aborts at the FIRST bad entry; this checker enumerates EVERY bad entry and runs
in the ordinary ``scripts/test`` suite.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "scripts" / "sanitize" / "policy.yaml"
REPLACEMENTS = ROOT / "scripts" / "sanitize" / "replacements"


def load_policy(path: Path = POLICY) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _tracked_paths(root: Path) -> set[str]:
    output = subprocess.run(["git", "ls-files"], cwd=root, check=True,
                            capture_output=True, text=True).stdout
    return {line for line in output.splitlines() if line}


def _is_tracked(relative: str, tracked: set[str]) -> bool:
    """True when ``relative`` is a tracked file or a directory holding one."""
    name = str(relative).rstrip("/")
    return name in tracked or any(item.startswith(f"{name}/") for item in tracked)


def _anchor_matches(text: str, edit: dict[str, Any]) -> tuple[int, int]:
    """Match count and required minimum, mirroring ``engine._apply_edit``."""
    minimum = int(edit.get("min_matches", 1))
    mode, old = edit.get("mode"), edit["old"]
    if mode == "delete_lines":
        pattern = re.compile(old)
        return sum(1 for line in text.splitlines(keepends=True)
                   if pattern.search(line)), minimum
    if mode in {"regex", "regex_all"}:
        limit = 0 if mode == "regex_all" else 1
        _, count = re.subn(old, edit.get("new", ""), text, count=limit, flags=re.S)
        return count, minimum
    return text.count(old), minimum


def audit_policy(policy: dict[str, Any], root: Path) -> list[str]:
    """Return one message per dead policy entry, never stopping at the first."""
    tracked = _tracked_paths(root)
    absent = {str(item["path"]).rstrip("/")
              for item in policy.get("expected_absent", []) or []}
    problems: list[str] = []
    for index, relative in enumerate(policy.get("delete_paths", []) or []):
        if not _is_tracked(relative, tracked) and str(relative).rstrip("/") not in absent:
            problems.append(f"delete_paths[{index}]: {relative} is not tracked and is "
                            f"not declared in expected_absent")
    for index, relative in enumerate(policy.get("delete_exact", []) or []):
        if not _is_tracked(relative, tracked):
            problems.append(f"delete_exact[{index}]: not tracked: {relative}")
    for item in policy.get("expected_absent", []) or []:
        name = str(item["path"]).rstrip("/")
        if _is_tracked(name, tracked):
            problems.append(f"expected_absent: {name} is tracked again; drop the "
                            f"declaration (and the delete_paths entry if unwanted)")
    for index, relative in enumerate(policy.get("replace_files", []) or []):
        if not (REPLACEMENTS / relative).is_file():
            problems.append(f"replace_files[{index}]: no replacement authored for {relative}")
    for index, relative in enumerate(
            policy.get("structural", {}).get("pyproject_files", []) or []):
        if not _is_tracked(relative, tracked):
            problems.append(f"structural.pyproject_files[{index}]: not tracked: {relative}")
    for index, item in enumerate(policy.get("allow_exceptions", []) or []):
        if not _is_tracked(item["path"], tracked):
            problems.append(f"allow_exceptions[{index}]: not tracked: {item['path']}")
    for index, entry in enumerate(policy.get("patches", []) or []):
        relative = entry["path"]
        if not _is_tracked(relative, tracked):
            problems.append(f"patches[{index}]: target is not tracked: {relative}")
            continue
        path = root / relative
        if not path.is_file():
            problems.append(f"patches[{index}]: tracked target missing from checkout: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for edit_index, edit in enumerate(entry.get("edits", [])):
            count, minimum = _anchor_matches(text, edit)
            if count < minimum:
                problems.append(f"patches[{index}] {relative}: edit #{edit_index} matched "
                                f"{count}, expected >= {minimum}: {edit['old']!r}")
    return problems


def test_policy_entries_reference_tracked_files_and_live_anchors() -> None:
    problems = audit_policy(load_policy(), ROOT)
    assert not problems, "sanitizer policy drift:\n" + "\n".join(problems)


def test_checker_enumerates_every_bad_entry() -> None:
    policy = {
        "delete_paths": ["scripts/does_not_exist.py"],
        "replace_files": ["scripts/sanitize/not_authored.md"],
        "patches": [{"path": "pyproject.toml",
                     "edits": [{"old": "anchor that is not in the tree", "new": ""}]}],
    }
    problems = audit_policy(policy, ROOT)
    assert len(problems) == 3, problems
    assert any("delete_paths[0]" in item and "not tracked" in item for item in problems)
    assert any("no replacement authored" in item for item in problems)
    assert any("matched 0" in item for item in problems)
