# Companion-X Crew Features — Roadmap

**Epic:** `python-factory-bp34j`

## Delivery strategy

Build one vertical capability at a time through the factory rails: brick contract → runtime → typed MCP → Companion-X integration → tests. Avoid broad backend construction with no usable product path.

**Owner sequencing decision (2026-09-11):** implement M1–M6 feature rails first. Defer cross-feature UX polish, responsive/animation evidence, interaction-flow capture, and final new-user acceptance to M7. A missing *interactive* capture or browser *operate* permission is evidence debt, not a blocker to dependency-ready backend work. Milestone-local UI may remain minimal where needed to prove integration; M7 owns the coherent final experience. **Amendment (19:03):** every slice that adds or changes a visible surface still captures one view-only render screenshot at slice time (see `LOOP-GUIDE.md` Safety rails) — cheap, no permission needed, and it catches the render bugs that unit tests cannot.

**Program audit (2026-09-11):** the original M0–M7 list ported KiroCrew's *management* layer but omitted the *worker* capability that makes KiroCrew usable for development — the agent could not touch files, a shell, or git anywhere in Companion-X. M2.5 and M6.5 were added to close that gap. The local MCP authentication regression was moved from M7 debt to an immediate fix.

| Milestone | Bead | Outcome | Depends on |
|---|---|---|---|
| I0 | create on start | **Immediate:** launcher owns its API port and token; no 401 on any MCP-backed tab | — |
| I1 | create on start | **Storage hygiene:** persistent graph, telemetry retention/rollup, TinyDB debris removed | I0, M3 |
| M0 | `python-factory-bp34j.1` | OpenRouter provider freedom | — |
| M1 | `python-factory-bp34j.2` | Persistent multi-session management | M0 |
| M2 | `python-factory-bp34j.3` | Durable, visible background subagents | M1 |
| M2.5 | create on activation | **Developer tools:** typed file/shell/git capability + project scoping + Terminal panel | M1 |
| M3 | `python-factory-bp34j.4` | Scheduler brick: cron and one-shot jobs | M1 |
| M4 | `python-factory-bp34j.5` | Goal and monitor loops | M2, M3 |
| M5 | `python-factory-bp34j.6` | Typed lessons and active learning curation | M1 |
| M5.5 | create on activation | **Learning substrate:** unified relationship graph over memory/KB/lessons/sessions/runs + loop cycles scored on the RL rail | M5, M4, I1 |
| M6 | `python-factory-bp34j.7` | Versioned Artifacts capability | M1 |
| M6.5 | create on activation | **Crews:** agent + workspace + memory store + model bundles, Crews page, model/provider picker, any OpenAI-compatible provider | M2.5, M1 |
| M7.5 | create on activation | **Feature parity by checklist:** every in-scope row of `kirocrew-feature-map.md` (111 of 140; `OWNER_NA`/`OWNER_DEFERRED`/`OWNER_REBRAND` excluded) is `PRESENT+WORKS`; Agent Capabilities and Settings each ONE rail icon with the full suite inside; Terminal is a real panel | M7 UI slices |
| M7.6 | create on activation | **Dogfood loop:** Companion-X runs its own goal loop end-to-end — arm from chat, each cycle injects the goal text into a fresh agent turn, agent edits/tests/reviews/updates the ledger, stop file halts — and completes one real checklist row with the KiroCrew loop OFF. **Priority: immediately after the Terminal rows, before the remaining Settings rows.** | Terminal (rows 77–81), devtools unbounded |
| M7.7 | create on activation | **Unified graph memory:** Memory AND KB share ONE target — the `graph` brick's persistent networkx store; a light local embedder continuously creates/updates similarity edges; KiroCrew-style Memory/KB UI (rows 43–54) reads the graph. ChromaDB retired for these two. **First milestone Companion-X's own loop builds after M7.6.** | M7.6 |
| M8 | create on activation | **Rebrand:** every `OWNER_REBRAND` row ditched (owner's words) or re-specced under Companion-X's own name/repo/release story | M7.5 |
| M9 | create on activation | **Deferred features:** Voice → Channels → Remote Crew + webhooks → Brick Store; zero `OWNER_DEFERRED` rows remain | M8 |
| M7 | `python-factory-bp34j.8` | Unified Companion-X UX, KiroCrew data import, acceptance | M2–M6.5 |

**Ordering note:** M5 is in flight and finishes first. I1 is small and deterministic — do it right after I0. Then M2.5 (the dependency that makes M4 loops able to do real work), M5.5, M6, M6.5, M7.

## I0 — Immediate: launcher port/token ownership

- `scripts/companion-x-ui.sh` must refuse to start when the API port is already owned, and must verify that the PID it spawned is the process answering `/api/health`.
- API and Next BFF share exactly one server-only `MCP_LOCAL_AUTH_TOKEN`; it never reaches browser JavaScript.
- Regression: Graph, Evals, Blockchain, Games, Machine Learning tabs and the Sessions deck load against authenticated MCP; a 401 renders a truthful error, never an empty state.

**Exit:** a cold launch with a stale API still on :8000 fails loudly; a clean launch loads every MCP-backed tab with no 401 in the API log.

**New finding (2026-09-17, owner-reported live regression — "sessions and agents page dont load... massive regression"):** root-caused precisely, not assumed. This is a DIFFERENT bug from the launch-time port/token-ownership contract above — it fires on an otherwise-healthy, correctly-launched stack purely from wall-clock time. `components/auth/src/factory/auth/access.py::_seed_local()` seeds the local-dev MCP token via `backend.seed_token(token, subject, audience=...)` with **no `ttl` argument**, so it silently inherits `MemoryBackend.seed_token`'s own default (`components/auth/src/factory/auth/runtime/adapters/memory.py`, `ttl: int = 3600` — exactly one hour). Once that hour elapses, `verify_access_token` correctly returns `{"ok": False, "error": "expired"}`, but `RuntimeCredentialVerifier.verify()` (`access.py`) collapses EVERY failure reason — expired, revoked, wrong audience, anything — into a bare `None`, and the MCP SDK's own auth middleware then reports the exact same generic `invalid_token` 401 to the client regardless of cause. The result: any local dev session running longer than one hour (the norm, not the exception, for this kind of long-running dogfood/loop work) silently loses ALL MCP access — every capability tab shows "unavailable", chat shows "Tools unavailable — retry connection" — with zero indication it's an auth expiry and no client-side recovery path (a page reload does not re-seed the token; only a full process restart does). **Verified live, not assumed**: confirmed via direct `curl` against the owner's actual running API using the real token pulled from the live process environment (hash-compared against the Next.js process's own copy to rule out a token-MISMATCH theory first — they matched exactly) — the correct, matching token still received `401 invalid_token` from the server itself, and the API process's own `ps` uptime (1h12m) was confirmed past the 3600s seed TTL. This directly violates this milestone's own exit criterion ("no 401 in the API log") and the Tier-1 DoD in `north_star.md` ("no MCP 401 on any tab") for any session outliving one hour — not a cosmetic gap. **Fix, scoped precisely, two parts:** (1) `_seed_local()` should pass an explicit long-lived `ttl` for local dev use (a local machine's own dev token has no meaningful reason to expire hourly; a realistic ceiling like 30 days, or reading a `MCP_LOCAL_AUTH_TOKEN_TTL_SECONDS` env override with a long default, both fit the existing `seed_token(..., ttl: int = 3600)` signature with zero new plumbing). (2) `RuntimeCredentialVerifier.verify()`/`SDKTokenVerifier.verify_token()` collapsing every distinct backend failure reason into an undifferentiated `None` is a real, separate diagnosability gap worth fixing on its own merits (a future auth incident — revoked, audience mismatch, anything — will look IDENTICAL to this one in the browser and take the same investigation from scratch) — flagged here but the TTL fix alone resolves the owner's actual reported symptom and is the higher-priority half. **Exit for this finding:** a local dev session provably survives multiple hours of continuous use with no MCP 401 (a real, timed proof — not just reading the new TTL value), and a test pins the local-seed TTL so a future edit cannot silently reintroduce the 1-hour default. Do not touch the owner's currently-running live process directly to patch this — fix the source, prove it with a fresh isolated launch on the 18000/13000 smoke ports, then let the owner restart their own stack when ready.

**FIXED 2026-09-17 (same day, next cycle after the finding).** `_seed_local()` now calls `_local_seed_ttl()` — a small new helper defaulting to `86400` (24h, `seed_token`'s OWN validation maximum, confirmed by reading `ttl > 86400` in `MemoryBackend.seed_token` before picking a number — this avoids widening a shared safety bound for every other caller of that primitive, rather than the roadmap's earlier "30 days" idea which would have exceeded it), overridable down (never up past 86400 — `seed_token`'s own bound still enforces this) via `MCP_LOCAL_AUTH_TOKEN_TTL_SECONDS` for an owner who wants a shorter-lived local token. **Item 2 (collapsed failure-reason diagnosability) deliberately NOT fixed this cycle** — a real, separate, lower-priority gap correctly left for its own slice, not silently dropped. Tests: 4 new (`test_local_seed_ttl.py` — a token seeded at process start still verifies successfully via a mocked-clock jump past the OLD 3600s boundary, matching the owner's exact real-world symptom; the actual default value is pinned at the `seed_token` maximum rather than just "longer than an hour," guarding against a future edit picking some other short value; an owner override that would exceed `seed_token`'s own 1..86400 bound is correctly rejected, proving the fix never bypasses that existing safety check; a shorter owner-chosen override still works). Full `components/auth/test` 200/200, zero regressions. **Live-verified on the safe 18000/13000 smoke ports** (never the owner's live 8000/3000, confirmed both before and after via `lsof`): a fresh isolated launch booted cleanly and a real authenticated MCP `initialize` call against the smoke API returned `200` with the fix applied, proving the new TTL path doesn't break the ordinary happy path. **Honestly disclosed, not overclaimed**: the actual multi-hour wall-clock survival is proven by the mocked-clock unit tests (the same verification technique this session already uses elsewhere, e.g. row 16's checkpoint tests), not by an actual multi-hour live wait in this same sitting — a real multi-hour observation was impractical within one turn; the mechanical proof (the exact same code path, the exact same boundary condition, a real `time.time()` jump) is the honest substitute, disclosed as such rather than silently presented as a full live timed proof.

## I1 — Storage hygiene (small, deterministic, owner-approved 2026-09-11)

Findings from the 2026-09-11 program audit, verified against code and data:

- `projects/companion_x/.env` sets `FACTORY_GRAPH_ADAPTER=networkx` (ephemeral). The code default `persistent_networkx` already snapshots the graph as integrity-checked JSON into the Storage blob store. Switch the env, prove the graph survives an API restart, update the README adapter table.
- `.storage/docs.db` is 22 GB: 10.2M raw OTel spans (10.7 GB) and 280k raw `resource_metrics` export blobs (7.9 GB, 9–28 KB each) in `telemetry_spans` / `telemetry_metrics`. Nothing reads those raw rows back (Metrics tab reads the live aggregator; RL reads Events). The telemetry brick's `RetentionPolicy` exists but the raw doc-store sink ignores it. Add retention + daily rollup as a Scheduler job (first real dogfood of M3): keep a bounded raw window for the Timeline, aggregate older data, delete the rest. Telemetry gets its own DB file so the general document store stops absorbing it.
- Remove the 104 `.storage/docs.json.corrupt-*` TinyDB files (1.8 GB) left from before the SQLite switch.
- The remaining dead pre-SQLite `.storage/docs.json` (~41 MB) is non-authoritative cleanup debt; remove it only with explicit owner approval.

This does **not** reduce adapter choice anywhere — multiple adapters per brick are a deliberate feature for project composers.

**Exit:** graph state survives restart; `docs.db` shrinks below 1 GB with the Timeline and Metrics tabs unchanged; a Scheduler job owns telemetry retention; debris gone.

**Status (2026-09-11 15:29, live acceptance):** CLOSED_PASS_WITH_NITS. Runtime instrumentation dependency placement is fixed; Companion-X started through `scripts/companion-x-ui.sh` on isolated smoke ports API `18000` / Next `13000`, Telemetry reported healthy, and a live span created through the authenticated Next BFF flushed 25 raw `telemetry_spans` rows into `.storage/telemetry.db`. The generic `.storage/docs.db` remained exactly 240 nontelemetry rows / 335,872 bytes. The smoke launcher was torn down and both isolated ports released. The legacy 41 MB `.storage/docs.json` was not touched and still awaits an explicit owner decision.

## M0 — Provider freedom

- Make provider resolution explicit through `llm_gateway` configuration.
- Build the framework-native OpenRouter chat model through LangChain.
- Preserve streaming, tool calls, structured output, telemetry, and CopilotKit v2 events.
- Remove stale runtime documentation that describes inactive model paths.

**Exit:** one real OpenRouter chat turn calls one typed MCP tool and renders correctly without `kiro-cli`.

## M1 — Persistent sessions

- Extend Agent's session ownership with durable metadata and lifecycle operations.
- Add create/list/resume/rename/archive/switch MCP tools.
- Accept user messages during an active turn with persisted correlation identity and truthful `written`, `consumed`, or `requeued` delivery state.
- If the runtime cannot consume a steer at an inference boundary, requeue it exactly once for the next turn—never drop or duplicate it.
- Add a Companion-X session sidebar and agent-controlled navigation.

**Exit:** restart the API, resume a session, prove persona/history continuity, and prove a mid-turn user message is either consumed by the active turn or visibly requeued once.

## M2 — Background subagents

- Connect Agent spawn to Workflow durable attempts.
- Preserve nested tool/node events in AG-UI.
- Add per-attempt status, live steering, cancellation, completion delivery, and retry.
- A steer to a running subagent must be consumed in-flight or requeued exactly once with truthful delivery state.
- Re-enable per-node activity inside the existing containment UI.

**Exit:** launch, observe, restart, reconcile, and complete a background subagent.

## M2.5 — Developer tools (the worker capability)

KiroCrew gets file, shell, and git access from `kiro-cli`. Companion-X has none. Without this, sessions, subagents, and goal loops can only talk.

- Inspect KiroCrew's tool contracts (read/write/edit file, bounded shell, git, glob/grep) and safety rails (path confinement, denylist, destructive-command confirmation) and port the behavior, not the implementation.
- Extend the existing `sandbox` brick (or a focused `devtools` brick if meta-architect rules sandbox is the wrong owner) with typed MCP operations: `read_file`, `write_file`, `edit_file`, `list_dir`, `search`, `run_command` (bounded, streaming, confined to the project root), and git reads (`status`, `diff`, `log`); stage, commit, and push are separate `@authoring` operations requiring explicit user approval.
- Add **project scoping**: a session/crew binds to one project directory; every devtool resolves paths inside it; file search and `@`-mentions in the chat composer are scoped to it.
- Add a **Terminal panel** to the cockpit that streams `run_command` output through the existing AG-UI activity rail; reuse KiroCrew's terminal/agent panel icons where license permits.
- Register QA and meta-architect gates as **Evals-owned acceptance policies executed through sealed, personaless Workflow-managed LangGraphs** rather than ad-hoc personas. The reviewer manifest freezes rubric/model and exactly the read/list/search/git-read Devtools scope; it receives no command/write/authoring tools. Builder-run deterministic checks are immutable evidence inputs, Evals deterministic/model evaluators score them, and Evals persists the thresholded immutable report.

**Exit:** through Companion-X chat alone, the agent reads a file in a scoped project, edits it, runs the project's tests in the Terminal panel, and shows a git diff — and a path outside the project root is refused.

## M3 — Scheduler

- Add a focused Scheduler brick using the canonical brick anatomy.
- Classify every tool with the standard MCP taxonomy and enforce strict Pydantic ingress plus typed `ToolResult` egress.
- Support recurring cron, intervals, and one-shot execution.
- Enroll due work into Workflow exactly once.
- Add Schedule page and chat tools.

**Exit:** a persisted schedule fires once, survives restart, and can be paused/resumed.

## M4 — Goal and monitor loops

- Model each cycle as a durable Workflow attempt triggered by Scheduler.
- Read north star, roadmap, and task ledger every cycle.
- Advance one highest-leverage task and verify evidence.
- Persist blocker-once and stop-file semantics.

**Exit:** a multi-cycle goal advances work, resumes after restart, and halts deliberately.

## M5 — Lessons and curation

- Compose Learning into Companion-X.
- Add typed lesson fields: rule, negative, scope, source, evidence, status.
- Activate curation subscriptions and durable Events storage.
- Recall accepted lessons into later agent turns.

**Exit:** explicit feedback produces a curated lesson that changes a later response.

## M5.5 — Learning substrate: one relationship graph, and loops that get scored

Owner direction (2026-09-11): memory and knowledge should be queryable as one connected picture so the assistant can see relationships it would otherwise miss. Verified today: Memory (A-MEM on Chroma), KB (Chroma), and Graph (networkx) are three silos with zero links; Workflow goal loops and background subagents emit no reward or learning events.

Design rule: **sources of record stay where they are; the graph is the relationship projection.** Same pattern M5 uses for Lessons → Memory.

- Memory items, KB documents, lessons, sessions, workflow runs, and findings become graph nodes with typed edges (`derived_from`, `mentions`, `learned_in`, `about_run`, `supersedes`). Chroma keeps owning similarity search; the graph owns relationships. No brick merge, no new brick.
- Projection is fed by the existing Events bus: one subscriber in the graph brick over the existing memory/KB/lessons/session/workflow lifecycle events. Stable IDs cross the boundary; content does not have to.
- One typed `graph_neighborhood` tool (deterministic) expands a set of hit IDs to their k-hop neighborhood, and an Agent before-model middleware does hybrid recall: vector hits → neighborhood → bounded context.
- Workflow loop cycles and background-subagent completions publish the existing workflow-completion learning event with `domain_class="dev-loop"` and the cycle report (evidence strength, test delta, review verdict), so the existing generic score dispatcher evaluates the registered self-gating Learning sources (`llm-judge`, telemetry, and Games only when graph ground truth exists) and feeds the canonical `reward.computed` rail. No new scoring path.
- Requires I1 (persistent graph) or the projection evaporates on restart.
- Automatic dropped-event reconciliation is deferred until source bricks expose immutable change feeds; M5.5 proves the protected Graph rebuild seam and restart durability, not a mutable-list polling job.

**Exit:** a lesson created in M5 is reachable from the run that produced it and the KB document it cites through one `graph_neighborhood` call; a completed goal-loop cycle produces a stored reward; both survive an API restart.

## M6 — Artifacts

- Add an Artifacts brick over Storage and UI.
- Support stable slug, kind, version, tags, folders, comments, and rollback.
- Add gallery/detail pages and chat-driven save/update/navigation.

**Exit:** save, update, browse versions, comment, and restore an artifact through Companion-X.

## M6.5 — Crews, workspaces, and provider choice

- Port KiroCrew's **Crew** concept as data, not a new runtime: a crew = persona (agent template) + project workspace + memory store + model. Store through the existing Agent persona registry and Session brick; no `if crew == ...` anywhere.
- Add the **Crews page** (cards/list, "new sessions use", new crew) and a **model/provider picker** in the chat footer, both driven by typed MCP and controllable through CopilotKit frontend tools.
- Generalize the M0 profile resolver so any **OpenAI-compatible endpoint** (`openai-compat/<name>` with `<NAME>_BASE_URL` / `<NAME>_API_KEY` / `<NAME>_MODEL`) works without new code — this is how opencode, LM Studio, vLLM, and similar plug in. Keep OpenRouter, Ollama, and Bedrock paths byte-compatible.
- Reuse KiroCrew agent/model selector icons verbatim where the license permits.

**Exit:** create a crew bound to a project and to a model that differs from the session default (a different OpenRouter model, or `ollama/<model>` if Ollama is running — no new provider is required); start a session on it; the agent edits a file in that project through M2.5 tools with the crew's model, and the picker shows the crew's choice. **Owner decision (2026-09-13):** the `openai-compat/<name>` profile is complete as code with unit tests; a live proof against a non-OpenRouter endpoint is deferred until the owner actually adds one (opencode, later). Do not block on it.

## M7 — Product integration

- Add notification center and deep links for sessions, runs, schedules, artifacts, and crews.
- Make every new page controllable through CopilotKit frontend tools.
- **KiroCrew data import:** one-shot import of `~/.kiro/crew` semantic/episodic memory, lessons, and safe schedule definitions into the corresponding bricks (temp-copy only, per-kind counts, spot-checked payloads) so switching to Companion-X preserves the supported durable knowledge. KiroCrew's own canonical onboarding import excludes `sessions/*.jsonl`; M7 does not fabricate foreign LangGraph checkpoints.
- Cross-feature UX polish, responsive/animation evidence, and new-user acceptance deferred from M1–M6.5.
- Run cross-capability acceptance recipes and regression checks, including the I0 authenticated-tab regression.

**Exit:** all Tier-1 criteria in `north_star.md` have cited evidence, every milestone has a Gate B `PASS` or `PASS_WITH_NITS`, and the Gate C release seam in `quality-gates.md` passes with no new Guardian violations.

## M7.5 — Feature parity by checklist (owner escalation 2026-09-13 18:50 / 19:23)

**Root cause of the four-day gap:** this roadmap was written at the *capability* level from memory of KiroCrew, not from KiroCrew's code. KiroCrew publishes its own granular map — `docs/feature-map/README.md` in https://github.com/kirodotdev/kirocrew — one row per user-facing feature with the URL, page file, handler, and endpoints. Nobody pointed the loop at it. Now it is the acceptance list.

**The list:** `kirocrew-feature-map.md` in this directory (140 rows, 12 areas), generated by `scripts/gen_kirocrew_feature_map.py` from the read-only clone at `/Users/wdaniero/workplace/kirocrew-workspace/kirocrew-src`. Regenerate after pulling upstream; Status/Evidence/Location cells survive regeneration. Read the referenced upstream page/handler to learn the behaviour; **never copy KiroCrew code** — implement Python-Factory style (brick + MCP tool + typed contracts, LangChain/LangGraph on MCP v2, CopilotKit v2, shadcn/ui).

**Owner IA decisions (19:23, binding):**

1. **Agent Capabilities = ONE rail icon**, sub-nav inside: Crews · Agent Templates · Connections · Skills · Steering · Hooks · Prompts · Schedules · Artifacts · Lessons.
2. **Settings = ONE gear icon**, full suite inside: Overview · Import/Export · Chat · Display · Voice · Notifications · Shortcuts · Skills · Channels · Browser · Computer Use · Remote Crew · Privacy · Security · Developer · About — each is a checklist row that ends `PRESENT+WORKS` or `OWNER_NA`.
3. **Schedules and Artifacts lose their own rail icons** → under Agent Capabilities (owner said "pick one"; Settings is the alternative if he overrides).
4. **Terminal** is a real dockable panel with tabs, not an in-chat renderer.

**Procedure:**

- Cycle 1: **census only** — set every row's Status honestly (`TODO`→`MISSING`/`PRESENT+BROKEN`/`PRESENT+WORKS`/`OWNER_NA`), no building. Rows needing an owner call go in the ledger as ONE consolidated question.
- Then: IA restructure first (the two single-icon suites + rail cleanup — done 2026-09-13), then rows in the **OWNER PRIORITY ORDER defined at the top of `kirocrew-feature-map.md`** (Agent Capabilities → Settings → Terminal/subagents → Schedules/Artifacts/Memory → remaining Chat & sessions polish → the rest), never file order. One row or tightly coupled group per slice, row updated in the same cycle, one view-only screenshot per new/changed surface.
- **Renders ≠ works.** A mounted page showing "unavailable/empty" because its API is missing is `PRESENT+BROKEN`. `PRESENT+WORKS` requires the control to round-trip through the MCP tool and show the result.
- `OWNER_NA` only in the owner's words, quoted in Evidence. Never inferred.

**Exit:** zero `TODO`, `MISSING`, or `PRESENT+BROKEN` rows among the **in-scope** rows of `kirocrew-feature-map.md` (in-scope = not `OWNER_NA` / `OWNER_DEFERRED` / `OWNER_REBRAND`; 111 rows as of 2026-09-14 12:39, per `scripts/feature_map_status.py`); Gate 0 confirms the count; the rail matches IA decision 1–4 with a screenshot.

## M7.6 — Dogfood loop (owner priority 2026-09-14 21:03; runs INSIDE M7.5, right after the Terminal rows, BEFORE the remaining Settings rows)

**Why now:** the owner's whole reason for this port is the autonomous goal loop — "the most productive way I've found to do dev." Until Companion-X can run its own loop, every other feature is decoration. This milestone makes Companion-X able to finish the rest of this checklist *itself*, with KiroCrew turned off.

**What exists (verified by meta-architect `07130705`, 2026-09-15):** the complete cycle→Agent bridge is already production-wired on the correct owners. `workflow.start_loop` persists the loop/cycle; API lifespan pollers admit cycles and tick Scheduler; `loop_admission._task` carries objective+`cycle_instructions`; Scheduler `replay_claimed` calls public `agent.spawn_background` with `output_schema="loop-cycle-report-v1"`; Agent creates a fresh `bg_<hash>` thread/persona graph and drives the durable Workflow attempt through `workflow.resume_run`; Workflow validates `structured_outputs[agent_id]` as `LoopCycleReport`, settles disposition, schedules the next cycle, and honors `.companion-loop-stop-<loop_id>`. Restart continuity, goal success, stop-file halt, and monitor no-false-success already pass in `test_loop_acceptance.py`. **Do not add a bridge, engine, runtime, or parallel ledger.**

**The real gap:** the durable policy test mocks `agent.spawn_background`. Two live seams remain unproven: (a) a real one-node Agent graph with `output_schema="loop-cycle-report-v1"` persists the exact nested structured output that `loop_reconcile._outcome` reads; (b) one real unattended Companion-X loop uses the Developer persona's existing exact Devtools scope to complete a checklist row.

**Minimum verification slice (one row-group; do not gold-plate):**

1. **Developer scope contract.** Reuse/run `test_spawn_catalog_parity.py::test_developer_persona_has_exact_devtools_scope`; do not add tools, prompts, tiers, or another persona.
2. **Live structured-output seam.** Run a real `agent.spawn_background`/`workflow.resume_run` using `delivery_mode="workflow_loop"` and `output_schema="loop-cycle-report-v1"`; assert the persisted Workflow result contains `task_result.result.structured_outputs[developer]` validating as `LoopCycleReport`.
3. **One real dogfood cycle.** With the KiroCrew loop stopped, arm `workflow.start_loop(agent_id="developer", ...)` against one small unchecked feature-map row. Let API pollers perform admit→schedule→fire→spawn→settle unattended. Require real file edit, targeted tests, ledger/row update, `success`, `goal_complete`, and no cycle N+1. Reuse the existing server-computed stop sentinel for the halt proof.

**Exit (all three, with evidence in the ledger):**
- Existing durable restart/stopping acceptance remains green unchanged.
- Live structured Agent output validates through the exact persisted shape consumed by Workflow reconciliation.
- Companion-X's own loop, with KiroCrew loop OFF, completes one real in-scope checklist row and halts; cite loop id, cycle/run ids, row flipped, tests, and evidence.
- Rows 55, 58, 61 → `PRESENT+WORKS`.

**After M7.6 closes, the owner decides whether the remaining M7.5 rows are built by the KiroCrew loop or by Companion-X's own loop.** Default: Companion-X's own, so the rest of the port is also its acceptance test.

## M7.7 — Unified graph memory (owner ruling 2026-09-15 06:25; first milestone built by Companion-X's own loop after M7.6)

Owner: "i never 'deferred' unified graph for memory + memory, that's what i wanted that rust did well (rust used overgraph). so i like kirocrew style ui for accessing KB/Memory i just want them to have 1 target which is networkx. I think before they were both chromadb which isn't a graph. The point is to have a graph for memory/kb because i think the agents accessing it get more power because everything is related. the trick is to have some embedding model (either super light on the machine like kirocrew does or elsewhere) to constantly make/update connections."

**Current state (verified in code 2026-09-15 06:20 — BASELINE, superseded below):** `MEMORY_BACKEND=amem` → ChromaDB (`components/memory/.../adapters/amem.py`); `KB_BACKEND=chromadb`; `GRAPH_BACKEND=networkx` but the graph holds findings/runs/taxonomy only — Memory and KB never write to it; `MEMORY_EMBEDDINGS` is empty (no-op or Bedrock call-out), so nothing local is making connections. Two vector stores that don't know each other, and a graph neither uses.

**Progress (verified in code 2026-09-15 18:05):** the loop built the M7.7 core in cycles 24–30: `components/memory/.../runtime/adapters/graph_store.py` and `components/kb/.../runtime/retrieval/graph_store.py` (Memory and KB both writing to the graph through their existing ports), `embedding_local.py` in both bricks (in-process Qwen3-Embedding GGUF), memory MCP `deterministic.py` embedding status/stats tools, with tests (`test_graph_store.py`, `test_embedding_local.py` in each brick). Checklist: rows 46 `Explore memory`, 49 `Episodic search`, 51 `Memory graph` PRESENT+WORKS; 43 `Memory browser` and 50 `Embeddings` PRESENT+BROKEN; 44/45/48/53 pending owner rulings. **Not yet done:** flipping the owner's stack to the graph backends (`MEMORY_BACKEND=graph` / `KB_BACKEND=graph` in `projects/companion_x/.env` + restart), the one-shot ChromaDB → graph migration, the Scheduler similarity-edge job, and the exit proof (rows 43–54 green, KB and Memory pages showing one connected graph). Review of cycles 24–30 ran on the opus persona before the `compx-auditor` rule was in force — re-dispatch the M7.7 Gate A.5 through `compx-auditor` before the exit proof.

**Design shape (consult meta-architect on the seams; SDK-first; adapter breadth stays — this ADDS a graph adapter as the default, it does not delete the others):**

1. **One store, riding the existing rails.** Memory already has a `MemoryStore` port (`components/memory/.../runtime/ports.py`) with `amem`/`cognee`/`zep`/`neo4j` adapters; KB has a `VectorStore` port (`components/kb/.../runtime/ports.py`) with `chroma`/`bedrock`/`neo4j_vector`/`bm25`. **Add one `graph` adapter to each**, selected by `MEMORY_BACKEND=graph` / `KB_BACKEND=graph`, both writing to the `graph` brick's **persistent networkx** store (`persistent_networkx*.py`, lock + snapshot already exist). No new brick, no new MCP tools — agents keep calling `memory_store`/`memory_retrieve`/KB search unchanged. Node kinds: `memory`, `lesson`, `document`, `kb_chunk`, `finding`, `run`, `session`, `artifact`. Edge kinds: `similar_to` (embedding, weighted), `part_of` (chunk→document), `derived_from`, `mentions`, `in_session`, `cites`. **Shape rule (owner question 06:35):** the graph holds *chunks and relationships*, never multi-MB payloads — a document is one `document` node (title, source, hash, `blob_ref`) plus `kb_chunk` nodes of ~500–1000 tokens; the full bytes live in the Storage brick by reference. This keeps persistent-networkx snapshots small and is the OverGraph shape.
2. **Light embedder, always on — KiroCrew's way.** Upstream runs **Qwen3-Embedding-0.6B as a GGUF in-process via llama.cpp** (`src/kiro_crew/embeddings.py`: `_GGUF_FILENAME = "qwen3-embedding-0.6b.gguf"`, `LlamaCppEmbedder`, 1024-dim, one shared embedder for vector memory + knowledge library, keyword-search fallback when the model is absent). crew-rs proved the same model family with OverGraph. **Default for Companion-X: the same Qwen3-Embedding-0.6B GGUF through `llama-cpp-python`, in-process, as the `MemoryEmbedder` implementation** — one embedding space across Companion-X, crew-rs, and imported KiroCrew data. Second adapter: a tiny Ollama embedding model (`nomic-embed-text`) for when the owner prefers the model out of the API process. Owner rule: embeddings only, never inference; no Bedrock embeddings on this machine. Embedding runs as a Scheduler job: new/changed nodes are embedded and `similar_to` edges recomputed against a k-NN neighbourhood; the embedding-space signature is stored on the graph (as upstream does with `embedding_space_sig`) so a model swap triggers a re-embed instead of silently mixing spaces.
3. **Agents read the graph.** `memory_retrieve`, KB search, and the hybrid-recall middleware traverse the graph (seed by embedding similarity, expand 1–2 hops along typed edges) so recall returns *related* context, not just nearest vectors. Lessons brick and Notification deep links attach to the same nodes.
4. **KiroCrew-style UI on top (rows 43–54).** Memory browser, Store picker (shows the one graph store + adapter health), Explore memory (graph neighbourhood view — reuse the existing Graph canvas), Episodic search, Embeddings status (model, queue depth, last run), Memory graph, Usage, Backups (snapshot of the persistent networkx file). Row briefs 43–54 in `row-briefs.md` already map these; re-check them against this milestone's design before building.
5. **Migration.** One-shot importer from the existing ChromaDB collections (Memory + KB) into graph nodes with embeddings recomputed locally; runs through the Migration brick's Workflow path so it is resumable. ChromaDB stays installed as a non-default adapter (adapter breadth), no longer the target.

**Exit:** `MEMORY_BACKEND=graph` and `KB_BACKEND=graph` in the owner's `.env`; a stored memory and an ingested KB document appear as nodes in the same persistent networkx store with a `similar_to` edge created by the local embedder within one scheduler tick; `memory_retrieve` returns a KB chunk reached via graph traversal that vector-only search would not rank; Memory browser + Explore render the neighbourhood; rows 43–54 `PRESENT+WORKS`; ChromaDB data migrated with counts matching; Gate A.5 + security (local files, no data leaves the machine).

## M8 — Rebrand (owner ruling 2026-09-14 12:39; runs AFTER M7.5, BEFORE M9)




Design: `m8-rebrand-design.md` (stories R-01..R-12, branding census, owner substitutes S-1..S-6). Product name stays **Companion-X**; KiroCrew survives only as the importer's data-source name and Lessons provenance. **Note for M7.5 now:** row 93 Computer Use currently *points the user to the KiroCrew app* — that is `PRESENT+BROKEN` under owner ruling "Computer Use → CORE"; build it as a Companion-X capability (story R-03) when the Settings area reaches that row, do not wait for M8.

Owner: "old kirocrew urls wont work because im making this my own thing. I'll eventually point to my own github and other shit (even rebrand). So we can rebrand/whatever last but before the deferred features."

Scope = every `OWNER_REBRAND` row (16 as of today): the Redirects area (132–140) and the KiroCrew-identity operator surfaces (117–123: Cloud launch, Mobile connect, Kiro sign-in, Source-provider review, Crash report notice, Startup feature video, OpenAI-compatible API). Per row decide **ditch** (owner says so, in words) or **re-spec** under Companion-X's own name, repo, and release story. Product name, repo URL, and update/changelog source are owner inputs collected ONCE at M8 start. Exit: zero `OWNER_REBRAND` rows remain (each becomes `PRESENT+WORKS` or `OWNER_NA`).

## M9 — Deferred features (owner ruling 2026-09-14 12:39; runs AFTER M8)

Owner: "we can defer voice/channels (i want these but we can put these at the back since they're features)"; "remotecrew/webhooks sound super interesting but not core. Defer like features (e.g. slack etc)"; "i dont need an app store, we can have a 'brick store' and defer this to later."

Scope = every `OWNER_DEFERRED` row (13 as of today), in this order: (1) Voice (87); (2) Channels — Slack/Discord delivery (91); (3) Remote Crew + webhooks (94, 95, 116); (4) **Brick Store** replacing KiroCrew's Apps area (69–76) — re-spec against bricks/MCP powers, not an app marketplace. Exit: zero `OWNER_DEFERRED` rows remain.

## Deferred

- ~~Memory/KB/Graph consolidation.~~ **Not deferred — never was, per owner 2026-09-15. It is M7.7 Unified graph memory.**
- ADK or agent-framework replacement.
- Full KiroCrew channel/app ecosystem.
- KiroCrew Skills authoring/loading system (`crystallize` and reusable skill packs).
- Interactive browser automation (Playwright operate/click/type).
- Artifact remote publishing/sharing/provider sync, forks, file-backed live reload, and binary/image asset lifecycle.
- One-click public artifact deploy (`deploy-web` / `artifact-deploy`) and webapp lifecycle.
- Voice, computer use, and external messaging-channel parity.
