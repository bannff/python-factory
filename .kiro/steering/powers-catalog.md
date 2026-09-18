# Powers Catalog — what you can drive & test with

> Auto-loaded steering. Every software-factory agent reads this. It's an **index**
> of the powers available to build, drive, and **test** Companion-X work. Deep
> signatures live in `.agents/steering/`.

## Driving the platform: `@companion-x` (MCP-first — the MCP IS the API)
Never import bricks or hit raw HTTP. Progressive discovery:
- `list_bricks` — loaded bricks (`tools_count: -1` = registered, not yet loaded).
- `get_brick_tools(brick_name)` — lists a brick's tools **and lazy-loads it**.
- `call_brick_tool(brick_name, tool_name, arguments)` — workhorse; `arguments` is a **JSON string**.
- `read_brick_resource(uri)` — e.g. `graph://schemas/taxonomy/security`.
- Convenience: `memory_store`, `memory_retrieve`, `foreman_guardian_check`, `health_check`.

### Bricks you'll use to test the RL loop
- **graph** — `graph_get_findings_for_run`, `graph_get_workflow_summary` (verify entities persisted — the rp44 gate).
- **evals** — `evals_persist_score`, `evals_sop_plan` (scoring).
- **learning** — `learning_compute_reward` (the reward-source seam).
- **games** — `games_process_workflow_rl` (RL cascade).
- **memory** — store/retrieve learnings; **always `user_id="kiro-agent"`**; tags = ANY-match.
- **sandbox** — challenge provisioning for workflow runs.

### Acceptance-probe pattern (prove agnostic)
Run a non-security workflow (`domain_class='probe-nonsec'`), confirm a signed
reward via a reward source, store+retrieve memory with an arbitrary tag, and
confirm **no** cwe/sast/dast branch was touched.

## Building & verifying code
- **Tests**: `uv run pytest <path>` (plain pytest often can't import — use `uv run`).
- **Finish gate**: `foreman_guardian_check` (brick compliance + index integrity) before declaring done.
- **Tracking**: `bd` (beads) — `bd ready`, `bd show <id>`, `bd update`, `bd close`. Not markdown TODOs.

## Other MCP powers on the toolbelt
- `@github` — open PRs (after the user pushes; `main` is PROTECTED, no agent `git push`).
- `@builder-mcp` — Amazon internal (code search, CRs, pipelines) when needed.
- `@strands` — Strands SDK docs/reference for SDK-native verdicts.
- `@filesystem`, `@aws-iac`, `@agentcore`, `@creds-agent` — infra / AWS as needed.

## Deep references
`.agents/steering/companion-x-power.md` · `mcp-tools.md` · `platform-doctrine.md` ·
`dev-principles.md` · `workflow.md` · `brick-anatomy.md` · `brick-inventory.md` · `companion-memory.md`
