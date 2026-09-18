"""Filesystem confinement and symlink defenses for sanitizer operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable


class SafetyError(RuntimeError):
    """Raised when a path could escape or redirect a declared root."""


def _reject_root_symlink(root: Path) -> None:
    if root.is_symlink():
        raise SafetyError(f"root must not be a symlink: {root}")


def confined(root: Path, relative: str | Path, *, must_exist: bool = False) -> Path:
    """Return a path only when it is lexically and physically inside ``root``."""
    _reject_root_symlink(root)
    rel = Path(relative)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise SafetyError(f"unsafe relative path: {relative}")
    root_real = root.resolve(strict=True)
    candidate = root / rel
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise SafetyError(f"symlink in confined path: {current}")
        if not current.exists():
            break
    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(root_real):
        raise SafetyError(f"path escapes declared root: {relative}")
    if must_exist and not candidate.exists():
        raise SafetyError(f"required path missing: {candidate}")
    return candidate


def iter_files(root: Path, *, skip_dirs: Iterable[str] = ()) -> Iterable[Path]:
    """Yield regular files after rejecting every symlink in the tree."""
    assert_no_symlinks(root, skip_dirs=skip_dirs)
    skipped = set(skip_dirs)
    for path in root.rglob("*"):
        if any(part in skipped for part in path.relative_to(root).parts):
            continue
        if path.is_file():
            yield path


def assert_no_symlinks(root: Path, *, skip_dirs: Iterable[str] = ()) -> None:
    _reject_root_symlink(root)
    skipped = set(skip_dirs)
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        dirs[:] = [name for name in dirs if name not in skipped]
        for name in [*dirs, *files]:
            path = base / name
            if path.is_symlink():
                raise SafetyError(f"symlink forbidden in sanitizer tree: {path}")


def validate_policy_paths(policy: dict[str, Any], tree: Path, replacements: Path) -> None:
    """Validate every policy-carried filesystem path before transformation."""
    groups = (
        (tree, policy.get("delete_paths", [])),
        (tree, policy.get("delete_exact", [])),
        (tree, policy.get("replace_files", [])),
        (tree, (item["path"] for item in policy.get("patches", []))),
        (tree, policy.get("structural", {}).get("pyproject_files", [])),
        (tree, (item["path"] for item in policy.get("allow_exceptions", []))),
        (replacements, policy.get("replace_files", [])),
    )
    for root, paths in groups:
        for relative in paths or []:
            confined(root, str(relative).rstrip("/"))
