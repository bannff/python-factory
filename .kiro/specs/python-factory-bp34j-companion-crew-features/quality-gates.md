# Companion-X Crew Features — Quality Gates

## Principle

The building agent owns fast feedback inside a milestone. Independent agents audit periodically and at milestone seams. Do not block every small task on an external reviewer.

Reviews exist at three altitudes. Gate A.5 and Gate B ask "did this work do what it claims, on the rails?" Gate 0 asks "is the plan still the right plan, and are the docs feeding the loop still true?" The 2026-09-11 program audit found a missing worker capability (developer tools) and a steering doc describing a retired runtime — both invisible to A.5/B because those gates only judge the active slice against the active milestone.

## Gate 0 — Program-fidelity review

Trigger: at every milestone seam (run alongside Gate B), whenever `roadmap.md` or `north_star.md` changes, and whenever a slice touches a steering or README file.

Dispatch exactly one **meta-architect** — as `spawn_run(agent="compx-auditor")`, the fable-5 read-only auditor persona; never the builder's own persona. It reads `north_star.md`, `roadmap.md`, the KiroCrew upstream feature inventory (sidebar, settings, agent capabilities, chat footer), the repo steering docs, and the current code, and must answer:

1. Does every numbered user outcome in `north_star.md` map to at least one roadmap milestone with an exit criterion? List any outcome with no home.
2. Does the KiroCrew upstream expose a user-visible capability that the roadmap neither ports nor explicitly defers? Answer from `kirocrew-feature-map.md`, not memory: run `scripts/feature_map_status.py` and report the row counts per Status (`TODO`/`MISSING`/`PRESENT+BROKEN`/`PRESENT+WORKS`/`OWNER_NA`/`OWNER_DEFERRED`/`OWNER_REBRAND`) and list every in-scope non-green row. `OWNER_*` rows are out of M7.5 scope by owner ruling; do not re-litigate them. If the upstream clone is ahead of the generated commit, regenerate first.
3. Would a user who finishes every roadmap milestone be able to do the stated goal (day-to-day development from Companion-X)? If not, name the missing dependency.
4. Do the steering docs, project README, and `LOOP-GUIDE.md` describe the runtime, frameworks, and ownership that the code actually uses? Cite any file/line that contradicts the code.
5. Is any milestone carrying work that belongs to a different owner (brick) or a different altitude (debt filed as "later" that breaks the product today)?
6. Redundancy audit: cite (file:line) any dead code path, broken adapter, duplicate capability, unbounded data growth, or doc that describes a retired direction. Multiple working adapters per brick are **not** a finding — they are deliberate project-composer options.

Verdict: `ON_PLAN`, `AMEND_PLAN` (with the exact roadmap/north-star/steering edits required), or `HALT` (goal is unreachable as written). `AMEND_PLAN` edits are applied before the next implementation slice begins and are recorded in `tasks.md` as a program-review row.

## Gate A.5 — Periodic fidelity checkpoint

Trigger after three implementation slices since the last independent review, or immediately when a slice introduces a new brick, framework seam, persistence model, or orchestration path.

Dispatch exactly one rotating reviewer:

- **Meta-architect** for ownership, architecture, framework use, or scope questions.
- **QA reviewer** for behavior, contracts, state transitions, and test-quality questions.

The reviewer reads `north_star.md`, `roadmap.md`, `tasks.md`, `quality-gates.md`, the current diff, and validation evidence. It must answer:

1. Does the work directly advance the active milestone?
2. Did it reuse framework primitives and existing factory rails before adding code?
3. Is any bespoke abstraction, duplicate capability, or premature generalization present?
4. Do MCP taxonomy, strict ingress, typed egress, Polylith ownership, and file-size rules hold?
5. Is the evidence strong enough to continue?
6. Did the slice change behavior that any steering doc, README, or design doc describes? If so, was that doc updated in the same slice?

Record the verdict and reset the slice counter. A `BLOCK` pauses implementation until corrected; `PASS_WITH_NITS` creates Beads only for substantive follow-ups.

## Gate A — Slice gate

Run after each coherent code slice before advancing `tasks.md`.

Required checks are scoped to changed behavior:

- Targeted `pytest` for affected Python packages.
- Existing contract tests for every changed MCP surface.
- Pydantic strictness tests for ingress/egress changes.
- Hypothesis properties for stateful CRUD, transitions, scheduling, retries, and deduplication.
- Ruff on changed Python packages.
- Configured Python type checker on affected packages when available; the repository currently configures mypy, not Pyright.
- Frontend unit tests, lint, and TypeScript checks for changed Companion-X code.
- Visual verification for user-visible UI changes: one view-only render screenshot per new or changed surface, captured in the same slice (LOOP-GUIDE Safety rails). Interaction flows and polish remain M7.

The builder may fix Gate A failures directly. No independent subagent is required.

## Gate B — Milestone seam

Run once when every task and exit criterion in a milestone appears complete.

**Feature handoff:** after each complete KiroCrew feature port, send the diff and evidence to a meta-architect for a one-line factory-rails verdict before closing its Bead: `PASS`, `PASS_WITH_NITS`, or `BLOCK`.

Dispatch independent reviews in parallel:

0. **Gate 0 program-fidelity review** (see above) — runs at every milestone seam.
1. **QA reviewer** — verifies acceptance criteria, test quality, edge cases, Pydantic contracts, Hypothesis coverage, and regression evidence.
2. **Meta-architect** — verifies Polylith ownership, MCP taxonomy, strict ingress/typed egress, SDK-first design, no cross-brick internals, and files under 200 lines.
3. **Triggered specialist only when applicable:**
   - SDK/model integration → framework SDK expert.
   - Auth, secrets, paths, network, or tenant boundaries → security reviewer.
   - User-visible workflow or layout → UX reviewer with real screenshots.

Verdicts:

- `PASS` — milestone may close.
- `PASS_WITH_NITS` — milestone may close; create Beads for substantive follow-ups.
- `BLOCK` — fix findings and re-run only the failed review scope.

Do not repeatedly audit unchanged work. Do not audit documentation-only microtasks.

## Gate C — Tier-1 release seam

Run before Track B halts or a review-ready change is prepared:

- All milestone Gate B verdicts recorded.
- `foreman_guardian_check` with no new violations.
- Broad affected-package pytest suite.
- Frontend lint, type checks, and tests.
- Cross-capability E2E recipe.
- Real OpenRouter streamed tool-call proof.
- Restart/recovery proof for sessions, subagents, schedules, goals, lessons, and artifacts.
- Visual proof of every new Companion-X surface.
- Existing Memory and KB regressions remain green.

## Trigger rules

Consult before implementation when repository rules require it:

- New brick, adapter, event schema, or Pydantic contract → meta-architect.
- SDK integration → relevant SDK expert.
- Security-sensitive boundary → security reviewer.
- Significant UI change → UX design workflow.

These design consults do not replace Gate B's independent verification.

## Ledger format

`tasks.md` records only concise evidence:

```text
Slice: LOCAL_GREEN — tests/lint/types
Milestone: AUDIT_PENDING | PASS | PASS_WITH_NITS | BLOCK
Program review: ON_PLAN | AMEND_PLAN | HALT — <review-id>
Review IDs: <qa-id>, <architect-id>, <specialist-id if applicable>
Evidence: exact commands and artifacts
```

The cycle log keeps a rolling window of the most recent 15 cycles. Older rows move to `tasks-archive.md` in the same directory at every milestone seam. The loop reads `tasks.md`, never the archive, unless a cycle explicitly needs history.
