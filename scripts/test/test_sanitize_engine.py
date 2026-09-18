"""Focused transform confinement and token-awareness tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from sanitize import engine
from sanitize.safety import SafetyError, assert_no_symlinks, validate_policy_paths


def test_delete_path_traversal_is_rejected_before_delete(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("keep")
    with pytest.raises(SafetyError, match="unsafe relative path"):
        engine.delete_paths(tree, {"delete_paths": ["../outside.txt"]}, engine.Report())
    assert outside.read_text() == "keep"


def test_replacement_path_traversal_is_rejected(tmp_path: Path) -> None:
    tree, replacements = tmp_path / "tree", tmp_path / "replacements"
    tree.mkdir()
    replacements.mkdir()
    with pytest.raises(SafetyError):
        validate_policy_paths(
            {"replace_files": ["../../secret"]}, tree, replacements,
        )


def test_symlink_anywhere_in_source_is_rejected(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    target = tmp_path / "target.txt"
    target.write_text("secret")
    (tree / "linked.txt").symlink_to(target)
    with pytest.raises(SafetyError, match="symlink forbidden"):
        assert_no_symlinks(tree)


def test_symlink_parent_blocks_policy_write(tmp_path: Path) -> None:
    tree, replacements = tmp_path / "tree", tmp_path / "replacements"
    tree.mkdir()
    replacements.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (tree / "redirect").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SafetyError, match="symlink in confined path"):
        validate_policy_paths(
            {"replace_files": ["redirect/file.txt"]}, tree, replacements,
        )


def test_python_identifier_rename_preserves_strings_comments_and_js(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    python = tree / "sample.py"
    javascript = tree / "sample.ts"
    python.write_text('OldName = 1\ntext = "OldName"\n# OldName\nprint(OldName)\n')
    javascript.write_text('// OldName\nconst value = "OldName";\nOldName();\n')
    report = engine.Report()
    engine.rename_symbols(tree, {"rename_symbols": {"OldName": "NewName"}}, report)
    assert python.read_text() == (
        'NewName = 1\ntext = "OldName"\n# OldName\nprint(NewName)\n'
    )
    assert javascript.read_text() == '// OldName\nconst value = "OldName";\nOldName();\n'
    assert report.renamed == {"sample.py": 2}


def test_anchored_patch_failure_is_loud(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "module.py").write_text("actual\n")
    policy = {
        "patches": [{
            "path": "module.py",
            "edits": [{"old": "missing\n", "new": "replacement\n"}],
        }],
    }
    with pytest.raises(engine.PolicyError, match="anchor not found"):
        engine.apply_patches(tree, policy, engine.Report())
    assert (tree / "module.py").read_text() == "actual\n"


def test_scrub_prose_does_not_rewrite_code_contracts(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "README.md").write_text("PrivateName\n")
    (tree / "contract.py").write_text('NAME = "PrivateName"\n')
    policy = {
        "scrub_prose": {
            "extensions": [".md", ".txt"],
            "filenames": [],
            "terms": [{"from": "PrivateName", "to": "PublicName"}],
        },
    }
    engine.scrub_prose(tree, policy, engine.Report())
    assert (tree / "README.md").read_text() == "PublicName\n"
    assert (tree / "contract.py").read_text() == 'NAME = "PrivateName"\n'
