# Kiro E2E Security Pipeline — Handover Prompt

Paste everything below into a new Kiro conversation with any model.

---

## MISSION

Run the full Kiro E2E security pipeline against sandbox targets and produce experiment reports. The pipeline is: **Sandbox Setup → Polymorphic Recon → DAST Testing → RL Scoring → Experiment Report**. Each run produces a JSON report in `projects/companion_x/challenges/experiments/{run_id}.json` with 30+ metrics and per-finding detail.

## WHAT EXISTS (do not rebuild)

### Skills (in `.kiro/skills/`)
- `kiro-sandbox-setup` — Provisions Docker sandbox via profile, health checks, stores SandboxEnv in graph
- `kiro-recon-lead` — Polymorphic recon: detects target type (API/web/SPA), fingerprints tech stack, discovers endpoints, maps auth, writes TargetApp + EndpointInventory + AuthProfile to graph
- `kiro-recon-verifier` — Validates recon completeness, fills gaps, checks GT coverage
- `kiro-dast-tester` — Tests running app via HTTP, stores ProvenExploit entities in graph with full evidence
- `kiro-sast-scanner`, `kiro-sast-consolidator`, `kiro-sast-validator` — SAST pipeline (skip for non-source targets)

### Hook
- `.kiro/hooks/kiro-workflow-pipeline.kiro.hook` — Fires after every `invokeSubAgent`. If it was the FINAL security workflow phase (DAST), triggers post-pipeline: RL scoring + experiment report.

### Sandbox Profiles (one container at a time, auto-terminates previous)
| Profile | Port | Health Path | GT Count |
|---------|------|-------------|----------|
| idor_warehouse | 5050 | /health | 3 |
| webgoat | 8080 | /WebGoat | 3 |
| dvwa | 8080 | /login.php | 10 |
| vampi | 5050 | / | 6 |
| juice_shop | 3000 | / | 41 |

### GT Files
Each target has ground truth at `projects/companion_x/challenges/{target}/gt_entries.json`. The RL scorer matches ProvenExploit entities to GT by CWE + HTTP method + endpoint path.

### Companion-X Power
All brick tools are accessed via the `companion-x` Kiro power using `call_brick_tool`. Key bricks: sandbox, graph, memory, security, games, metrics.

## HOW TO RUN THE FULL E2E PIPELINE

### Step 1: Sandbox Setup
Activate the `kiro-sandbox-setup` skill, then dispatch a sub-agent:

```
invokeSubAgent(name="security-engineer", prompt="
  You are the Sandbox Setup agent for run {run_id} against {target_app}.
  ACTIVATE the kiro-sandbox-setup skill.
  Inputs: target_app={target_app}, run_id={run_id}, profile={profile}
  Use companion-x power. Run HTTP from host (containers may lack curl).
")
```

Or do it manually:
1. `call_brick_tool(brick="sandbox", tool="sandbox.provision", args='{"profile": "{profile}"}')`
2. Health check from host: `curl -sf http://localhost:{port}{health_path}`
3. For VAmPI: `curl -sf http://localhost:5050/createdb` to init DB
4. For DVWA: login to set security=low cookie first

### Step 2: Polymorphic Recon
Dispatch recon lead sub-agent:

```
invokeSubAgent(name="security-engineer", prompt="
  You are the Recon Lead for run {run_id} against {target_app}.
  ACTIVATE the kiro-recon-lead skill.
  Inputs: target_app={target_app}, run_id={run_id}, target_url=http://localhost:{port}, sandbox_env_id=factory-sandbox
  Run ALL HTTP from host via localhost:{port}.
  Write TargetApp (MERGE), EndpointInventory, AuthProfile to graph.
  This is NOT the final phase.
")
```

### Step 3: DAST Testing (FINAL PHASE)
Dispatch DAST tester sub-agent:

```
invokeSubAgent(name="security-engineer", prompt="
  You are the DAST tester for run {run_id} against {target_app}.
  ACTIVATE the kiro-dast-tester skill.
  Inputs: target_app={target_app}, target_url=http://localhost:{port}, run_id={run_id}, sandbox_env_id=factory-sandbox, vuln_class=multi
  Load recon data from graph: EndpointInventory and AuthProfile for {run_id}.
  Run ALL HTTP from host. Every ProvenExploit MUST have populated parameter field.
  Store each exploit in graph. Return _metrics block.
")
```

### Step 4: Post-Pipeline (triggered by hook, or do manually)
The hook should fire automatically after the DAST sub-agent completes. If it doesn't, do manually:

1. RL Scoring:
```
call_brick_tool(brick="games", tool="games_process_workflow_rl",
  args='{"graph_id":"kiro-multi","run_id":"{run_id}","vuln_class":"multi","workflow_type":"dast","target_app":"{target_app}"}')
```

2. Write Experiment Report:
```
call_brick_tool(brick="games", tool="games_write_experiment_report",
  args='{"run_id":"{run_id}","workflow_type":"kiro","target_app":"{target_app}","vuln_class":"multi","framework":"{framework}","agent_count":1,"duration_seconds":120,"extra_metrics":"{...}"}')
```

The `extra_metrics` is a JSON STRING (not dict) containing:
- `pipeline_execution_summary`: phases array
- `tooling_observations`: list of notes
- `dynamic_verification`: {verified_finding, verification_failed, not_tested, sast_predictions_confirmed: 0, sast_predictions_total: 0, sast_correlation_rate: 0.0}
- `tool_calls`: {total, per_tool, errors}
- `per_phase_seconds`, `time_to_first_finding_seconds`, `params`, `tokens_source: "self_reported"`, `with_attack_chain`, `avg_confidence_score`

The brick handles everything else (findings detail, categories, scoring) from graph automatically.

## RUN ID CONVENTION

Use: `kiro-pipeline-{target}-{sequence}` or `kiro-{model}-{target}-{sequence}`

Examples: `kiro-pipeline-vampi-003`, `kiro-deepseek-vampi-001`, `kiro-qwen-dvwa-001`

## KEY RULES

1. **One sandbox at a time** — `sandbox.provision` auto-terminates the previous container
2. **HTTP from host** — Most containers lack curl. Run all curl from the host via `localhost:{port}`
3. **Flat graph properties** — Neo4j doesn't support nested objects. All ProvenExploit properties must be flat strings/numbers/booleans
4. **Parameter field required** — Every ProvenExploit MUST have `parameter` populated (e.g. "username (path, user_controlled)")
5. **Don't calculate scores** — Trust `games_process_workflow_rl` output. Don't compute your own P/R/F1
6. **Don't assemble findings** — `games_write_experiment_report` extracts per-finding detail from graph automatically
7. **extra_metrics is a JSON string** — Pass it as an escaped JSON string, not a dict

## COMPLETED RUNS (for reference)

| Run ID | Target | Model | F1 | TP | FP | FN | Report |
|--------|--------|-------|----|----|----|----|--------|
| kiro-pipeline-dvwa-003 | dvwa | claude-sonnet-4 | 1.0 | 10 | 0 | 0 | Gold standard |
| kiro-pipeline-vampi-002 | vampi | claude-sonnet-4 | 1.0 | 6 | 0 | 0 | With bug fixes |
| kiro-pipeline-juiceshop-001 | juice_shop | claude-sonnet-4 | 0.0* | 16 | 16 | 2 | *GT format mismatch (fixed) |

*Juice Shop F1=0.0 because GT entries lacked HTTP method+path — now fixed in gt_entries.json.

## QUICK START (copy-paste ready)

To run a target E2E with the current model:

1. Check what sandbox is running: `docker ps --filter "name=factory-sandbox"`
2. Provision the target you want (auto-terminates previous): use companion-x `sandbox.provision(profile="{profile}")`
3. Wait 10-15s, health check from host: `curl -sf http://localhost:{port}{health_path}`
4. Target-specific init (VAmPI: `curl -sf http://localhost:5050/createdb`)
5. Dispatch recon sub-agent (activate kiro-recon-lead skill)
6. Dispatch DAST sub-agent (activate kiro-dast-tester skill) — hook handles the rest

## TARGET-SPECIFIC NOTES

**VAmPI** (easiest, recommended for model comparison):
- Flask REST API, JWT auth with 60s expiry, refresh tokens between tests
- `/createdb` must be called to init test data
- Email IDOR (GT-3) is a confused deputy — changes caller's email not target's
- Container has no curl

**DVWA** (PHP, session-based):
- Needs login + security=low cookie for all requests
- CSRF user_token required for POST forms
- reCAPTCHA API key missing prevents full captcha exploit

**Juice Shop** (hardest, 41 GT):
- Angular SPA + Express API, JWT auth
- SQLi on /rest/products/search and /rest/user/login
- Many GT entries require browser interaction or specific knowledge
- 32 GT entries have HTTP method+path, 9 are challenge-only
