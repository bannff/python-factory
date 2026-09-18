#!/usr/bin/env python3
"""Build a verified public snapshot; optionally sync a confirmed local clone.

Default invocation and ``--dry-run`` are non-destructive. ``--sync`` requires
confirmation, an absolute clone path, and its expected canonical origin. The
script never pushes.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from sanitize import engine, verify  # noqa: E402
from sanitize.cli import parse_args  # noqa: E402
from sanitize.safety import SafetyError, assert_no_symlinks, confined  # noqa: E402
from sanitize.sync import SyncError, sync_into_clone  # noqa: E402

PRIVATE = Path(__file__).resolve().parent.parent
POLICY = PRIVATE / "scripts" / "sanitize" / "policy.yaml"
REPLACEMENTS = PRIVATE / "scripts" / "sanitize" / "replacements"


def _git(arguments: list[str], cwd: Path) -> str:
    process = subprocess.run(
        ["git", *arguments], cwd=cwd, capture_output=True, text=True,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.strip())
    return process.stdout.strip()


def export_head(private: Path, destination: Path) -> str:
    """Export tracked files from a named commit, then reject archived links."""
    revision = _git(["rev-parse", "HEAD"], private)
    archive = destination.parent / "head.tar"
    with archive.open("wb") as stream:
        subprocess.run(
            ["git", "archive", "--format=tar", revision], cwd=private,
            stdout=stream, check=True,
        )
    destination.mkdir(parents=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(destination)], check=True)
    archive.unlink()
    assert_no_symlinks(destination)
    return revision


def regenerate_bricks_index(tree: Path) -> str:
    entries: dict[str, list[dict[str, Any]]] = {"components": [], "bases": []}
    for group in entries:
        root = confined(tree, group)
        for directory in sorted(root.iterdir()):
            brick = confined(tree, directory.relative_to(tree) / "BRICK.yaml")
            if brick.is_file():
                entries[group].append(yaml.safe_load(brick.read_text()) or {})
    output = confined(tree, "BRICKS_INDEX.yaml")
    document = {"schema_version": 1, "workspace": "python-factory", "bricks": entries}
    output.write_text(yaml.safe_dump(document, sort_keys=False, width=100), encoding="utf-8")
    return f"{len(entries['components'])} components + {len(entries['bases'])} bases"


def _private_tree_ready(private: Path) -> bool:
    lines = _git(["status", "--porcelain"], private).splitlines()
    modified = [line for line in lines if not line.startswith("??")]
    if modified:
        print("private tree has modified tracked files; commit before snapshot:")
        for line in modified[:40]:
            print(f"   {line}")
        return False
    untracked = [line for line in lines if line.startswith("??")]
    if untracked:
        print(f"note: {len(untracked)} untracked path(s) excluded by git archive")
    return True


def _verify(tree: Path, policy: dict[str, Any], skip_pytest: bool) -> verify.VerifyResult:
    result = verify.VerifyResult()
    verify.scan_forbidden(tree, policy, result)
    verify.structural_checks(tree, policy, result)
    if policy["structural"].get("require_compileall"):
        verify.run_compileall(tree, result)
    if policy["structural"].get("require_pytest_collect") and not skip_pytest:
        verify.run_pytest_collect(tree, result)
    return result


def main(arguments: list[str] | None = None) -> int:
    options = parse_args(arguments)
    if not _private_tree_ready(PRIVATE):
        return 2
    policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    workdir = Path(tempfile.mkdtemp(prefix="sanitize-public-"))
    tree = workdir / "tree"
    try:
        assert_no_symlinks(REPLACEMENTS)
        revision = export_head(PRIVATE, tree)
        report = engine.transform(tree, REPLACEMENTS, policy)
        detail = regenerate_bricks_index(tree)
        assert_no_symlinks(tree)
        print(f"policy v{policy['version']}; exported {revision[:12]}; {detail}")
        print(f"deleted={len(report.deleted)} replaced={len(report.replaced)} "
              f"patched={len(report.patched)} scrubbed={sum(report.scrubbed.values())}")
        result = _verify(tree, policy, options.skip_pytest)
        print(verify.render(result))
        if not result.ok:
            print("VERIFY FAILED -- nothing synced")
            return 1
        if not options.sync:
            print("dry-run passed; no clone was modified")
            return 0
        assert options.clone is not None and options.expected_remote is not None
        status = sync_into_clone(
            tree, options.clone, options.expected_remote, confirmed=options.confirmed,
            protected=(PRIVATE,),
        )
        post = _verify(options.clone, policy, False)
        print(verify.render(post))
        if not post.ok:
            print("POST-SYNC VERIFY FAILED -- clone remains uncommitted")
            return 1
        print(f"working tree synchronized; changed paths: {len(status.splitlines())}")
        print("NOT STAGED, COMMITTED, OR PUSHED. Review and publish manually.")
        return 0
    except (engine.PolicyError, SafetyError, SyncError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    finally:
        if options.keep_tree:
            print(f"output tree kept at: {tree}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
