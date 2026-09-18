"""Recon — graph-only variant (parallel independent agents).

3 parallel agent nodes (Haiku, Nova2 Lite, GPT OSS) each run
Veritas recon independently → summary agent (Sonnet) merges.

Context variables: {{run_id}}, {{target_app}}

Workflow detail (Veritas search_resources, CDK reads, workspace
write rules) lives in skills/veritas-recon/SKILL.md,
skills/cdk-analysis/SKILL.md, skills/compx-platform/SKILL.md —
loaded via the AgentSkills plugin. See bd python-factory-2xbi.
"""
from __future__ import annotations

from .models import HAIKU, SONNET, NOVA2_LITE, GPT_OSS

_RECON_PROMPT = (
    "You are a security recon agent.\n"
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

_SUMMARY_PROMPT = (
    "You are the recon summary agent.\n"
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Agent ID: summary\n\n"
    "Use the veritas-recon skill. Activate it via the skills tool, "
    "then follow its phases.\n"
    "Cross-reference resources discovered by 2/3+ agents → "
    "confirmed; graph_add_entity type=ReconSummary with counts."
)

RECON_GRAPH_ONLY: dict = {
    "id": "rt-recon-graph",
    "name": "Recon App (Parallel Agents Graph)",
    "description": (
        "3 models run Veritas recon in parallel "
        "(Haiku, Nova2 Lite, GPT OSS) → Sonnet summarizer."
    ),
    "required_bricks": ["graph", "security", "memory", "kb"],
    "context_vars": ["run_id", "target_app"],
    "entry_points": ["haiku-recon", "nova2-recon", "gptoss-recon"],
    "nodes": [
        # bd:python-factory-2tgo1 — per-prompt skill mapping. Recon
        # nodes ref 3 skills; summary refs only veritas-recon.
        {"id": "haiku-recon", "type": "agent", "model": HAIKU,
         "description": "Haiku recon agent.",
         "system_prompt": _RECON_PROMPT,
         "skills": ["veritas-recon", "cdk-analysis", "compx-platform"],
         "tools": ["think"],
         "context": {"agent_id": "haiku-recon"}},
        {"id": "nova2-recon", "type": "agent", "model": NOVA2_LITE,
         "description": "Nova2 Lite recon agent.",
         "system_prompt": _RECON_PROMPT,
         "skills": ["veritas-recon", "cdk-analysis", "compx-platform"],
         "tools": ["think"],
         "context": {"agent_id": "nova2-recon"}},
        {"id": "gptoss-recon", "type": "agent", "model": GPT_OSS,
         "description": "GPT OSS recon agent.",
         "system_prompt": _RECON_PROMPT,
         "skills": ["veritas-recon", "cdk-analysis", "compx-platform"],
         "tools": ["think"],
         "context": {"agent_id": "gptoss-recon"}},
        {"id": "summary", "type": "agent", "model": SONNET,
         "description": "Merges recon from 3 agents.",
         "system_prompt": _SUMMARY_PROMPT,
         "skills": ["veritas-recon"],
         "tools": ["think"]},
    ],
    "edges": [
        {"source": "haiku-recon", "target": "summary"},
        {"source": "nova2-recon", "target": "summary"},
        {"source": "gptoss-recon", "target": "summary"},
    ],
    "max_node_executions": 3,
    "execution_timeout": 1800,
    "node_timeout": 600,
}
