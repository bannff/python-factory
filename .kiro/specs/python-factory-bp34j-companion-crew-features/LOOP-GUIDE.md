# Companion-X Crew Features — Loop Guide

## Goal instruction

> Your north star is in `north_star.md`, roadmap in `roadmap.md`, tasks in `tasks.md`. Pick the single highest-leverage next step toward the goal and execute it. Update `tasks.md`. Post a blocker ONCE if genuinely stuck. To halt the loop, create `.stop-companion-crew-features` at the root of the normal checkout.

## Scope

Operate only inside the normal `/Users/wdaniero/workplace/python-factory` checkout and epic `python-factory-bp34j`. Track A (`crew-rs`) is independent and must not be read, modified, paused, or coordinated from this loop.

## Every cycle

1. Stop immediately if `.stop-companion-crew-features` exists at the checkout root.
2. Read `north_star.md`, `roadmap.md`, `tasks.md`, and `quality-gates.md`, plus the active milestone design document linked from `tasks.md`, before acting. **From M7 onward also read `kirocrew-feature-map.md`** — it is the granular, code-referenced acceptance list; pick the next `TODO`/`MISSING`/`PRESENT+BROKEN` row in area order and update that row in the same cycle. When you need to know how a feature behaves, read the upstream page/handler the row cites (read-only clone at `/Users/wdaniero/workplace/kirocrew-workspace/kirocrew-src`); never copy the code. Do not read `tasks-archive.md` unless the current step needs history.
3. Confirm the active Bead and claim it before implementation.
4. Inspect current code and tests; memory, prior summaries, **and steering docs** are not ground truth — code is. If a steering doc or README contradicts the code you are touching, fix the doc in the same slice and note it in the ledger.
5. Before each KiroCrew feature port, inspect the upstream implementation and tests. Port its behavioral contract and failure guarantees—not its architecture or `kiro-cli` dependency.
6. Select one highest-leverage, dependency-ready step—not an entire milestone.
7. For non-trivial changes, follow the repo's required specialist/design workflow.
8. Run existing targeted tests before changing behavior.
9. Implement one coherent slice through contract, runtime, MCP, and UI as applicable.
10. Run the applicable Gate A checks in `quality-gates.md`; run Guardian whenever code changes.
11. Increment `Slices since independent review` in `tasks.md`. At three slices—or an immediate architecture trigger—run one rotating Gate A.5 reviewer and reset the counter.
12. At a milestone seam, dispatch Gate 0 (program fidelity), Gate B QA, and Gate B meta-architect once; add only triggered specialists. Apply any Gate 0 `AMEND_PLAN` edits before the next slice.
13. After each complete feature port, hand its diff and evidence to a meta-architect for a one-line verdict on factory-rail reuse, ownership, simplicity, MCP contracts, and SDK-first compliance before closing its Bead.
14. Update `tasks.md` with exact evidence and the next ready step. Keep the cycle log to the last 15 rows; move older rows to `tasks-archive.md` at every milestone seam.
15. Close a Bead only when its acceptance evidence is real. Write Beads state at every milestone seam so `bd ready` matches the ledger.
16. If all Tier-1 criteria are proven, create the stop file and halt.

## Cycle mechanics — explicit, do not infer (owner amendment 2026-09-14 12:41, builder model changed to a faster one)

These are the concrete mechanisms behind steps 7–13. Use them by name; a cycle that skips them is not a cycle.

- **Row briefs (owner amendment 2026-09-14 14:15).** A separate read-only prep chat pre-researches upcoming rows into `row-briefs.md`. Before starting a row, check that file: if the row's brief is marked `READY`, use it as your research and skip re-reading upstream from scratch (verify its file citations exist; trust its mapping unless the code contradicts it). If there is no READY brief, do the research yourself as before — **never wait for a brief and never write to `row-briefs.md`** (the prep chat never writes to `tasks.md` or the feature map; that separation is what lets the two run at once).
- **Design consult BEFORE new substrate.** If a slice would add a new model, store, adapter, middleware, graph node, MCP tool, or brick, first `spawn_run` ONE read-only **meta-architect** reviewer with: the proposed design (≤1 page), the north-star Non-negotiables, and the question "does an existing brick/store already provide this; is this the simplest thing that satisfies the owner's words?" Wait for the completion event; apply `AMEND_PLAN` before writing code. Pair a **security-engineer** reviewer in the same batch when the slice touches auth, approval, secrets, git, or file/command execution. Never write "the architecture is now settled" in the ledger without citing the consult ID. **Consults decide HOW, never WHETHER:** where the owner has ruled (Non-negotiables — autonomy, approval list, real terminal/commands), the consult prompt must quote the ruling and ask only for the safest implementation of it; a verdict that recommends allowlists, sandboxes, "bounded" runners, or confirmation prompts against a ruling is recorded as OUT_OF_SCOPE and not applied.
- **Simplicity check on owner-phrased features.** When the owner described a feature in simple terms ("a simple list", "one gear icon"), the default is to REUSE an existing store/surface (e.g. the durable Settings/Chat preferences store, the existing approval card) and add the minimum. A design with more than one new store/model/adapter beyond what an existing brick offers needs the meta-architect's explicit approval of that extra piece, quoted in the ledger.
- **Builders fan out.** For a slice with two or more independent pieces (separate bricks, separate files with separate tests, backend vs frontend), `spawn_run` them as parallel builder tasks in ONE batch (≤3 on this 18 GB machine), each with: the row number, the upstream page/handler to read, the factory conventions to follow, the exact test command bounded by `timeout 900`, and "report file paths + test output, do not update the ledger." Then STOP and wait for all completion events; do not do the work yourself after spawning. Serial work only when pieces genuinely depend on each other.
- **Evidence is captured with named tools.** After any UI change: `browser_navigate` to the surface on the 18000/13000 smoke stack, `browser_take_screenshot`, **read the frame**, save under `/tmp/python-factory-evidence/<milestone>-<surface>.png`, cite the path. If `browser_*` tools are absent from your tool list, run the project's headless Playwright (`npx playwright test` in `frontends/next-dashboard`, `timeout 900`). MCP round-trip proof = call the real MCP tool and show the state change in the UI, not a unit test alone.
- **Minimum cycle depth.** A cycle ends with at least one of: a feature-map row status changed with evidence; a consult verdict applied; a builder batch integrated and tested. A cycle whose ledger row reports only "foundation in place" or "architecture settled" with no row flipped, no consult ID, no test count, and no screenshot is a wasted cycle — do not write that row; keep working until one of the three has happened or the 2-hour turn limit forces a checkpoint. **The auto-nudge is not a question — never answer it with a status summary.** If you find yourself restating the plan or re-describing screenshots the owner attached earlier, stop writing and take the first concrete action of the plan (open the upstream handler, spawn the consult, write the failing test). Two consecutive cycles with no file changed means the cycle is broken: post ONE blocker naming what you could not do and why, rather than a third summary.
- **Upstream defines the job and the controls — Companion-X defines the how.** For every checklist row, open the KiroCrew page named in the row's `Page (website/src/)` column and write down two things: the *job* a user gets done there (in one sentence, in the user's words) and the *controls* they need for it (create / edit / delete / enable / see-what-happened). That list is the spec. Then build it on Companion-X's own rails — bricks, ports and adapters, MCP tools, CopilotKit — using the polymorphic patterns the factory already has. **Do not copy KiroCrew's code, architecture, or screen layout**; a different layout is fine, a better one is welcome. **Do not expose a brick's internal vocabulary as the user's form** either — that is how Hooks became "Event pattern / Handler" (free text, no list of handlers, no agent lifecycle events), which a user cannot use to get the job done (owner smoke 2026-09-15 13:44). The acceptance test is always the same question: *can a Companion-X user accomplish the upstream job here, end to end, in a real browser?* Not "does it look like KiroCrew" and not "does the brick call succeed". A tab that renders "unavailable" is MISSING, not PRESENT.
- **Reviews are dispatched, not narrated — and they run on the auditor persona.** Gate A.5 / Gate 0 / Gate B and every design consult mean `spawn_run(agent="compx-auditor", ...)` — the fable-5 read-only auditor at `~/.kiro/agents/compx-auditor.json` — with the diff, the feature-map row numbers, and the evidence; wait for the completion event; record its verdict ID. **Never spawn `kirocrew` / `kirocrew-lite` as a reviewer** (that is the builder's own model grading itself and it is how five owner-visible defects passed review on 2026-09-15). Self-review is not a gate. Builders/researchers may use `kirocrew-lite`.
- **Owner smoke test after every green row (owner escalation 2026-09-15 07:47–08:01).** Five minutes of the owner clicking found five defects — dead terminal keys, backwards typing, theme flash, no + buttons, one-model picker — that a night of mock-vs-mock reviews graded PASS. Rule: when a row flips to `PRESENT+WORKS`, post ONE short owner-facing note in the chat: what to click on `localhost:3000` (three steps max), what they should see, and whether a stack restart is needed. Then continue; do not wait. The owner's report of any defect on that row is a P1 that outranks the next row. Never mark a UI row green without at least one **real** end-to-end proof (real browser against a real API with real data), not a mock on both ends.

## Safety rails

- Work only in the normal `/Users/wdaniero/workplace/python-factory` checkout; keep changes uncommitted and never push unless the owner explicitly asks.
- Do not touch Track A.
- Do not introduce ADK, Strands, or `kiro-cli`. The runtime is LangChain/LangGraph on MCP v2.
- Developer tools stay confined to the scoped project root; `run_command` is bounded and streams; push and destructive git are `@authoring`.
- Preserve CopilotKit v2 and its frontend-tool page-control path.
- Do not consolidate Memory/KB/Graph in this program.
- Do not create a KiroCrew mega-component.
- Use typed MCP interfaces between bricks; no internal cross-brick imports.
- New bricks must match a compliant exemplar: `BRICK.yaml`, `runtime/ports.py`, adapters, `mcp/{deterministic,operational,authoring}.py`, strict brick-local Pydantic input DTOs, typed output DTOs, `ToolResult` envelopes, and `interface.py`.
- Workflow owns durable attempts; Scheduler owns time; Agent owns intelligence.
- Use SDK/framework primitives before custom wrappers.
- Keep files under 200 lines.
- Run one heavy build/test command at a time.
- **Every test or build command is bounded (2026-09-13, after four memory-starvation stalls):** wrap in `timeout 900` (`gtimeout` if needed); run one test tree per command, never three; run vitest as `vitest run <tree> --pool=forks --poolOptions.forks.maxForks=2`; never pipe a long command through `| tail` — let output stream so a slow run is visibly different from a dead one. A run that hits the timeout is a real failure to record (likely host memory pressure), not something to retry immediately. Builders and sub-agents inherit this rule.
- Never run a server or launcher (`companion-x-ui.sh`, `next dev`, `uvicorn`, `main.py`) in the foreground of a tool call — it never exits and blocks the loop (cycle 81 lost 46 minutes this way). Background it, wrap the whole check in `timeout <secs>`, poll health, and kill the process group in a trap before the tool call returns. Prefer the deterministic test fixture (`projects/companion_x/test/test_local_launcher.py`) over a live launch.
- `kill -TERM <launcher pid>` then `wait` is NOT a valid cleanup — `next dev` outlives its parent and the `wait` hangs forever (a second 56-minute stall at ~14:27). Start the launcher with `setsid` (or `set -m`) so it owns a process group, clean up with `kill -TERM -- -<pgid>; sleep 2; kill -KILL -- -<pgid>`, and never call `wait` without `timeout`. Do not launch on ports 8000/3000 while the owner's own Companion-X may be running — use alternate ports for smoke launches.
- Never weaken tests or acceptance criteria to make a cycle pass.
- Never claim UI completion without visual verification.
- **Render proof per surface (owner amendment 2026-09-11 19:03):** any slice that adds or changes a user-visible surface (a panel, page, renderer, deck, badge) captures **one view-only screenshot** of it as Gate A evidence in the same slice — Playwright is available and view-only needs no Globe permission. Use the standard launcher on `API_PORT=18000 NEXT_PORT=13000`, or the running owner stack read-only if it is up. Read the frame and state what it shows; save it under `/tmp/python-factory-evidence/<milestone>-<surface>.png` and cite the path in the ledger. This is a "does it render" check, not acceptance: interaction flows, responsive/animation evidence, and new-user review remain M7. A slice that ships a renderer with unit tests and no frame is not LOCAL_GREEN.
- **Which browser to use for evidence (owner amendment 2026-09-13 22:18) — two exist, prefer in this order:**
  1. **Playwright MCP `browser_*` tools, if they are in your tool list** (`io.github.microsoft/playwright-mcp` is installed in KiroCrew). Use them for navigate + snapshot + screenshot, and for click/type when an MCP round-trip proof needs it. Prefer a headless/isolated context; the loop's evidence must never depend on the owner's Chrome tabs, cookies, or focus.
  2. **The project's own headless Playwright** (`frontends/next-dashboard/e2e/`, `@playwright/test`, `npx playwright test --reporter=line` under `timeout 900`) when the MCP tools are absent from your tool list or when several builders need to capture in parallel — it is always available, isolated, and writes PNGs to disk.
  3. **KiroCrew's Chrome Extension Mode browser** (the same Playwright MCP attached to the owner's real Chrome) — also has Playwright, so it is a valid fallback for view-only frames if 1 and 2 both fail, but it shares the owner's tabs and only one agent can hold the relay. Reserve it for owner-requested live demos on the owner's stack; never use it for unattended loop evidence.
  Say which backend produced each frame in the ledger. "No browser available" is not a blocker while option 2 exists.
- Never claim provider completion without one real streamed tool-call round trip.

## Blocker policy

A blocker is genuine only when progress on every dependency-ready roadmap item requires unavailable credentials, an owner decision, an external dependency, or repeated verified infrastructure failure. Interaction-flow capture, browser *operate* permission, visual polish, and optional tooling are deferred to M7 when feature-rail work can continue — but the one view-only render frame per new surface (Safety rails) is never deferred and never a blocker; it takes one Playwright call.

On first observation:

1. Record it in `tasks.md` and the active Bead.
2. Tell the owner once with the minimum decision or action required.
3. Continue independent work if any remains.

Do not repeat the same blocker on later cycles unless evidence changes.

## Completion contract

A milestone closes only with cited command, test, runtime, or visual evidence for every exit criterion. Narrative confidence is not evidence.
