"""Tests for the registry/launch_validator pre-flight gate (bd-2xbi Wave 1.2).

The validator is a pure stdlib function. We exercise it against
the real on-disk skills directory via ``skills_dir()`` — no
mocking — to confirm it gates the templated-skill failure mode
that QA tester's R2 issue identified at Wave 1.0.

bd python-factory-a4h7 migrated ``rt-sast-scan`` from a graph
(nodes/edges) to a workflow (factory key). The validator now
routes workflow-kind configs through the factory and scans the
rendered prompts. The IDOR happy path / unsupported-vuln-class
cases keep working transparently because the factory pre-renders
``{{vuln_class}}`` → static skill ref → on-disk lookup.

Coverage:
- IDOR + ``rt-sast-scan`` → no errors (rendered refs resolve).
- XSS / SQLi / SSRF / CSRF / Path_Traversal + ``rt-sast-scan``
  → at least one error referencing the missing
  ``<vuln_class>-code-scan`` skill.
- Missing ``vuln_class`` in context → ``Missing required context
  variable: vuln_class`` plus errors for every other declared
  context_var.
- Static-only swarm (``RECON_SWARM``) + valid context → no errors.
- Templated swarm (``SAST_SCAN_SWARM``) + invalid vuln_class
  → at least one templated-ref error.
- Hypothesis property: any context where ``vuln_class`` is not
  in ``supported_classes()`` produces at least one error.
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from factory.agent.registry.defaults_code_scan import SAST_SCAN_GRAPH
from factory.agent.registry.defaults_code_scan_swarm import SAST_SCAN_SWARM
from factory.agent.registry.defaults_redteam_swarms import RECON_SWARM
from factory.agent.registry.launch_validator import (
    skills_dir,
    validate_launch_context,
)
from factory.agent.registry.vuln_class_config import supported_classes


def _ctx(vuln_class: str) -> dict[str, object]:
    """Full SAST context for a given vuln_class (lowercase folder form)."""
    return {
        "vuln_class": vuln_class,
        "target_app": "demo-app",
        "run_id": "r-001",
        "target_packages": "pkg-a,pkg-b",
        "sast_workspace": "/tmp/sast",
    }


# --- IDOR happy path -------------------------------------------------

def test_idor_sast_scan_resolves_clean() -> None:
    """idor-code-scan + idor-validate exist on disk → no errors."""
    errors = validate_launch_context(SAST_SCAN_GRAPH, _ctx("idor"))
    assert errors == [], errors


def test_run_graph_normalizes_vuln_class_for_validator() -> None:
    """Launcher-boundary fix for bd-s1g. Mixed-case vuln_class (as
    docstring example shows) must validate clean after the
    .lower() normalization. The validator itself stays pure;
    this test exercises the launcher's responsibility."""
    # Simulate run_graph.py's normalization step.
    context = {"vuln_class": "IDOR", "target_app": "demo-app",
               "run_id": "r-001", "target_packages": "pkg-a",
               "sast_workspace": "/tmp/sast"}
    if "vuln_class" in context and isinstance(context["vuln_class"], str):
        context["vuln_class"] = context["vuln_class"].lower()
    errors = validate_launch_context(SAST_SCAN_GRAPH, context)
    assert errors == [], errors


# --- Missing-skill-on-disk by vuln_class ----------------------------

@pytest.mark.parametrize(
    "vuln_class",
    ["xss", "sqli", "ssrf", "csrf", "path-traversal"],
)
def test_unsupported_vuln_class_flags_missing_skill(vuln_class: str) -> None:
    """Every other vuln_class lacks an on-disk skill folder today."""
    errors = validate_launch_context(SAST_SCAN_GRAPH, _ctx(vuln_class))
    code_scan_hits = [e for e in errors if f"{vuln_class}-code-scan" in e]
    assert code_scan_hits, errors


# --- Missing required context vars ----------------------------------

def test_missing_context_vars_listed_individually() -> None:
    """Empty context fails every declared context_var with a clear msg."""
    errors = validate_launch_context(SAST_SCAN_GRAPH, {})
    expected = {
        "Missing required context variable: vuln_class",
        "Missing required context variable: target_app",
        "Missing required context variable: run_id",
        "Missing required context variable: target_packages",
        "Missing required context variable: sast_workspace",
    }
    assert expected.issubset(set(errors)), errors


def test_partial_context_only_flags_missing() -> None:
    """Provided vars don't trigger the missing-var error."""
    errors = validate_launch_context(
        SAST_SCAN_GRAPH, {"vuln_class": "idor"}
    )
    assert "Missing required context variable: vuln_class" not in errors
    assert "Missing required context variable: target_app" in errors


# --- Swarm coverage --------------------------------------------------

def test_static_only_swarm_resolves_clean() -> None:
    """RECON_SWARM has no templated refs and no context_vars declared."""
    errors = validate_launch_context(
        RECON_SWARM, {"run_id": "r-001", "target_app": "demo-app"}
    )
    assert errors == [], errors


def test_templated_swarm_flags_missing_skill() -> None:
    """SAST_SCAN_SWARM has live `{{vuln_class}}-code-scan` refs."""
    errors = validate_launch_context(SAST_SCAN_SWARM, _ctx("xss"))
    assert any("xss-code-scan" in e for e in errors), errors


# --- skills_dir accessor wiring -------------------------------------

def test_skills_dir_resolves_to_real_inventory() -> None:
    """skills_dir() must point at the same folder AgentSkills loads."""
    base = skills_dir()
    assert base.is_dir(), base
    assert (base / "idor-code-scan" / "SKILL.md").is_file()


def test_explicit_skills_dir_overrides_default(tmp_path) -> None:
    """Passing skills_dir_path lets callers swap inventories."""
    # Empty tmp dir → idor-code-scan not present → error.
    errors = validate_launch_context(
        SAST_SCAN_GRAPH, _ctx("idor"), skills_dir_path=tmp_path
    )
    assert any("idor-code-scan" in e for e in errors), errors


# --- Hypothesis property: unsupported vuln_class always errs --------

# Lowercase folder-name form. Filter out any class that happens to
# match a real on-disk skill folder (defensive — currently only
# 'idor' has a code-scan/validate pair).
_ON_DISK_LOWER = {p.name for p in skills_dir().iterdir() if p.is_dir()}
_SUPPORTED_LOWER = {c.lower() for c in supported_classes()}


@settings(max_examples=50, deadline=None)
@given(
    bogus=st.text(
        alphabet="abcdefghijklmnopqrstuvwxyz",
        min_size=3, max_size=12,
    ).filter(
        lambda s: (
            s not in _SUPPORTED_LOWER
            and f"{s}-code-scan" not in _ON_DISK_LOWER
            and f"{s}-validate" not in _ON_DISK_LOWER
        )
    ),
)
def test_unsupported_vuln_class_always_errs(bogus: str) -> None:
    """Any vuln_class without backing skills produces ≥1 error."""
    errors = validate_launch_context(SAST_SCAN_GRAPH, _ctx(bogus))
    assert errors, f"expected errors for vuln_class='{bogus}', got none"
