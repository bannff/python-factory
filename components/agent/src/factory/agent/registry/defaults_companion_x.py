"""Default Companion-X chat agent registration (bd:python-factory-hadbi.1).

Registers ``companion-x-default`` — the agent the chat sidebar resolves
when ``COMPANION_X_CHAT_AGENT_ID`` is unset (or set to the default).
The ``system_prompt`` is the verbatim original ``COMPANION_X_PROMPT``
from ``runtime/companion/prompt.py`` so chat behavior is byte-identical
to pre-pivot. Phase 2 substrate prep — no new domain agents (wine,
workout) yet; future ones add their own ``defaults_<agent>.py``.

Design verdicts:
- meta-architect ``9a4aba3c`` — register companion-x-default as another
  ``AgentConfig``; fold the AgentSkills SDK-First fix into Phase 2 by
  adding optional ``skills:list[str]`` to the contract.
- strands-expert ``a4843cb1`` — wire ``compx-platform`` (brick API
  catalog) and ``companion-x-behavior`` (response style + UI rules) as
  skills (bd:python-factory-4hahv). Insertion order: compx-platform
  first per SDK _resolve_skills iteration guarantee.
- strands-expert ``9b6d46cd`` — chat lookup is
  ``os.environ.get('COMPANION_X_CHAT_AGENT_ID', 'companion-x-default')``
  with LOUD-FAIL on a missing env-named id (no silent fallback).
- Epic 6 (Agentic Dataset Skills) — add ``can-analyst`` to the chat
  default's skills list so the chat sidebar can answer MF4 ingest /
  DBC matching / constraint schema questions out of the box. Inserted
  AFTER ``dataset-generation`` because can-analyst builds on top of
  the dataset workflow primitives (dataset_submit_generation,
  dataset_get_job, dataset_resolve_artifact).

Model: no persona-level override — this agent inherits the process
default model (``COMPANION_X_CHAT_MODEL``, itself typically
``openrouter``/``OPENROUTER_MODEL`` from ``.env``) via
``LangChainModelCache.effective_id``. A prior revision hardcoded the
``SONNET`` Bedrock constant here, which silently overrode the working
OpenRouter default for every session on this persona regardless of
``.env`` — removed so this persona can never again diverge from the
one real config variable.
"""
from __future__ import annotations

from ..runtime.companion.prompt import COMPANION_X_PROMPT
from ..runtime.registry_contracts import AgentConfig

COMPANION_X_DEFAULT_AGENT: AgentConfig = AgentConfig(
    id="companion-x-default",
    name="Companion X (default)",
    model="openrouter",
    system_prompt=COMPANION_X_PROMPT,
    tools=[],
    skills=[
        "compx-platform", "companion-x-behavior",
        "dataset-generation", "can-analyst",
    ],
    description=(
        "Default Companion-X chat agent — security-flavored persona, "
        "retains today's behavior; also handles CAN analyst questions "
        "via the can-analyst skill."
    ),
)


__all__ = ["COMPANION_X_DEFAULT_AGENT"]
