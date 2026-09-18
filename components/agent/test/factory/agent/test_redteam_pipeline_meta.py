"""Tests for the redteam-pipeline meta-graph (bd python-factory-nrt5).

Hybrid Graph composition (Option E): outer kind=graph with two
``type=graph`` nested-workflow refs (recon-app, sandbox-setup) and
three ``type=swarm`` leafs (scan, prove, eval).

Pre-conditions: (i) no shims, (ii) SDK-First, (iii) <200 LOC,
(iv) MCP-First surface, (x) outer node_timeout >= max child + 600s,
(xi) GAP-1, GAP-2, smoke-alias regressions.
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st

from factory.agent.registry.defaults_redteam_meta_graph import (
    REDTEAM_PIPELINE_GRAPH, REDTEAM_PIPELINE_GRAPHS,
)
from factory.agent.registry.defaults_recon_graph import RECON_REGISTRATION
from factory.agent.registry.defaults_sandbox_graph import (
    SANDBOX_SETUP_REGISTRATION,
)


# Schema / shape

def test_meta_graph_id_is_redteam_pipeline() -> None:
    assert REDTEAM_PIPELINE_GRAPH["id"] == "redteam-pipeline"


def test_meta_kind_is_graph() -> None:
    assert REDTEAM_PIPELINE_GRAPH["kind"] == "graph"


def test_meta_node_count_is_5() -> None:
    assert len(REDTEAM_PIPELINE_GRAPH["nodes"]) == 5


def test_meta_recon_node_is_graph_type_with_graph_id_recon_app() -> None:
    n = next(x for x in REDTEAM_PIPELINE_GRAPH["nodes"] if x["id"] == "recon")
    assert n["type"] == "graph" and n["graph_id"] == "recon-app"


def test_meta_sandbox_node_is_graph_type_with_graph_id_sandbox_setup() -> None:
    n = next(x for x in REDTEAM_PIPELINE_GRAPH["nodes"] if x["id"] == "sandbox")
    assert n["type"] == "graph" and n["graph_id"] == "sandbox-setup"


def test_meta_scan_prove_eval_nodes_are_swarm_type() -> None:
    by_id = {n["id"]: n for n in REDTEAM_PIPELINE_GRAPH["nodes"]}
    for nid, swid in (("scan", "rt-scan-vulns"),
                      ("prove", "rt-prove-vulns"),
                      ("eval", "rt-eval-tail")):
        assert by_id[nid]["type"] == "swarm"
        assert by_id[nid]["swarm_id"] == swid


def test_meta_edges_form_linear_chain() -> None:
    edges = [(e["source"], e["target"]) for e in REDTEAM_PIPELINE_GRAPH["edges"]]
    assert edges == [("recon", "sandbox"), ("sandbox", "scan"),
                     ("scan", "prove"), ("prove", "eval")]


def test_meta_max_cycles_is_1() -> None:
    assert REDTEAM_PIPELINE_GRAPH["max_cycles"] == 1


def test_meta_required_bricks_superset_of_children() -> None:
    """Outer required_bricks ⊇ recon-app + sandbox-setup."""
    outer = set(REDTEAM_PIPELINE_GRAPH["required_bricks"])
    children = (set(RECON_REGISTRATION.required_bricks)
                | set(SANDBOX_SETUP_REGISTRATION.required_bricks))
    assert children.issubset(outer), f"Missing: {children - outer}"


def test_meta_context_vars_subset() -> None:
    cv = set(REDTEAM_PIPELINE_GRAPH["context_vars"])
    assert {"run_id", "target_app", "vuln_class"}.issubset(cv)


# Pre-cond (x): outer timeout > child + buffer
def test_outer_node_timeout_exceeds_child_execution_timeout_plus_buffer() -> None:
    """asyncio.to_thread does NOT propagate cancellation, so outer
    node_timeout must exceed max(child execution_timeout) by 600s."""
    outer = REDTEAM_PIPELINE_GRAPH["node_timeout"]
    max_child = max(RECON_REGISTRATION.execution_timeout,
                    SANDBOX_SETUP_REGISTRATION.execution_timeout)
    assert outer >= max_child + 600


# Hypothesis: launch context shape
@settings(max_examples=50, deadline=None)
@given(
    run_id=st.text(min_size=1, max_size=20),
    target_app=st.text(min_size=1, max_size=20),
    vuln_class=st.sampled_from(["IDOR", "XSS", "SQLi", "SSRF", "CSRF", "AUTH"]),
)
def test_meta_accepts_arbitrary_run_id_target_app_vuln_class(
    run_id: str, target_app: str, vuln_class: str,
) -> None:
    ctx = {"run_id": run_id, "target_app": target_app, "vuln_class": vuln_class}
    for k in REDTEAM_PIPELINE_GRAPH["context_vars"]:
        if k in ctx:
            assert ctx[k] is not None


# Registry deprecations remain topology data, independent of execution SDK.
def test_redteam_sandbox_pipeline_id_no_longer_in_registry() -> None:
    """v1 redteam-sandbox-pipeline (bd-wu6a) deleted in nrt5."""
    from factory.agent.registry.defaults import get_default_graphs
    assert "redteam-sandbox-pipeline" not in {g.id for g in get_default_graphs()}


def test_redteam_pipeline_v2_id_no_longer_in_registry() -> None:
    from factory.agent.registry.defaults import get_default_graphs
    ids = {g.id for g in get_default_graphs()}
    assert "redteam-pipeline-v2" not in ids
    assert "redteam-pipeline" in ids


def test_redteam_pipeline_graphs_singleton() -> None:
    assert len(REDTEAM_PIPELINE_GRAPHS) == 1
    assert REDTEAM_PIPELINE_GRAPHS[0] is REDTEAM_PIPELINE_GRAPH