"""Red team pipeline swarms — 5 reusable workflows.

recon → pull-artifacts → setup-sandbox → scan-vulns → prove-vulns

Each swarm writes work products to the GRAPH scoped by run_id + app.
Memory is for learnings only. GPT OSS always last (no handoff needed).

Context variables (injected by executor):
  {{run_id}}     — unique pipeline run identifier
  {{target_app}} — Veritas app name being assessed

Workflow detail (Veritas tools, graph storage rules, sandbox CLI,
swarm handoff protocol) lives in the AgentSkills:
  - compx-platform — platform tools
  - veritas-recon — recon workflow
  - sandbox-ops — sandbox + AWS CLI
  - swarm-collaboration — handoff protocol
See bd python-factory-2xbi.
"""
from __future__ import annotations

from .models import HAIKU, SONNET, NOVA2_LITE, SCOUT, GPT_OSS

# Common context block — every agent prompt starts with this.
_CTX = (
    "Run ID: {{run_id}} | App: {{target_app}}\n"
    "Use these skills (call the skills tool once for each):\n"
    "1. compx-platform — for platform context\n"
    "2. veritas-recon — for the recon workflow\n"
    "3. swarm-collaboration — for handoff and storage protocol\n\n"
    "All graph entities MUST include run_id='{{run_id}}' and "
    "app='{{target_app}}'.\n"
)

# bd:python-factory-2tgo1 — _CTX names 3 skills; agents that
# additionally use the sandbox-ops skill (deployer, deploy-verify)
# extend with that.
_CTX_SKILLS = ["compx-platform", "veritas-recon", "swarm-collaboration"]
_CTX_SKILLS_SANDBOX = _CTX_SKILLS + ["sandbox-ops"]

# Node 1: Recon — query Veritas, graph-plot the app
RECON_SWARM: dict = {
    "id": "rt-recon",
    "name": "Recon App",
    "description": "Query Veritas for full app intel and write "
    "app model to graph.",
    "entry_point": "recon-lead",
    "max_handoffs": 8, "max_iterations": 15,
    "agents": [
        {"id": "recon-lead", "model": HAIKU,
         "description": "Queries Veritas, writes entities to graph.",
         "system_prompt": (
             "You are the recon-lead — first agent in the recon "
             "swarm.\n" + _CTX +
             "Run get_app_topology + get_app_security_profile + "
             "query for CodePackage nodes. Write App, each Account, "
             "each CodePackage to graph. Hand off to recon-verify."
         ), "tools": [], "skills": list(_CTX_SKILLS)},
        {"id": "recon-verify", "model": NOVA2_LITE,
         "description": "Cross-checks recon, fills gaps in graph.",
         "system_prompt": (
             "You are the recon-verify agent — second in the recon "
             "swarm.\n" + _CTX +
             "Query the graph for entities written by recon-lead. "
             "Run independent Veritas queries to fill gaps. Add any "
             "missing entities. Hand off to recon-summary."
         ), "tools": [], "skills": list(_CTX_SKILLS)},
        {"id": "recon-summary", "model": GPT_OSS,
         "description": "Consolidates recon graph into summary.",
         "system_prompt": (
             "You are the recon-summary agent — last in the recon "
             "swarm.\n" + _CTX +
             "Query the graph for all entities written this run. "
             "Add a ReconSummary entity with counts. Do NOT hand "
             "off — you are last."
         ), "tools": [], "skills": list(_CTX_SKILLS)},
    ],
}

# Node 2: Pull Artifacts — read CDK code, add to graph
PULL_ARTIFACTS_SWARM: dict = {
    "id": "rt-pull-artifacts",
    "name": "Pull Artifacts",
    "description": "Read CDK code and infra definitions, add "
    "findings to graph.",
    "entry_point": "artifact-puller",
    "max_handoffs": 8, "max_iterations": 15,
    "agents": [
        {"id": "artifact-puller", "model": HAIKU,
         "description": "Reads code package files.",
         "system_prompt": (
             "You are the artifact-puller — first agent in the "
             "pull-artifacts swarm.\n" + _CTX +
             "Query graph for CodePackage entities, list files via "
             "builder, read key files, add CodeFile entities. Hand "
             "off to artifact-reviewer."
         ), "tools": [], "skills": list(_CTX_SKILLS)},
        {"id": "artifact-reviewer", "model": SONNET,
         "description": "Reviews code for secrets and misconfigs.",
         "system_prompt": (
             "You are the artifact-reviewer — second in the "
             "pull-artifacts swarm.\n" + _CTX +
             "Query graph for CodeFile entities. Look for hardcoded "
             "secrets, ARNs, keys, overpermissive IAM, misconfigs. "
             "Add Secret or Misconfig entities, link to CodeFile. "
             "Hand off to artifact-summary."
         ), "tools": [], "skills": list(_CTX_SKILLS)},
        {"id": "artifact-summary", "model": GPT_OSS,
         "description": "Summarizes artifacts in graph.",
         "system_prompt": (
             "You are the artifact-summary agent — last in the "
             "pull-artifacts swarm.\n" + _CTX +
             "Query graph for Secret + Misconfig entities. Add an "
             "ArtifactSummary entity. Do NOT hand off — you are last."
         ), "tools": [], "skills": list(_CTX_SKILLS)},
    ],
}

# Node 3: Setup Sandbox — deploy infra to LocalStack
SETUP_SANDBOX_SWARM: dict = {
    "id": "rt-setup-sandbox",
    "name": "Setup Sandbox",
    "description": "Build CFN from graph model, deploy to "
    "LocalStack sandbox.",
    "entry_point": "cfn-builder",
    "max_handoffs": 8, "max_iterations": 15,
    "agents": [
        {"id": "cfn-builder", "model": SONNET,
         "description": "Builds CFN template from graph model.",
         "system_prompt": (
             "You are the cfn-builder — first agent in the "
             "setup-sandbox swarm.\n" + _CTX +
             "Query graph for Account + resources, build a minimal "
             "CFN template (IAM roles matching discovered policies, "
             "S3 buckets, DynamoDB tables). Add a CFNTemplate entity "
             "with the body in properties. Hand off to deployer."
         ), "tools": [], "skills": list(_CTX_SKILLS)},
        {"id": "deployer", "model": HAIKU,
         "description": "Deploys CFN to LocalStack.",
         "system_prompt": (
             "You are the deployer — second in the setup-sandbox "
             "swarm.\n" + _CTX +
             "Use the sandbox-ops skill (call skills tool) for "
             "sandbox CLI patterns. Query graph for CFNTemplate, "
             "list sandbox envs, deploy via sandbox_deploy_cfn. Add "
             "a SandboxEnv entity. Hand off to deploy-verify."
         ), "tools": [], "skills": list(_CTX_SKILLS_SANDBOX)},
        {"id": "deploy-verify", "model": SCOUT,
         "description": "Validates sandbox deployment.",
         "system_prompt": (
             "You are the deploy-verify agent — last in the "
             "setup-sandbox swarm.\n" + _CTX +
             "Use the sandbox-ops skill (call skills tool) for "
             "AWS CLI patterns. Query graph for SandboxEnv, run "
             "sandbox_execute to list roles/buckets/tables, add "
             "a DeployValidation entity. Do NOT hand off — last."
         ), "tools": [], "skills": list(_CTX_SKILLS_SANDBOX)},
    ],
}


# Import exploit-phase swarms from separate file
from .defaults_redteam_exploit import (  # noqa: E402
    SCAN_VULNS_SWARM, PROVE_VULNS_SWARM,
)

RT_FOCUSED_SWARMS: list[dict] = [
    RECON_SWARM, PULL_ARTIFACTS_SWARM, SETUP_SANDBOX_SWARM,
    SCAN_VULNS_SWARM, PROVE_VULNS_SWARM,
]
