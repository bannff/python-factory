"""Tests for the recon factory (bd python-factory-s5ev).

Mirrors ``test_factories.py`` for the SAST canary, adapted to the
recon shape: 4 tasks (recon-lead → recon-verify → recon-summary →
eval-scorer), pure-constant factory (no per-call inputs), eval-tail
embedded as ``eval-scorer`` task.

Pre-condition (i) of strands-expert verdict d6dc80c0: the recon
factory must be pure-deterministic — Hypothesis property pins
idempotency over arbitrary contexts (recon reads NO context).
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st

from factory.agent.registry.defaults_recon_graph import (
    RECON_REGISTRATION,
    build_recon_tasks,
)
from factory.agent.registry.factories import (
    FACTORY_REGISTRY,
    get_factory,
    known_factories,
)


# --- Schema / shape ----------------------------------------------------

def test_recon_renders_4_tasks() -> None:
    """build_recon_tasks returns the canonical 4-task DAG."""
    tasks = build_recon_tasks()
    assert len(tasks) == 4
    assert [t["task_id"] for t in tasks] == [
        "recon-lead", "recon-verify", "recon-summary", "eval-scorer",
    ]


def test_recon_has_required_fields() -> None:
    """Every task carries strands_tools.workflow expected fields."""
    tasks = build_recon_tasks()
    for t in tasks:
        for field in (
            "task_id", "description", "system_prompt",
            "tools", "model_provider", "model_settings",
            "dependencies", "priority", "timeout",
        ):
            assert field in t, f"{t['task_id']}: missing {field}"
        assert t["model_provider"] == "bedrock"
        assert "model_id" in t["model_settings"]
        assert isinstance(t["tools"], list) and t["tools"]


def test_recon_tools_are_bare_names() -> None:
    """All tool names are bare — no dot-prefixed (workflow.py L329-336)."""
    tasks = build_recon_tasks()
    for t in tasks:
        for tn in t["tools"]:
            assert "." not in tn, (
                f"{t['task_id']}: tool '{tn}' must be bare name"
            )


def test_recon_no_unresolved_template_vars_owned_by_factory() -> None:
    """Factory pre-renders nothing — recon takes no context.

    ``{{run_id}}`` and ``{{target_app}}`` are template markers
    resolved by ``WorkflowExecutor`` at create time. The factory
    itself owns no rendering, so the prompts come back with the
    markers intact.
    """
    tasks = build_recon_tasks()
    # The recon-lead/verify/summary prompts include {{run_id}} and
    # {{target_app}} markers. Eval-scorer additionally includes
    # {{metric_prefix}}, {{eval_evaluators}}, etc. — all expected.
    lead = tasks[0]["system_prompt"]
    assert "{{run_id}}" in lead and "{{target_app}}" in lead


def test_recon_dependencies_form_valid_dag() -> None:
    """Topological sort drains all 4 tasks."""
    tasks = build_recon_tasks()
    ids = {t["task_id"] for t in tasks}
    for t in tasks:
        for dep in t["dependencies"]:
            assert dep in ids, f"{t['task_id']}: bad dep {dep}"
    indeg = {t["task_id"]: len(t["dependencies"]) for t in tasks}
    by_dep = {t["task_id"]: list(t["dependencies"]) for t in tasks}
    queue = [tid for tid, n in indeg.items() if n == 0]
    drained = 0
    while queue:
        tid = queue.pop(0)
        drained += 1
        for other, deps in by_dep.items():
            if tid in deps:
                deps.remove(tid)
                indeg[other] -= 1
                if indeg[other] == 0:
                    queue.append(other)
    assert drained == len(tasks), "DAG has a cycle"


def test_recon_has_pause_boundary_before_eval() -> None:
    """eval-scorer.dependencies == ['recon-summary'] — pause boundary."""
    tasks = build_recon_tasks()
    by_id = {t["task_id"]: t for t in tasks}
    assert by_id["eval-scorer"]["dependencies"] == ["recon-summary"]


# --- Hypothesis property: pure-determinism ----------------------------

@settings(max_examples=50, deadline=None)
@given(
    run_id=st.text(min_size=1, max_size=20),
    target_app=st.text(min_size=1, max_size=20),
)
def test_recon_factory_is_pure_over_any_context(
    run_id: str, target_app: str,
) -> None:
    """Recon factory reads NO context — output identical regardless."""
    factory = get_factory("recon")
    a = factory({"run_id": run_id, "target_app": target_app})
    b = factory({"run_id": "different", "target_app": "other"})
    assert a == b, "recon factory leaked context vars"


# --- Registry surface --------------------------------------------------

def test_factory_registry_resolves_recon() -> None:
    """The registration's factory key is in FACTORY_REGISTRY."""
    key = RECON_REGISTRATION.factory
    assert key in FACTORY_REGISTRY
    factory = get_factory(key)
    tasks = factory({"run_id": "r1", "target_app": "webgoat"})
    assert len(tasks) == 4


def test_known_factories_includes_recon() -> None:
    """Discovery surface for tooling."""
    assert "recon" in known_factories()


# --- Registration shape -----------------------------------------------

def test_recon_registration_carries_string_factory_key() -> None:
    """Pre-condition (ii): factory is a string registry key, not callable."""
    assert isinstance(RECON_REGISTRATION.factory, str)
    assert RECON_REGISTRATION.factory == "recon"


def test_recon_registration_id_for_alias_resolution() -> None:
    """recon-app id stays for back-compat with agent_invoke_graph."""
    assert RECON_REGISTRATION.id == "recon-app"
    assert RECON_REGISTRATION.kind == "workflow"


def test_recon_registration_required_bricks() -> None:
    """Required bricks match design memory d6dc80c0."""
    assert set(RECON_REGISTRATION.required_bricks) == {
        "graph", "veritas", "memory", "sandbox", "evals", "metrics",
    }


def test_recon_registration_context_vars() -> None:
    """Recon takes only run_id + target_app per design memory d6dc80c0."""
    assert set(RECON_REGISTRATION.context_vars) == {"run_id", "target_app"}


# --- Skill activation in factory-rendered prompts ---------------------
# Replaces the 3 ``_RG`` ``PROMPT_CASES`` entries from
# ``test_default_prompts_skills.py``. Recon prompts are no longer
# module-level constants — they're consumed via build_recon_tasks().

RECON_PROMPT_CASES: list[tuple[int, str, str]] = [
    # (task_index, expected_skill, expected_role)
    (0, "veritas-recon", "security recon lead"),
    (1, "veritas-recon", "recon verifier"),
    (2, "veritas-recon", "recon summary"),
]


@pytest.mark.parametrize(
    "idx, expected_skill, expected_role",
    RECON_PROMPT_CASES,
    ids=[f"recon[{i}]" for i, _, _ in RECON_PROMPT_CASES],
)
def test_recon_factory_prompt_is_thin_and_skill_aware(
    idx: int, expected_skill: str, expected_role: str,
) -> None:
    """build_recon_tasks()[i].system_prompt mirrors SKILL.md shape."""
    tasks = build_recon_tasks()
    prompt = tasks[idx]["system_prompt"]
    assert isinstance(prompt, str)
    assert len(prompt) < 1500, f"recon[{idx}] is {len(prompt)} chars"
    assert expected_skill in prompt
    assert "skills tool" in prompt
    assert expected_role in prompt
