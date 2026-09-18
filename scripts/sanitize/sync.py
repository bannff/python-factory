"""Destructive worktree sync guarded by complete, read-only preflight checks."""

from __future__ import annotations

import configparser
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from .safety import SafetyError, assert_no_symlinks


class SyncError(RuntimeError):
    """Raised before sync when clone identity or state is unsafe."""


def _git(arguments: list[str], cwd: Path) -> str:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"})
    process = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
         *arguments], cwd=cwd, capture_output=True, text=True, env=env,
    )
    if process.returncode:
        raise SyncError(process.stderr.strip() or f"git {' '.join(arguments)} failed")
    return process.stdout.strip()


def canonical_remote(value: str) -> str:
    raw = value.strip().rstrip("/")
    canonical = re.fullmatch(
        r"([a-z0-9.-]+)/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:\.git)?", raw,
    )
    if canonical:
        host, owner, repository = canonical.groups()
        return f"{host.lower()}/{owner}/{repository.removesuffix('.git')}"
    scp = re.fullmatch(r"git@([a-zA-Z0-9.-]+):([^/?#]+/[^/?#]+)", raw)
    if scp:
        host, path = scp.groups()
    elif "://" in raw:
        parsed = urlsplit(raw)
        if (parsed.scheme not in {"https", "ssh", "git"} or parsed.port is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.username not in {None, "git"}):
            raise SyncError(f"unsafe remote transport: {value}")
        host, path = parsed.hostname or "", parsed.path
    else:
        raise SyncError(f"invalid canonical remote: {value}")
    normalized = f"{host.lower()}/{path.lstrip('/')}".removesuffix(".git")
    if not re.fullmatch(r"[a-z0-9.-]+/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", normalized):
        raise SyncError(f"invalid canonical remote: {value}")
    return normalized


def _validate_root(clone: Path, protected: tuple[Path, ...]) -> Path:
    if not clone.is_absolute() or clone.is_symlink() or not clone.is_dir():
        raise SyncError(f"clone root must be an absolute, real directory: {clone}")
    resolved = clone.resolve(strict=True)
    if resolved in {Path("/"), Path.home().resolve()}:
        raise SyncError(f"unsafe clone root: {resolved}")
    for path in (item.resolve() for item in protected):
        if resolved == path or resolved.is_relative_to(path) or path.is_relative_to(resolved):
            raise SyncError(f"unsafe clone root: {resolved}")
    return resolved


def _remote_urls(root: Path, push: bool = False) -> list[str]:
    args = ["remote", "get-url"]
    if push:
        args.append("--push")
    args.extend(["--all", "origin"])
    return [canonical_remote(line) for line in _git(args, root).splitlines() if line]


def _reject_executable_config(git_dir: Path) -> None:
    config = git_dir / "config"
    if config.is_symlink() or not config.is_file():
        raise SyncError("git config must be a regular file inside .git")
    parser = configparser.RawConfigParser(strict=False)
    try:
        parser.read_string(config.read_text(encoding="utf-8"))
    except configparser.Error as error:
        raise SyncError(f"unparseable git config: {error}") from error
    unsafe_sections = {"filter", "alias", "include", "includeif"}
    unsafe_core = {"hookspath", "fsmonitor", "worktree", "attributesfile"}
    hits: list[str] = []
    for section in parser.sections():
        section_type = re.split(r"[\s.]", section, maxsplit=1)[0].lower()
        if section_type in unsafe_sections:
            hits.append(section)
        if section_type == "core":
            hits.extend(f"core.{key}" for key in parser[section] if key.lower() in unsafe_core)
    if hits:
        raise SyncError(f"unsafe executable or redirecting git config: {hits}")


def preflight_clone(clone: Path, expected_remote: str, *, confirmed: bool,
                    protected: tuple[Path, ...] = ()) -> Path:
    """Complete all validation before the caller may delete clone contents."""
    if not confirmed:
        raise SyncError("--sync requires --confirm-sync")
    expected = canonical_remote(expected_remote)
    root = _validate_root(clone, protected)
    git_dir = root / ".git"
    if git_dir.is_symlink() or not git_dir.is_dir():
        raise SyncError(f"public clone is not a normal git worktree: {root}")
    _reject_executable_config(git_dir)
    assert_no_symlinks(root, skip_dirs={".git"})
    top = Path(_git(["rev-parse", "--show-toplevel"], root)).resolve()
    actual_git = Path(_git(["rev-parse", "--absolute-git-dir"], root)).resolve()
    if top != root or actual_git != git_dir.resolve():
        raise SyncError("git worktree or git-dir redirects outside the declared clone")
    if _git(["rev-parse", "--is-bare-repository"], root) != "false":
        raise SyncError("bare repositories cannot be synchronized")
    for kind, urls in (("fetch", _remote_urls(root)), ("push", _remote_urls(root, True))):
        if urls != [expected]:
            raise SyncError(f"wrong {kind} remote: expected {[expected]}, got {urls}")
    dirty = _git([
        "status", "--porcelain=v1", "--untracked-files=all", "--ignored=matching",
    ], root)
    if dirty:
        raise SyncError(f"public clone is dirty (including ignored files):\n{dirty}")
    return root


def _copy_tree(source: Path, parent_fd: int) -> None:
    for child in source.iterdir():
        mode = child.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            os.mkdir(child.name, mode & 0o777, dir_fd=parent_fd)
            child_fd = os.open(child.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=parent_fd)
            try:
                _copy_tree(child, child_fd)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(mode):
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            output_fd = os.open(child.name, flags, mode & 0o777, dir_fd=parent_fd)
            with child.open("rb") as source_file, os.fdopen(output_fd, "wb") as output:
                shutil.copyfileobj(source_file, output)
        else:
            raise SyncError(f"unsupported source entry: {child}")


def sync_into_clone(source: Path, clone: Path, expected_remote: str, *,
                    confirmed: bool, protected: tuple[Path, ...] = ()) -> str:
    """Replace a clone worktree only; never stage, commit, run hooks, or push."""
    root = preflight_clone(clone, expected_remote, confirmed=confirmed,
                           protected=(*protected, source))
    assert_no_symlinks(source)
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        checked = preflight_clone(root, expected_remote, confirmed=True,
                                  protected=(*protected, source))
        opened = os.fstat(root_fd)
        current = os.stat(checked, follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise SyncError("clone root changed during preflight")
        for name in os.listdir(root_fd):
            if name == ".git":
                continue
            mode = os.stat(name, dir_fd=root_fd, follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                shutil.rmtree(name, dir_fd=root_fd)
            else:
                os.unlink(name, dir_fd=root_fd)
        _copy_tree(source, root_fd)
    finally:
        os.close(root_fd)
    if root.is_symlink() or root.resolve() != checked:
        raise SyncError("clone root changed during synchronization")
    assert_no_symlinks(root, skip_dirs={".git"})
    return "\n".join(sorted(child.name for child in source.iterdir()))
