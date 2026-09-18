"""QA verification tests for bd python-factory-m4cp (post bd-nrt5).

Author: qa-tester subagent. Asserts m4cp invariants, post-nrt5
adjusted: ``RT_SANDBOX_SETUP_SWARM`` was deleted along with
``REDTEAM_V2_SWARMS`` (the v2 back-compat shell — see
defaults_redteam_meta_graph.py docstring), so the original
preservation/dedup tests are gone. This file now pins the surviving
m4cp invariants:
  - sandbox-setup factory pure-constant under arbitrary context
  - factory returns fresh lists (no shared mutable state)
  - concurrent invocation produces identical results
  - WorkflowConfig roundtrips deterministically
  - rt-eval-tail emitted exactly once via REDTEAM_PIPELINE_SWARMS

Stays under 200 LOC. ``hypothesis.settings(max_examples=50)`` per
QA-tester rule. Public-API only — no underscore-prefixed access.
"""
from __future__ import annotations

import threading

import pytest
from hypothesis import given, settings, strategies as st

from factory.agent.registry.defaults_redteam_meta_graph import (
    REDTEAM_PIPELINE_GRAPH, REDTEAM_PIPELINE_SWARMS,
)
from factory.agent.registry.defaults_sandbox_graph import (
    SANDBOX_GRAPHS, SANDBOX_SETUP_REGISTRATION,
    build_sandbox_setup_tasks,
)
from factory.agent.registry.factories import (
    FACTORY_REGISTRY, get_factory, known_factories,
)


# --- A. Meta-pipeline references the migrated workflow ---------------

def test_redteam_pipeline_sandbox_node_targets_workflow():
    """sandbox node is a nested type=graph ref to sandbox-setup."""
    sandbox_node = next(n for n in REDTEAM_PIPELINE_GRAPH["nodes"]
                        if n["id"] == "sandbox")
    assert sandbox_node["type"] == "graph"
    assert sandbox_node["graph_id"] == "sandbox-setup"


def test_redteam_pipeline_recon_node_targets_workflow():
    """recon node is a nested type=graph ref to recon-app."""
    recon_node = next(n for n in REDTEAM_PIPELINE_GRAPH["nodes"]
                      if n["id"] == "recon")
    assert recon_node["type"] == "graph"
    assert recon_node["graph_id"] == "recon-app"


# --- B. EVAL tail wiring (post-nrt5) --------------------------------

def test_redteam_pipeline_eval_node_resolves_eval_tail_swarm():
    """rt-eval-tail must be present so the eval node resolves."""
    assert "rt-eval-tail" in {s["id"] for s in REDTEAM_PIPELINE_SWARMS}


def test_redteam_pipeline_eval_tail_emitted_exactly_once():
    """Post-nrt5 there's no dedup loop — REDTEAM_PIPELINE_SWARMS is
    a flat list of three swarms, not an aggregated set."""
    ids = [s["id"] for s in REDTEAM_PIPELINE_SWARMS]
    assert ids.count("rt-eval-tail") == 1, (
        f"rt-eval-tail emitted {ids.count('rt-eval-tail')} times"
    )


def test_redteam_pipeline_graph_eval_node_uses_correct_swarm_id():
    """Eval node references rt-eval-tail (not v2-suffixed)."""
    eval_node = next(n for n in REDTEAM_PIPELINE_GRAPH["nodes"]
                     if n["id"] == "eval")
    assert eval_node["swarm_id"] == "rt-eval-tail"


# --- C. Pure-constant factory + idempotency -------------------------

def test_factory_returns_fresh_lists_each_call():
    """Mutating returned list must not poison subsequent calls."""
    a = build_sandbox_setup_tasks()
    a.clear()
    b = build_sandbox_setup_tasks()
    assert len(b) == 5, "factory leaks shared state between calls"


def test_factory_returns_fresh_tools_lists():
    """Per-task tools list is a fresh copy (``_task`` does list())."""
    a = build_sandbox_setup_tasks()
    a[0]["tools"].clear()
    b = build_sandbox_setup_tasks()
    assert len(b[0]["tools"]) >= 1, "task tools list aliased"


@settings(max_examples=50, deadline=None)
@given(extra_keys=st.dictionaries(
    keys=st.text(min_size=1, max_size=10),
    values=st.one_of(st.text(max_size=50), st.integers(),
                     st.none(), st.booleans()),
    max_size=5,
))
def test_factory_is_pure_constant_under_arbitrary_context(extra_keys):
    """Sandbox-setup factory is documented pure-constant. Hypothesis
    pins this — arbitrary context must not change output."""
    factory = get_factory("sandbox_setup")
    assert factory({}) == factory(extra_keys), (
        "sandbox-setup factory leaked context vars"
    )


def test_factory_concurrent_invocation_safety():
    """Threaded callers each get equivalent task lists."""
    factory = get_factory("sandbox_setup")
    results: list[list[dict]] = []
    lock = threading.Lock()

    def call() -> None:
        out = factory({"run_id": "t", "target_app": "x"})
        with lock:
            results.append(out)

    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 8
    canonical = results[0]
    for i, r in enumerate(results[1:], start=1):
        assert r == canonical, f"Thread {i} divergent — race condition"


# --- D. Registry surface invariants ---------------------------------

def test_known_factories_is_sorted():
    """Discovery surface stable across imports."""
    keys = known_factories()
    assert keys == sorted(keys)


def test_factory_registry_keys_match_known():
    """FACTORY_REGISTRY keys() and known_factories() agree."""
    assert set(FACTORY_REGISTRY.keys()) == set(known_factories())


def test_unknown_factory_raises_keyerror():
    """get_factory rejects unknown keys — no silent fallthrough."""
    with pytest.raises(KeyError):
        get_factory("does-not-exist")


# --- E. WorkflowConfig registration shape ---------------------------

def test_sandbox_setup_registration_has_pure_data_factory_key():
    """factory= must be a string registry key (Option A, mem 33b12ebb)."""
    assert isinstance(SANDBOX_SETUP_REGISTRATION.factory, str)
    assert not callable(SANDBOX_SETUP_REGISTRATION.factory)


def test_sandbox_graphs_is_singleton_workflow_list():
    """SANDBOX_GRAPHS is a 1-element list of WorkflowConfig."""
    assert len(SANDBOX_GRAPHS) == 1
    assert SANDBOX_GRAPHS[0] is SANDBOX_SETUP_REGISTRATION


def test_sandbox_setup_reg_kind_is_workflow():
    """kind=workflow drives WorkflowExecutor dispatch."""
    assert SANDBOX_SETUP_REGISTRATION.kind == "workflow"
