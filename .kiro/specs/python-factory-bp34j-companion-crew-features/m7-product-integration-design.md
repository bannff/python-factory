# M7 Design — Product Integration, Import, and Tier-1 Acceptance

**Epic:** `python-factory-bp34j`  
**Milestone:** M7 — unified Companion-X UX, KiroCrew data import, and Gate C

## Goal

Finish the daily-driver experiment without creating another agent runtime or a
KiroCrew mega-component. Companion-X gains a safe one-shot import, durable
notification inbox and typed deep links, direct UI/chat parity for Sessions,
Schedules, Lessons, Artifacts, and Crews, then one evidence-driven Gate C sweep.

## Audited truth and scope

Existing backend rails already satisfy provider chat, durable Sessions,
background subagents, Scheduler, goal loops, Lessons, Artifacts, Devtools,
Crews, and model routing. Artifacts/Crews/Terminal already have accepted visual
evidence and are not redesigned. Missing product paths are Schedule, Lessons,
direct Session navigation, durable notifications/deep links, import, and a
unified acceptance recipe.

KiroCrew's canonical onboarding importer explicitly excludes `sessions/*.jsonl`.
M7 imports semantic/episodic memory, typed lessons, disabled schedules, and
supported markdown memory. It does not fabricate LangGraph checkpoints from
foreign transcripts. Session history, skills, MCP servers, workspaces, config,
and runtime/secret state are out of import scope.

## Ownership

- **Migration (new focused brick):** source discovery, trusted temp snapshot,
  `kirocrew-v1` parsing, immutable import plan, per-record receipts/reporting.
  It is a deterministic capability, not a runtime or control plane.
- **Workflow:** durable import attempt, cancellation, retry, terminal reason,
  restart, and page progression through existing attempt/checkpoint idempotency.
- **Memory/Lessons/Scheduler:** validate and persist their own imported records
  through protected typed MCP; Migration never imports their runtimes.
- **Notification:** durable owner-scoped inbox state plus delivery adapters.
- **Session:** remains Session metadata/history authority; no transcript import.
- **Companion-X:** Settings import flow, missing views/routes, notification bell,
  deep-link rendering, and CopilotKit navigation tools.
- **Agent:** conversational composition only; it starts typed operations and
  navigates UI but owns no import or inbox state.

## KiroCrew source adapter

`kirocrew-v1` resolves only operator-configured `KIROCREW_IMPORT_ROOT`; public
inputs accept no path and default disabled. Enumerate and stage only the relative
paths listed below—no secret, model, log, upload, session, or unknown file is ever
opened or copied. `lstat` every component, open leaves with `O_NOFOLLOW`, reject
links/devices/sockets/owner mismatch, and use descriptor `fstat` for type, size,
and mutation checks. Caps (500 files, 8 MiB each, 64 MiB DB) apply only to this
allowlist; parsing uses the trusted temp copy. Bind snapshot/adapter digests.

Accepted sources:

- `memory.db` schema v1–3: use SQLite online backup from a read-only source so
  committed WAL rows are included; plain copy plus `immutable=1` is forbidden.
  Integrity-check the standalone snapshot, then read live semantic/episodic rows
  only—no embeddings, FTS/FAISS, events, or deleted rows. Kind fails on corruption.
- `lessons.jsonl`: `{ts, rule, category, negative, repo_scope}` with per-line
  isolation; legacy semantic `lesson.*` rows are deduplicated against JSONL.
- `crons.json` or canonical `cron/jobs.json` v2: safe fields only; imported
  schedules are atomically disabled/paused.
- `workspace/memory/{preferences.md,projects.md,history/*.md}` under the same
  size/injection controls, deduplicated against SQLite memory.

Never read/import `.local_secret`, signing/HMAC keys, telemetry salt, vault or
webhook stores, cron `secret_env*`, command/script payloads, runtime result/error
fields, managed MCP config, persona identity paragraphs, or session transcripts.
Unknown schema versions fail the kind, not the whole snapshot; malformed records
produce bounded typed diagnostics without raw content.

## Import contracts and durability

Migration exposes strict typed tools:

- `migration_preview(source="kirocrew-v1", kinds=...)` (`@operational`, read-only)
  creates/deletes a temp snapshot but no target writes; returns plan digest and
  per-kind found/eligible/
  excluded counts, bounded reason codes, and redacted samples.
- `migration_start(plan_digest, kinds=...)` (`@operational`) enrolls one Workflow
  attempt and returns `run_id`; exact replay returns the same attempt.
- `migration_get(run_id)` (`@deterministic`) returns per-kind imported/skipped/
  failed counts, page cursor, terminal reason, and no source content.
- `migration_apply_page` is service-only from Workflow and requires exact
  snapshot/plan/page binding. Pages are bounded and receipt-CAS committed only
  after every target call has a typed terminal result. A Workflow-native
  continuation outcome re-drives successful partial pages without consuming the
  separate genuine-failure retry budget; both paths remain explicitly capped.

Migration receipts reuse public Storage SQLStore with `(tenant, owner, adapter,
source_fingerprint, kind, source_record_id)` uniqueness. Target idempotency keys derive
from source-record identity, while target digest detects edited-source conflicts.
Exact replay skips; changed material creates a plan; partial runs resume through
Workflow checkpoints and committed receipts. Imports are merge-only.

Target-owned protected tools:

- Memory reuses its structural `global` partition and existing metadata/tag
  semantics; source-identity idempotency prevents duplicates and embeddings rebuild.
- Lessons accepts only Migration-bound user-authored records as `accepted`, uses
  exact normalized identity, and merge-enriches without semantic “newer wins”
  deletion.
- Scheduler creates the exact supported interval/one-shot/cron shape atomically
  in paused state; it never briefly schedules imported work. Unsupported command,
  script, secret, or malformed jobs are excluded.

All service calls use `tool_invoker_for_caller`, strict Pydantic v2 ingress,
typed `ToolResult` egress, and ambient tenant/owner authority. No direct
cross-brick runtime imports.

## Durable notifications and deep links

Extend Notification with owner-scoped `NotificationRecord` over public Storage
SQLStore: id, kind, title, credential/PII-redacted bounded body, priority,
target union, created/read timestamps, revision, and dedupe key. Persist inbox truth before best-effort
channel delivery. Add typed list/get/mark-read/mark-all-read tools with revision
fencing; foreign/not-found remain opaque.

Targets are a closed union: Session, Workflow run, Schedule, Artifact, Crew,
Lesson, or Canvas view. Each target carries only its canonical ID. The frontend
resolves it to internal routes; arbitrary/external URLs are forbidden. Opening a
target rechecks ambient authority against its source brick—an inbox ID grants no
access; stale/foreign targets are opaque not-found. Producers publish only after
source commit. Delivery failure cannot erase inbox truth.

## Selected visual specification (owner, cycle 174)

Option A is authoritative: preserve the existing 48px rail and accepted Artifacts/Crews galleries; add divider-grouped destinations with labeled tooltips, a compact topbar inbox popover, and one Settings canvas page with exactly General / Import / Providers tabs. Mobile uses labeled sheets. No further mockup round is required.

## Product UX and CopilotKit parity

Before visual code, present 2–3 token-native mockups covering grouped Operations
navigation, topbar notification inbox, and Settings import preview/report. Separate
operations from the security canvas; additions must not relocate/restyle accepted
Artifacts/Crews entries. The owner-selected mockup is the visual spec. Surfaces:

- Sessions route/deep link backed by the existing Session Deck and history.
- Schedules list/detail with paused/active/next-fire and lifecycle actions.
- Lessons list/detail with status/scope/source and curation actions.
- Topbar bell/inbox: named keyboard-operable control, polite unread live region,
  and plain actions such as “Open the schedule that fired,” never IDs.
- Settings import preview/confirm/progress/report; no raw path/secret. Explain
  “adds missing items; never overwrites/deletes,” friendly counts/reasons, replay as
  “Already imported—nothing to redo,” and source-disabled setup guidance.

Add Canvas IDs/routes and `fe_navigate_canvas` parity. Focused frontend tools may
navigate exact session/schedule/lesson/notification targets; mutations remain
backend MCP and retain CAS/HITL semantics. Loading, empty, error, partial/retry,
unauthorized, source-disabled, and deleted-target (“This item no longer exists”)
states are truthful; raw reason codes never render. New icon controls need accessible
names/`aria-current`; progress/unread use polite live regions; deep links focus the
target heading.

## Acceptance and security tests

- Hypothesis: source path/record grammar, size/count bounds, receipt replay,
  partial-page restart, lesson merge identity, paused schedule import, inbox CAS,
  deep-link target union, and owner isolation.
- Adversarial fixtures include symlink/hardlink escape, dirty-WAL mutation, corrupt SQLite,
  malformed JSONL, unknown versions, injection text, credential shapes,
  duplicate lessons, deleted memory, secret cron fields, and foreign authority.
- Preview causes zero target writes; execute twice produces identical targets and
  all skips on replay; interruption resumes without duplicate writes.
- Temp-copy source remains byte-identical; cleanup is bounded and cannot touch
  the original KiroCrew home.
- Import report gives exact per-kind counts and digest-bound redacted spot checks.

## Gate C evidence

Run one isolated 18000/13000 recipe covering import preview/execute/replay,
Session→Schedule→Workflow/loop→Lesson→Artifact→Notification deep link, and an
OpenRouter streamed tool call. Restart and verify Sessions, subagents, schedules,
goals, lessons, artifacts, Crews, import receipts, and inbox state. Load every
MCP-backed tab with zero 401 and truthful errors.

Capture static desktop/mobile frames for each new surface. Record GIF/video for
session switching/steering, subagent completion, schedule fire, goal-loop advance,
notification deep-link navigation, and import preview→completion. Run a separate
brand-new non-technical unified-cockpit review and apply legitimate findings.

## Slices

1. Scaffold Migration with split snapshot/per-kind parser/receipt adapters, preview,
   and receipts; immediate Gate A.5 for the new brick/persistence boundary.
2. Protected Memory/Lessons/Scheduler import tools plus Workflow attempt/restart.
3. Notification inbox persistence, typed targets, producer projection.
4. Owner-selected Operations mockup; Sessions/Schedules/Lessons/Notifications UI,
   routes, responsive render evidence, and CopilotKit navigation.
5. Settings import UI/chat path and composed import/restart acceptance.
6. Unified Gate C recipe, recordings/responsive frames, new-user review, Gate 0/B/C.

Deferred: foreign session transcript activation, skills/MCP/workspace/config import,
overwrite/rollback import, external notification URLs, public deployment, voice,
computer use, and Memory/KB/Graph consolidation.
