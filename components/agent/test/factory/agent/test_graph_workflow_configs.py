"""Graph workflow config integrity tests.

Validates redteam-pipeline meta graph + leaf swarms (eval-tail,
scan-vulns, prove-vulns). Properties: node types, swarm_id refs,
prompt content, no dupes, eval tail model/sections/template vars,
edge validity, LOC limits.

bd python-factory-nrt5: REDTEAM_V2_* renamed to REDTEAM_PIPELINE_*;
recon-app/sandbox-setup are kind=workflow registrations and stay in
test_factories_recon.py / test_factories_sandbox_setup.py.
"""
from __future__ import annotations
from pathlib import Path

from factory.agent.registry.defaults_recon_graph import RECON_GRAPHS
from factory.agent.registry.defaults_sandbox_graph import SANDBOX_GRAPHS
from factory.agent.registry.defaults_redteam_meta_graph import (
    REDTEAM_PIPELINE_GRAPH, REDTEAM_PIPELINE_GRAPHS,
    REDTEAM_PIPELINE_SWARMS,
)
from factory.agent.registry.defaults_eval_tail import RT_EVAL_TAIL_SWARM
from factory.agent.registry.redteam_eval_addenda import (
    EVAL_TAIL_PREAMBLE, EVAL_SESSION_SCORING, EVAL_METRICS_RECORDING,
)
from factory.agent.registry.models import NOVA2_LITE

_REG = (Path(__file__).resolve().parents[4]
        / "src" / "factory" / "agent" / "registry")
if not _REG.exists():
    _REG = (Path(__file__).resolve().parents[5]
            / "components" / "agent" / "src"
            / "factory" / "agent" / "registry")

# Workflow-kind registrations (e.g. recon-app post-s5ev) are
# WorkflowConfig instances without ``nodes``/``edges``. Filter them
# out of dict-iteration tests; they're covered by
# ``test_factories_recon.py`` instead.
ALL_GRAPHS = [
    g for g in (RECON_GRAPHS + SANDBOX_GRAPHS + [REDTEAM_PIPELINE_GRAPH])
    if isinstance(g, dict) and g.get("kind", "graph") == "graph"
]
# Post-nrt5: REDTEAM_PIPELINE_SWARMS is the canonical list (3 leafs);
# the meta-pipeline composes recon-app + sandbox-setup as nested
# workflows (type=graph nodes), not via swarm-id refs.
ALL_SWARMS: list[dict] = list(REDTEAM_PIPELINE_SWARMS)
_SWARM_IDS = {s["id"] for s in ALL_SWARMS}


def test_meta_pipeline_node_types_are_graph_or_swarm():
    """recon+sandbox are type=graph; scan+prove+eval are type=swarm."""
    by_id = {n["id"]: n for n in REDTEAM_PIPELINE_GRAPH["nodes"]}
    assert by_id["recon"]["type"] == "graph"
    assert by_id["sandbox"]["type"] == "graph"
    for nid in ("scan", "prove", "eval"):
        assert by_id[nid]["type"] == "swarm", (
            f"{nid} type={by_id[nid]['type']}"
        )


def test_meta_pipeline_swarm_ids_resolve_in_pipeline_swarms():
    """Each swarm-type node's swarm_id is in REDTEAM_PIPELINE_SWARMS."""
    for n in REDTEAM_PIPELINE_GRAPH["nodes"]:
        if n["type"] == "swarm":
            assert n["swarm_id"] in _SWARM_IDS, (
                f"{n['id']} refs unknown {n['swarm_id']}"
            )


def test_every_agent_has_nonempty_system_prompt():
    for sw in ALL_SWARMS:
        for a in sw["agents"]:
            p = a.get("system_prompt", "")
            assert p and p.strip(), (
                f"{sw['id']}/{a['id']} empty system_prompt"
            )


def test_no_duplicate_swarm_ids_in_pipeline_swarms():
    ids = [s["id"] for s in ALL_SWARMS]
    assert len(ids) == len(set(ids))


def test_config_files_under_200_loc():
    # redteam_recon_addenda.py and redteam_sandbox_addenda.py were
    # removed in Wave 1.1 (bd python-factory-2xbi). Workflow content
    # now lives in skills/veritas-recon/SKILL.md and
    # skills/sandbox-ops/SKILL.md, loaded via AgentSkills.
    for name in [
        "defaults_recon_graph.py", "defaults_sandbox_graph.py",
        "defaults_redteam_meta_graph.py", "defaults_eval_tail.py",
        "defaults_redteam_exploit.py", "redteam_eval_addenda.py",
    ]:
        p = _REG / name
        assert p.exists(), f"Missing: {name}"
        loc = len(p.read_text().splitlines())
        assert loc < 200, f"{name} is {loc} LOC (limit 200)"


def test_eval_tail_swarm_structure():
    s = RT_EVAL_TAIL_SWARM
    assert s["id"] == "rt-eval-tail"
    assert len(s["agents"]) == 1
    assert s["agents"][0]["id"] == "eval-scorer"


def test_eval_tail_uses_nova2_lite():
    assert RT_EVAL_TAIL_SWARM["agents"][0]["model"] == NOVA2_LITE


def test_eval_tail_prompt_contains_all_sections():
    prompt = RT_EVAL_TAIL_SWARM["agents"][0]["system_prompt"]
    assert EVAL_TAIL_PREAMBLE in prompt
    assert EVAL_SESSION_SCORING in prompt
    assert EVAL_METRICS_RECORDING in prompt


def test_eval_tail_prompt_has_template_variables():
    prompt = RT_EVAL_TAIL_SWARM["agents"][0]["system_prompt"]
    for var in ("{{metric_prefix}}", "{{eval_evaluators}}",
                "{{run_id}}", "{{target_app}}"):
        assert var in prompt, f"Missing template var: {var}"


def test_meta_pipeline_edges_reference_valid_nodes():
    nids = {n["id"] for n in REDTEAM_PIPELINE_GRAPH["nodes"]}
    for e in REDTEAM_PIPELINE_GRAPH.get("edges", []):
        assert e["source"] in nids, (
            f"edge src {e['source']} invalid"
        )
        assert e["target"] in nids, (
            f"edge tgt {e['target']} invalid"
        )


def test_redteam_pipeline_order():
    nodes = [n["id"] for n in REDTEAM_PIPELINE_GRAPH["nodes"]]
    assert nodes == ["recon", "sandbox", "scan", "prove", "eval"]
    edges = [(e["source"], e["target"])
             for e in REDTEAM_PIPELINE_GRAPH["edges"]]
    assert ("recon", "sandbox") in edges
    assert ("prove", "eval") in edges


def test_redteam_pipeline_swarms_includes_leaf_swarms():
    ids = {s["id"] for s in REDTEAM_PIPELINE_SWARMS}
    expected = {"rt-scan-vulns", "rt-prove-vulns", "rt-eval-tail"}
    assert expected.issubset(ids), f"Missing: {expected - ids}"


def test_redteam_pipeline_graphs_singleton():
    """REDTEAM_PIPELINE_GRAPHS is a 1-element list of meta-graph."""
    assert len(REDTEAM_PIPELINE_GRAPHS) == 1
    assert REDTEAM_PIPELINE_GRAPHS[0] is REDTEAM_PIPELINE_GRAPH
