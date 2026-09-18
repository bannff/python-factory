"""Recon — hybrid (graph-of-swarms) variant.

2 parallel 2-agent swarms (discoverer + verifier) → summary agent.

Context variables: {{run_id}}, {{target_app}}

Workflow detail (Veritas search_resources, CDK reads, workspace
write rules) lives in skills/veritas-recon/SKILL.md,
skills/cdk-analysis/SKILL.md, skills/compx-platform/SKILL.md —
loaded via the AgentSkills plugin. See bd python-factory-2xbi.
"""
from __future__ import annotations

from .models import HAIKU, SONNET, NOVA2_LITE, GPT_OSS

_DISCOVERER_PROMPT = (
    "You are a recon discoverer in a 2-agent team.\n"
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Agent ID: {{agent_id}}\n\n"
    "Use these skills (call the skills tool once for each):\n"
    "1. veritas-recon — for the Veritas discovery workflow\n"
    "2. cdk-analysis — for CDK code reading\n"
    "3. compx-platform — for platform tools\n\n"
    "Detect Amazon-internal deps (AAA/Odin/CloudAuth/Coral/Turtle) "
    "in code reads.\n"
    "When done, hand off via swarm/graph protocol."
)

_VERIFIER_PROMPT = (
    "You are a recon verifier in a 2-agent team.\n"
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Agent ID: {{agent_id}}\n\n"
    "Use these skills (call the skills tool once for each):\n"
    "1. veritas-recon — for the Veritas discovery workflow\n"
    "2. compx-platform — for platform tools\n\n"
    "When done, store learnings."
)

_SUMMARY_PROMPT = (
    "You are the recon summary agent.\n"
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Agent ID: {{agent_id}}\n\n"
    "Use the veritas-recon skill. Activate it via the skills tool, "
    "then follow its phases.\n"
    "Cross-reference resources discovered by both teams; "
    "graph_add_entity type=ReconSummary with counts."
)

# --- Team swarms ---

RECON_HYBRID_TEAM_A: dict = {
    "id": "rt-recon-hybrid-team-a",
    "name": "Recon Hybrid Team A (Haiku + Nova2 Lite)",
    "description": "Haiku discoverer + Nova2 Lite verifier.",
    "entry_point": "discoverer-a",
    "max_handoffs": 4, "max_iterations": 15,
    "agents": [
        # bd:python-factory-2tgo1 — discoverer prompt names 3 skills,
        # verifier names 2 (no cdk-analysis).
        {"id": "discoverer-a", "model": HAIKU,
         "description": "Haiku recon discoverer.",
         "system_prompt": _DISCOVERER_PROMPT, "tools": [],
         "skills": ["veritas-recon", "cdk-analysis", "compx-platform"]},
        {"id": "verifier-a", "model": NOVA2_LITE,
         "description": "Nova2 Lite recon verifier.",
         "system_prompt": _VERIFIER_PROMPT, "tools": [],
         "skills": ["veritas-recon", "compx-platform"]},
    ],
}

RECON_HYBRID_TEAM_B: dict = {
    "id": "rt-recon-hybrid-team-b",
    "name": "Recon Hybrid Team B (GPT OSS + Sonnet)",
    "description": "GPT OSS discoverer + Sonnet verifier.",
    "entry_point": "discoverer-b",
    "max_handoffs": 4, "max_iterations": 15,
    "agents": [
        {"id": "discoverer-b", "model": GPT_OSS,
         "description": "GPT OSS recon discoverer.",
         "system_prompt": _DISCOVERER_PROMPT, "tools": [],
         "skills": ["veritas-recon", "cdk-analysis", "compx-platform"]},
        {"id": "verifier-b", "model": SONNET,
         "description": "Sonnet recon verifier.",
         "system_prompt": _VERIFIER_PROMPT, "tools": [],
         "skills": ["veritas-recon", "compx-platform"]},
    ],
}

RECON_HYBRID_SWARMS: list[dict] = [
    RECON_HYBRID_TEAM_A, RECON_HYBRID_TEAM_B,
]

RECON_HYBRID_GRAPH: dict = {
    "id": "rt-recon-hybrid",
    "name": "Recon App (Hybrid Graph-of-Swarms)",
    "description": (
        "2 parallel 2-agent swarms (discoverer+verifier) "
        "→ Sonnet summary agent."
    ),
    "required_bricks": ["graph", "security", "memory", "kb"],
    "context_vars": ["run_id", "target_app"],
    "entry_points": ["recon-team-a", "recon-team-b"],
    "nodes": [
        {"id": "recon-team-a", "type": "swarm",
         "swarm_id": "rt-recon-hybrid-team-a",
         "description": "Haiku discoverer + Nova2 Lite verifier"},
        {"id": "recon-team-b", "type": "swarm",
         "swarm_id": "rt-recon-hybrid-team-b",
         "description": "GPT OSS discoverer + Sonnet verifier"},
        {"id": "summary", "type": "agent", "model": SONNET,
         "description": "Merges recon from 2 teams.",
         "system_prompt": _SUMMARY_PROMPT,
         "skills": ["veritas-recon"],
         "tools": ["think"]},
    ],
    "edges": [
        {"source": "recon-team-a", "target": "summary"},
        {"source": "recon-team-b", "target": "summary"},
    ],
    "max_node_executions": 3,
    "execution_timeout": 1800,
    "node_timeout": 600,
}
