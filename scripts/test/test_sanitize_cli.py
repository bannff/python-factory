"""Focused CLI and destructive-sync preflight tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sanitize.cli import parse_args
from sanitize.sync import SyncError, preflight_clone, sync_into_clone

CANONICAL = "github.com/bannff/python-software-factory"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _clone(tmp_path: Path, remote: str = CANONICAL) -> Path:
    clone = tmp_path / "public-clone"
    clone.mkdir()
    _git(clone, "init", "-q")
    _git(clone, "config", "user.email", "test@example.com")
    _git(clone, "config", "user.name", "Sanitizer Test")
    (clone / "README.md").write_text("safe\n")
    _git(clone, "add", "README.md")
    _git(clone, "commit", "-q", "-m", "initial")
    _git(clone, "remote", "add", "origin", remote)
    return clone


def test_default_and_explicit_dry_run_are_non_destructive() -> None:
    default = parse_args([])
    explicit = parse_args(["--dry-run"])
    assert not default.sync and not explicit.sync
    assert default.clone is None and explicit.clone is None
    assert not default.confirmed and not explicit.confirmed


@pytest.mark.parametrize(
    "arguments",
    [
        ["--sync"],
        ["--sync", "--confirm-sync"],
        ["--sync", "--confirm-sync", "--public-clone", "/tmp/clone"],
        ["--dry-run", "--confirm-sync"],
        [
            "--sync", "--confirm-sync", "--public-clone", "/tmp/clone",
            "--expected-remote", CANONICAL, "--skip-pytest",
        ],
    ],
)
def test_sync_requires_all_explicit_flags(arguments: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(arguments)


def test_sync_options_accept_only_canonical_expected_remote(tmp_path: Path) -> None:
    options = parse_args([
        "--sync", "--confirm-sync", "--public-clone", str(tmp_path / "clone"),
        "--expected-remote", CANONICAL,
    ])
    assert options.sync and options.confirmed
    with pytest.raises(SystemExit):
        parse_args([
            "--sync", "--confirm-sync", "--public-clone", str(tmp_path / "clone"),
            "--expected-remote", "git@github.com:bannff/python-software-factory.git",
        ])


def test_preflight_rejects_missing_confirmation_before_git(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    with pytest.raises(SyncError, match="confirm-sync"):
        preflight_clone(clone, CANONICAL, confirmed=False)


def test_preflight_rejects_wrong_remote(tmp_path: Path) -> None:
    clone = _clone(tmp_path, "https://github.com/other/repository.git")
    with pytest.raises(SyncError, match="wrong fetch remote"):
        preflight_clone(clone, CANONICAL, confirmed=True)
    assert (clone / "README.md").read_text() == "safe\n"


def test_preflight_rejects_dirty_clone(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    (clone / "README.md").write_text("dirty\n")
    with pytest.raises(SyncError, match="dirty"):
        preflight_clone(clone, CANONICAL, confirmed=True)
    assert (clone / "README.md").read_text() == "dirty\n"


def test_preflight_rejects_clone_root_symlink(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    link = tmp_path / "clone-link"
    link.symlink_to(clone, target_is_directory=True)
    with pytest.raises(SyncError, match="absolute, real directory"):
        preflight_clone(link, CANONICAL, confirmed=True)


def test_preflight_rejects_protected_root(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    with pytest.raises(SyncError, match="unsafe clone root"):
        preflight_clone(clone, CANONICAL, confirmed=True, protected=(tmp_path,))


def test_preflight_rejects_wrong_push_remote(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    _git(clone, "remote", "set-url", "--push", "origin", "https://github.com/other/repo.git")
    with pytest.raises(SyncError, match="wrong push remote"):
        preflight_clone(clone, CANONICAL, confirmed=True)


def test_preflight_rejects_ignored_files(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    (clone / ".gitignore").write_text("secret.txt\n")
    _git(clone, "add", ".gitignore")
    _git(clone, "commit", "-q", "-m", "ignore fixture")
    (clone / "secret.txt").write_text("local data\n")
    with pytest.raises(SyncError, match="including ignored files"):
        preflight_clone(clone, CANONICAL, confirmed=True)


def test_preflight_rejects_redirected_worktree(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    _git(clone, "config", "core.worktree", str(redirected))
    with pytest.raises(SyncError, match="unsafe executable or redirecting"):
        preflight_clone(clone, CANONICAL, confirmed=True)


def test_sync_never_stages_or_commits(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=clone, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    source = tmp_path / "source"
    source.mkdir()
    (source / "PUBLIC.md").write_text("verified\n")
    status = sync_into_clone(source, clone, CANONICAL, confirmed=True)
    after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=clone, check=True,
        capture_output=True, text=True,
    ).stdout.strip()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=clone, check=True,
        capture_output=True, text=True,
    ).stdout
    assert before == after
    assert staged == ""
    assert "PUBLIC.md" in status and (clone / "PUBLIC.md").is_file()


def test_preflight_rejects_executable_git_config(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    _git(clone, "config", "core.hooksPath", str(tmp_path / "hooks"))
    with pytest.raises(SyncError, match="unsafe executable or redirecting"):
        preflight_clone(clone, CANONICAL, confirmed=True)


def test_preflight_rejects_obfuscated_filter_config(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    _git(clone, "config", "filter.evil.clean", "sh -c 'exit 1'")
    config = clone / ".git" / "config"
    config.write_text(config.read_text().replace('[filter "evil"]', '[filter\t"evil"]'))
    with pytest.raises(SyncError, match="unsafe executable or redirecting"):
        preflight_clone(clone, CANONICAL, confirmed=True)


def test_preflight_rejects_remote_with_user_or_port(tmp_path: Path) -> None:
    clone = _clone(
        tmp_path,
        "ssh://evil@github.com:2222/bannff/python-software-factory.git",
    )
    with pytest.raises(SyncError, match="unsafe remote transport"):
        preflight_clone(clone, CANONICAL, confirmed=True)


def test_preflight_rejects_legacy_dotted_filter_section(tmp_path: Path) -> None:
    clone = _clone(tmp_path)
    _git(clone, "config", "filter.evil.clean", "sh -c 'exit 1'")
    config = clone / ".git" / "config"
    config.write_text(config.read_text().replace('[filter "evil"]', '[filter.evil]'))
    with pytest.raises(SyncError, match="unsafe executable or redirecting"):
        preflight_clone(clone, CANONICAL, confirmed=True)
