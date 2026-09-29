# Companion-X Onboarding — Orientation Map (2026-09-29)

Onboarding artifact per `repo-onboarding` skill. Observations cited to file/line; inferences marked.

## Purpose

Companion-X is the **control plane** of the Python Software Factory: a domain-agnostic
expert-augmentation engine that dynamically assembles bounded, objective-specific agent
teams through the `agent` brick's surfaces and invokes capability bricks through MCP.
It is **not** another agent runtime (normative: `.agents/steering/factory-protocol.md`,
"AGENTIC CONTROL PLANE"). Security is domain pack #1 — a *data pack* (skills/SOP/
taxonomy/challenge ground truth), not engine code (`.agents/steering/platform-doctrine.md`).
The single interaction surface is Companion-X Web (Next.js cockpit).

The self-improving loop (North Star #3): agents act → games emit reward signals →
evals independently accept/promote evidence-bound trajectories → distillation (LoRA,
currently the keystone gap — trajectory landing-zone format unbuilt) → better model.

## Build / test / lint

| Action | Command |
|---|---|
| Sync env (workspace root) | `uv sync --frozen` (CI-exact) |
| Sync with ML extras (Darwin arm64) | `uvx --from uv==0.12.0 uv sync --group ml --config-settings-package lightgbm:cmake.define.USE_OPENMP=OFF` (README "Darwin arm64 OpenMP Runtime Contract" — plain `uv sync --group ml` builds LightGBM with OpenMP and fails here) |
| Add CAN test deps | append `--group can-test` |
| Run project tests | `uv run pytest projects/companion_x/test -q` **with CI env vars** (below) |
| Run one test | `uv run pytest projects/companion_x/test/test_main_composition_root.py -q` |
| Strict full suite (manual CI) | `uv run pytest` |
| CI (authority): PR lane | `.github/workflows/ci.yml` — `core-tests` job: `uv lock --check && uv sync --frozen` + `config/core-test-requirements.txt` + guardian ratchet check + strict suites (`components/test`, `foreman`, `agent`, `blockchain`, `scripts/test`) + changed-brick tests |
| CI: CAN lane | `can-tests` job: `uv sync --frozen --group can-test`, `uv run pytest components/dataset/test` |
| CI does NOT run | `projects/companion_x/test` or `components/machine_learning/test` (explicitly ignored in core-tests collection) — macOS-arm64 acceptance tests are local-only |
| Frontend tests | `cd frontends/next-dashboard && npm test` (vitest + playwright configured) |
| Local dev stack | `./scripts/companion-x-ui.sh` (launcher exists; generates ephemeral `MCP_LOCAL_AUTH_TOKEN`, starts API :8000 + Next :3000) |
| Container stack | `make dev` / `make up` / `make sandbox-up` / `make deploy-challenges` / `make test` / `make build` (projects/companion_x/Makefile) |

**Test env vars required locally** (from CI `core-tests` job env + `projects/companion_x/.env.example`):
`MCP_LOCAL_AUTH=true MCP_LOCAL_AUTH_TOKEN=<any> MCP_PERMISSIONS_CONFIG_DIR=config/mcp_permissions WORKFLOW_CONFIG_DIR=projects/companion_x/config FACTORY_AGENT_CONFIG_DIR=.storage/agent-config TELEMETRY_REQUIRED=0`

**CRITICAL env gotcha:** root `.venv` and `projects/companion_x` env are separate.
Plain `uv run` uses the ROOT env. `uv run --project projects/companion_x` tries to
resolve the full companion_x dependency set (torch, mlflow, lightgbm build — fails
on the OpenMP contract). After `uv sync --group ml --group can-test` at root, the
root env satisfies companion_x tests; run them with plain `uv run` + the env vars above.

## Top-level structure

| Path | Responsibility |
|---|---|
| `components/` | Polylith bricks (agent, workflow, dataset, games, evals, blockchain, memory, kb, graph, security, …). Each: `BRICK.yaml`, `runtime/` (logic), `mcp/` (tools), `interface.py` (public API) |
| `bases/` | Pure transport shells: `api` (FastAPI composition root), `mcp_server` (aggregator), `worker`, `blueprint` |
| `projects/companion_x/` | The deployable project: composition root `main.py`, brick wiring in `pyproject.toml [tool.polylith.bricks]` (~45 bricks), Dockerfiles, challenge packs |
| `projects/companion_x/skills/security/` | Security domain-pack SOP skills (recon-lead, SAST scanner/validator/consolidator, DAST tester, sandbox-setup) |
| `projects/companion_x/challenges/` | Security ground truth: VAMPI, DVWA, Juice Shop, IDOR warehouse, LocalStack IAM-privesc/SSRF-Lambda + `gt_entries.json` per challenge |
| `frontends/next-dashboard/` | Companion-X Web cockpit: Next.js 15 + CopilotKit v2 chat sidebar + AG-UI SSE |
| `frontends/shared-renderer/` | Universal A2UI React renderer package (component-map, renderers-*) |
| `.kiro/steering/`, `.agents/steering/` | Normative doctrine + implementation steering |
| `BRICKS_INDEX.yaml` | Generated brick catalog (2174 lines; `foreman` maintains it) |
| `config/mcp_permissions/` | MCP permission policies (CI points `MCP_PERMISSIONS_CONFIG_DIR` here) |

## Entry points

| Entry | What it starts |
|---|---|
| `projects/companion_x/main.py` | Unified MCP + REST + SSE + AG-UI on :8000 via `factory.api.main.create_app`; sets `EAGER_LOAD=0`, progressive discovery, `MCP_SERVER_NAME=companion-x` |
| `bases/api/src/factory/api/main.py` | Canonical composition root; `create_app()` installs MCP-UI redaction then mounts REST adapter + MCP aggregator + AG-UI streaming route |
| `frontends/next-dashboard` | Next.js cockpit on :3000; MCP BFF route handlers proxy with server-only bearer token |
| `RUN_MODE=api/mcp/worker` | Docker image modes: unified server / standalone stdio MCP / SQS worker |

## Critical path (chat → tools)

1. Browser → CopilotKit v2 chat sidebar (`selfManagedAgents` local registration, bd:python-factory-sopw)
2. → Next BFF `/ag-ui/run` → AG-UI SSE stream → API `stream_chat` via `factory.agent.interface.get_chat_agent_stream` (CHAT_STREAMING-gated)
3. → `agent` brick LangGraph runtime (`components/agent/.../adapters/langchain_runtime.py`, `langgraph_runtime.py`) — LangChain 1.3.17 / LangGraph 1.2.11 / MCP v2 (`mcp[cli]==2.1.1`), **zero Strands** (runtime truth, 2026-09-11)
4. → platform tool invoker reaches MCP aggregator → capability bricks (curated tool set)
5. → persona selected via registry: `COMPANION_X_CHAT_AGENT_ID` (default `companion-x-default`, LOUD-FAIL on miss)
6. Checkpoints: `AsyncSqliteSaver` at `./.storage/agent-checkpoints.db`; sessions in `session` brick `./.storage/sessions.db`

Model factory: `components/agent/.../runtime/adapters/langchain_model.py` from
`llm_gateway.resolve_chat_profile()` — `openrouter/<vendor>/<model>` | `ollama/<model>` | bare Bedrock id. Secrets by env-var *name* only.

## Active areas (6-week churn)

Frontend lockfile security bumps dominate (`next-dashboard/package.json` ×4) — recent
commits are all `chore(deps)`/`fix(deps)` clearing next/vitest criticals. The only
source churn: `test_main_composition_root.py`, `test_local_launcher.py`. History was
**reset at import** (commit bf5c1b41 "Initial commit — Companion-X (history reset;
imported from python-factory-archive@7a361be7)") — churn older than the reset is
invisible; treat hotspots as provisional.

## Conventions observed

- Polylith: logic in `runtime/`, MCP in `mcp/`, public API in `interface.py`; no cross-brick internal imports — use `factory.<brick>.interface`
- <200 LOC/file enforced by `foreman_guardian_check` (blocking PR ratchet, file_size_mode='ratchet')
- MCP tools: `@deterministic` / `@operational` / `@authoring` (gated); brick-name prefixes
- Hypothesis property tests required for stateful bricks (`.agents/steering/hypothesis-testing.md`)
- Issue tracking: `bd` (Beads) only, no markdown TODOs. **Local DB currently empty (0 issues) and `bd ready` errors with `table not found: issues`** — a broken/needs-init local Beads store (`.beads/dolt-server-config.yaml` untracked)
- Zero `if domain == ...` — domain packs are data; trinary polymorphic params + registry-overlay merge is the blessed mechanism
- Push protocol: `git pull --rebase && bd sync && git push`

## Baseline test state (this machine, 2026-09-29)

`uv run pytest projects/companion_x/test` with full local env: **7 passed, 4 failed.**

1. `test_execution_engine_config.py` (both tests) — `WorkflowError: Missing settings.yaml in config_dir`.
   **Root cause:** `.gitignore:89` ignores `projects/*/config/`, so
   `projects/companion_x/config/settings.yaml` (the `WORKFLOW_CONFIG_DIR` target,
   projects/companion_x/main.py:24) is untracked/per-machine and absent here. The
   regression test correctly loads real project config and fails on the gap.
   Only `config/auth/settings.yaml` (a `backend: memory` stub) exists.
2. `test_lightgbm_api_restart.py`, `test_lnn_chronos_api_restart.py` — `MCPError(-32603)`
   from a spawned two-PID API restart flow. Likely same missing-config root cause
   (spawned API process reads `WORKFLOW_CONFIG_DIR` from `.env`, which doesn't exist
   here yet); not further diagnosed. Heavy acceptance path (datasets, model passports).

## Unknowns

- `bd` local store needs init/repair (`bd ready` → `Error 1146: table not found: issues`; `bd stats` shows 0 total). `bd sync` may restore from remote.
- Exact provisioning for `projects/companion_x/config/settings.yaml` (workflow engine registry: expected `langgraph` → `agent.execute_langgraph_attempt`/`cancel_langgraph_attempt` per the failing test assertions). Copying root `config/settings.yaml` is unverified — engine ids may differ.
- `MCPError` in the two restart tests: same root cause as #1 or independent — needs `.env` provisioning and one run to confirm.
- Whether `frontends/shared-renderer` is consumed by next-dashboard via workspace deps or published (build artifacts committed under `lib/`).

## First-session checklist

```bash
# 0. Beads
bd sync   # restore issue DB

# 1. Env (Darwin arm64)
uvx --from uv==0.12.0 uv sync --group ml --group can-test \
  --config-settings-package lightgbm:cmake.define.USE_OPENMP=OFF

# 2. Project env files
cp projects/companion_x/.env.example projects/companion_x/.env
cp frontends/next-dashboard/.env.local.example frontends/next-dashboard/.env.local
# + provision projects/companion_x/config/settings.yaml (see Unknowns)

# 3. Run
./scripts/companion-x-ui.sh          # API :8000 + dashboard :3000
uv run pytest projects/companion_x/test -q \  # with CI env vars
  # expect 11/11 once config gap closed
```
