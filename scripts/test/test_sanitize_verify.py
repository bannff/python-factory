"""Focused fail-closed scanning and structural integrity tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from sanitize.safety import validate_policy_paths
from sanitize.verify import VerifyResult, scan_forbidden
from sanitize.verify_structure import find_deleted_imports, structural_checks

POLICY_PATH = Path(__file__).parents[1] / "sanitize" / "policy.yaml"


def test_forbidden_scan_honors_only_path_scoped_exception(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed.md"
    denied = tmp_path / "denied.md"
    allowed.write_text("SECRET public fixture\n")
    denied.write_text("SECRET leak\n")
    policy = {
        "forbid": [{"name": "secret", "pattern": "SECRET"}],
        "allow_exceptions": [{
            "path": "allowed.md", "pattern": "SECRET public fixture",
            "reason": "documented public fixture",
        }],
    }
    result = VerifyResult()
    scan_forbidden(tmp_path, policy, result)
    assert [(item.path, item.rule) for item in result.findings] == [
        ("denied.md", "secret"),
    ]
    assert len(result.exceptions_applied) == 1


def test_deleted_absolute_import_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "components" / "live" / "src" / "factory" / "live"
    source.mkdir(parents=True)
    (source / "module.py").write_text("import factory.dead.runtime\n")
    policy = {"delete_paths": ["components/dead/"]}
    assert find_deleted_imports(tmp_path, policy) == [
        "components/live/src/factory/live/module.py -> factory.dead.runtime",
    ]


def test_deleted_relative_import_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "components" / "live" / "src" / "factory" / "live"
    source.mkdir(parents=True)
    (source / "module.py").write_text("from .deleted import VALUE\n")
    policy = {
        "delete_paths": ["components/live/src/factory/live/deleted.py"],
    }
    assert find_deleted_imports(tmp_path, policy) == [
        "components/live/src/factory/live/module.py -> factory.live.deleted",
    ]


def test_structural_check_rejects_surviving_sanitizer_tooling(tmp_path: Path) -> None:
    (tmp_path / "components").mkdir()
    (tmp_path / "bases").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "sanitize_public.py").write_text("pass\n")
    (tmp_path / "pyproject.toml").write_text("")
    policy = {
        "delete_paths": ["scripts/sanitize/", "scripts/sanitize_public.py"],
        "structural": {
            "expected_components": 0,
            "expected_bases": 0,
            "strip_brick_maps": [],
            "pyproject_files": ["pyproject.toml"],
            "require_brick_yaml": True,
            "require_no_dangling_index": False,
        },
    }
    result = VerifyResult()
    structural_checks(tmp_path, policy, result)
    checks = {name: passed for name, passed, _ in result.structural}
    assert not checks["sanitizer_tooling_removed"]


def test_real_policy_enforces_publication_constraints(tmp_path: Path) -> None:
    policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    deleted = set(policy["delete_paths"])
    assert "scripts/sanitize/" in deleted
    assert "scripts/sanitize_public.py" in deleted
    assert ".agents/steering/relativix-fleet-intelligence.md" in deleted
    assert policy["scrub_prose"]["extensions"] == [".md", ".txt"]
    assert policy["scrub_prose"]["filenames"] == []
    assert policy["replace_files"] == [
        "components/agent/src/factory/agent/registry/redteam_playbooks.py",
        ".SANITIZATION_MANIFEST.md",
    ]
    assert "Rando" not in POLICY_PATH.read_text(encoding="utf-8")
    tree, replacements = tmp_path / "tree", tmp_path / "replacements"
    tree.mkdir()
    replacements.mkdir()
    validate_policy_paths(policy, tree, replacements)


def test_deleted_from_import_and_dynamic_import_are_detected(tmp_path: Path) -> None:
    source = tmp_path / "components" / "live" / "src" / "factory" / "live"
    source.mkdir(parents=True)
    (source / "module.py").write_text(
        "from factory import dead\n"
        "import importlib\n"
        "from importlib import import_module as load\n"
        "importlib.import_module('factory.dead.runtime')\n"
        "load('factory.dead.alias')\n"
    )
    policy = {"delete_paths": ["components/dead/"]}
    assert find_deleted_imports(tmp_path, policy) == [
        "components/live/src/factory/live/module.py -> factory.dead",
        "components/live/src/factory/live/module.py -> factory.dead.alias",
        "components/live/src/factory/live/module.py -> factory.dead.runtime",
    ]
