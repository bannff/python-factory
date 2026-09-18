"""Red team meta-pipeline — hybrid Graph composition (bd nrt5).

Outer ``kind=graph`` (Strands GraphBuilder runtime). Recon and
sandbox stages are nested ``type=graph`` refs to the migrated
``kind=workflow`` registrations (recon-app, sandbox-setup); scan,
prove and eval are leaf ``type=swarm`` refs.

Pattern: Strands "nested multi-agent" primitive — see strands-expert
verdict 4490fa80. The local executor already supports recursive
dispatch (executors/graph_nodes.py:_build_nested_graph_node →
GraphNode → child GraphExecutor.run → WorkflowExecutor for
``kind=workflow`` children) post bd-nrt5 GAP-1 fix.

Rename history (bd nrt5):
  - ``redteam-pipeline-v2`` → ``redteam-pipeline`` (drop v2 suffix).
  - ``redteam-sandbox-pipeline`` (bd-wu6a, v1) DELETED — its
    setup-sandbox CFN logic is superseded by the LocalStack-direct
    sandbox-setup workflow; its pull-artifacts is subsumed by recon-
    app via the cdk-analysis skill.
  - ``RT_RECON_SWARM`` / ``RT_SANDBOX_SETUP_SWARM`` deleted — they
    were back-compat shells solely for v2's swarm-id refs.
"""
from __future__ import annotations

from .defaults_redteam_exploit import (
    SCAN_VULNS_SWARM, PROVE_VULNS_SWARM,
)
from .defaults_eval_tail import RT_EVAL_TAIL_SWARM

REDTEAM_PIPELINE_GRAPH: dict = {
    "id": "redteam-pipeline",
    "kind": "graph",
    "name": "Red Team Pipeline",
    "description": (
        "recon → sandbox → scan → prove → eval. Composes 2 "
        "workflows (recon-app, sandbox-setup) + 3 swarms."
    ),
    "entry_point": "recon",
    "nodes": [
        {"id": "recon", "type": "graph",
         "graph_id": "recon-app",
         "description": "Veritas recon + CDK analysis (workflow)"},
        {"id": "sandbox", "type": "graph",
         "graph_id": "sandbox-setup",
         "description": (
             "Direct resource creation in LocalStack (workflow)"
         )},
        {"id": "scan", "type": "swarm",
         "swarm_id": "rt-scan-vulns",
         "description": "Scan graph for vuln classes"},
        {"id": "prove", "type": "swarm",
         "swarm_id": "rt-prove-vulns",
         "description": "Exploit in sandbox, prove findings"},
        {"id": "eval", "type": "swarm",
         "swarm_id": "rt-eval-tail",
         "description": "Score pipeline + record metrics"},
    ],
    "edges": [
        {"source": "recon", "target": "sandbox"},
        {"source": "sandbox", "target": "scan"},
        {"source": "scan", "target": "prove"},
        {"source": "prove", "target": "eval"},
    ],
    "max_cycles": 1,
    # bd-nrt5 pre-cond (x): outer node_timeout must be >=
    # max(child.execution_timeout) + 600s buffer (asyncio.to_thread
    # does not propagate cancellation). recon-app and sandbox-setup
    # both have execution_timeout=3600 → 3600 + 900 = 4500.
    "execution_timeout": 10800.0,  # 3h whole pipeline
    "node_timeout": 4500.0,
    "required_bricks": [
        "graph", "veritas", "sandbox", "memory",
        "evals", "metrics", "kb",
    ],
    "context_vars": ["run_id", "target_app", "vuln_class"],
}

REDTEAM_PIPELINE_GRAPHS: list[dict] = [REDTEAM_PIPELINE_GRAPH]

# Composes default registrations from the migrated workflows
# (recon-app + sandbox-setup are exported by their own modules into
# defaults.py via REDTEAM_PIPELINE_GRAPHS via the recon/sandbox
# imports there) plus the 3 standalone leaf swarms. No dedup loop —
# children are already canonical and singular.
REDTEAM_PIPELINE_SWARMS: list[dict] = [
    SCAN_VULNS_SWARM, PROVE_VULNS_SWARM, RT_EVAL_TAIL_SWARM,
]
