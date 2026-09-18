"""Recon app workflow — Veritas-powered AWS infra discovery.

Migrated from kind=graph (2-node graph delegating to swarms) to
kind=workflow (4-task DAG over workflow). Pattern
mirrors the SAST canary (bd python-factory-a4h7) but flattened —
workflow tasks cannot nest a Swarm, so the recon
swarm and eval-tail swarm are decomposed into sibling tasks.

Sequential pipeline:
  recon-lead → recon-verify → recon-summary → eval-scorer

Per-task scope (bd python-factory-s5ev):
- ``build_recon_tasks()`` is pure-deterministic — recon takes no
  per-call inputs (vuln_class doesn't apply). Other context vars
  (``{{run_id}}``, ``{{target_app}}``) stay as template markers
  resolved by ``WorkflowExecutor`` at workflow-create time.
- Tools use BARE names (sandbox_execute, search_resources, …) —
  ``_tool_predicate`` in strands_mcp_graph normalises dot→underscore
  on mount, and per-task filters in ``_create_task_agent`` key by
  ``tool_name`` which is the underscore form.

bd python-factory-nrt5: ``RT_RECON_SWARM`` and ``RECON_SWARMS`` were
removed — the meta-pipeline now composes recon-app as a nested
``type=graph`` ref instead of a ``swarm_id=rt-recon-v2`` ref, so the
back-compat swarm shell has no consumers.

Workflow detail (Veritas tools, CDK reads, workspace JSON layout)
lives in skills/veritas-recon/SKILL.md, skills/cdk-analysis/SKILL.md,
skills/compx-platform/SKILL.md — loaded via the AgentSkills plugin.
See bd python-factory-2xbi.
"""
from __future__ import annotations

from factory.agent.runtime.registry_contracts import WorkflowConfig

from .models import HAIKU, NOVA2_LITE, GPT_OSS
from .redteam_eval_addenda import (
    EVAL_TAIL_PREAMBLE,
    EVAL_SESSION_SCORING,
    EVAL_METRICS_RECORDING,
)

# --- Per-agent prompts (thin — workflow lives in SKILL.md) -----------

_LEAD_PROMPT = (
    "You are a security recon lead.\n"
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Agent ID: recon-lead\n\n"
    "Use these skills (call the skills tool once for each):\n"
    "1. veritas-recon — for the Veritas discovery workflow\n"
    "2. cdk-analysis — for CDK code reading\n"
    "3. compx-platform — for platform tools\n\n"
    "Detect Amazon-internal deps (AAA/Odin/CloudAuth/Coral/Turtle) "
    "in code reads.\n"
    "When done, summarise findings into the task result."
)

_VERIFY_PROMPT = (
    "You are a recon verifier.\n"
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Agent ID: recon-verify\n\n"
    "Use these skills (call the skills tool once for each):\n"
    "1. veritas-recon — for the Veritas discovery workflow\n"
    "2. compx-platform — for platform tools\n\n"
    "Cross-check recon-lead's entities, fill gaps, then summarise "
    "into the task result."
)

_SUMMARY_PROMPT = (
    "You are a recon summary agent.\n"
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Agent ID: recon-summary\n\n"
    "Use the veritas-recon skill. Activate it via the skills tool, "
    "then follow its phases.\n"
    "Use graph_count_entities_by_run(run_id='{{run_id}}') for "
    "per-label counts and graph_find_entities(entity_type=..., "
    "properties={'run_id': '{{run_id}}'}) for per-type lookups; "
    "then graph_add_entity type=ReconSummary with counts."
)

# Eval-scorer prompt embeds the shared eval-tail addenda. recon-app
# runs standalone, so {{metric_prefix}}/{{eval_evaluators}}/etc are
# left as template markers — the executor's inject_variables resolves
# them from the runtime context (or leaves them as-is for standalone
# smoke runs).
_EVAL_PROMPT = (
    EVAL_TAIL_PREAMBLE + EVAL_SESSION_SCORING + EVAL_METRICS_RECORDING
)

# --- Per-role tool sets (BARE underscore names — see module docstring)

_LEAD_TOOLS = [
    "search_resources", "get_app_topology", "get_app_security_profile",
    "get_resource_permissions", "get_data_flows",
    "get_deployment_chain",
    "graph_add_entity", "graph_add_relationship",
    "graph_find_entities", "graph_get_target_app",
    "sandbox_execute", "file_read", "http_request", "think",
]
_VERIFY_TOOLS = [
    "search_resources", "graph_find_entities",
    "graph_add_entity", "think",
]
_SUMMARY_TOOLS = [
    "graph_find_entities", "graph_count_entities_by_run",
    "graph_add_entity", "think",
]
_EVAL_TOOLS = [
    "graph_count_entities_by_run", "graph_get_workflow_summary",
    "graph_add_entity",
    "evals_evaluate_multi", "metrics_record", "memory_store", "think",
]


def _task(
    task_id: str, prompt: str, tools: list[str], model: str,
    deps: list[str], prio: int, skills: list[str] | None = None,
) -> dict:
    """Build one Workflow task dict. Pure — no rendering.

    bd:python-factory-2tgo1 — ``skills`` is the per-task AgentSkills
    attach list. Empty for eval-scorer (no skill ref in prompt).
    """
    return {
        "task_id": task_id,
        "description": prompt,
        "system_prompt": prompt,
        "tools": list(tools),
        "skills": list(skills or []),
        "model_provider": "bedrock",
        "model_settings": {"model_id": model},
        "dependencies": list(deps),
        "priority": prio,
        "timeout": 1800,
    }


def build_recon_tasks() -> list[dict]:
    """Render the 4-task recon DAG.

    Pure-constant — recon takes no per-call inputs. ``{{run_id}}``
    and ``{{target_app}}`` stay as template markers; the executor
    resolves them with the full runtime context at create time.
    Hypothesis-property tested in ``test_factories_recon.py``.
    """
    # bd:python-factory-2tgo1 — per-task skills extracted from prompts.
    # Lead/verify reference 3 skills each; summary references only
    # veritas-recon. eval-scorer has no skill ref.
    return [
        _task("recon-lead", _LEAD_PROMPT, _LEAD_TOOLS, HAIKU, [], 5,
              skills=["veritas-recon", "cdk-analysis", "compx-platform"]),
        _task("recon-verify", _VERIFY_PROMPT, _VERIFY_TOOLS,
              NOVA2_LITE, ["recon-lead"], 4,
              skills=["veritas-recon", "compx-platform"]),
        _task("recon-summary", _SUMMARY_PROMPT, _SUMMARY_TOOLS,
              GPT_OSS, ["recon-verify"], 3,
              skills=["veritas-recon"]),
        _task("eval-scorer", _EVAL_PROMPT, _EVAL_TOOLS,
              NOVA2_LITE, ["recon-summary"], 2, skills=[]),
    ]


# --- Workflow registration --------------------------------------------

RECON_REGISTRATION = WorkflowConfig(
    id="recon-app",
    kind="workflow",
    factory="recon",
    name="Recon App (Workflow)",
    description=(
        "Veritas-powered AWS infra discovery for {{target_app}}. "
        "recon-lead → recon-verify → recon-summary → eval-scorer."
    ),
    required_bricks=[
        "graph", "veritas", "memory", "sandbox", "evals", "metrics",
    ],
    context_vars=["run_id", "target_app"],
    tool_allowlist=None,  # bd-42dz: None means use all required_bricks tools
    execution_timeout=3600.0,
    node_timeout=1800.0,
)

# Back-compat exports — defaults.py imports RECON_GRAPHS. RECON_GRAPHS
# is a 1-element list of WorkflowConfig (was a list[dict] pre-s5ev).
# bd python-factory-nrt5: RECON_SWARMS removed; the v2 back-compat
# RT_RECON_SWARM had no remaining consumer once redteam-pipeline-v2
# became a hybrid graph composing recon-app via type=graph ref.
RECON_GRAPHS: list = [RECON_REGISTRATION]
