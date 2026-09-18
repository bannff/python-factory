# M3 Design — Durable Scheduler

**Epic:** `python-factory-bp34j`  
**Milestone:** M3 — Scheduler: cron and one-shot jobs  
**Research:** upstream contract `32c2987e`; Factory gap map `be012dbc`  
**Pre-implementation review:** `3eb70d82` — APPROVE_WITH_NOTES

## Goal

Companion-X can persist interval, one-shot, and cron schedules. Scheduler owns when work is due; Agent owns execution; Workflow owns each durable attempt. A due fire survives restart and enrolls exactly one Workflow run.

Final schedule-page UX and visual acceptance remain M7 work.

## Upstream behavior to preserve

- exactly one schedule kind: interval, one-shot, or five-field cron
- minimum recurring interval of 60 seconds
- IANA timezone and strict local `YYYY-MM-DD` skip dates
- explicit user pause separate from execution-driven auto-pause
- no overlap for one schedule
- deterministic same-minute cron and per-fire duplicate suppression
- one-shot disables after its first admitted fire
- five consecutive execution failures auto-pause; success resets failures
- restart recovers due and in-flight fires without duplicate work
- fire-time denial or resource saturation is not counted as execution failure

## Existing Factory rails

- **Storage SQLStore** supplies durable SQL execution; Session is the owner-scoped/CAS exemplar.
- **Agent `spawn_background`** already validates the origin Session/persona, freezes deterministic launch identity, and enrolls Workflow.
- **Workflow** already owns run idempotency, attempts, retry, cancellation, recovery, and terminal truth.
- **API BackgroundTaskOwner** already owns bounded asyncio task lifetime and startup activation.
- **Events/Notification** provide observability and alerts, never schedule truth.

The old worker sleep loop and KiroCrew JSON/file-lock engine are not reused.

## Ownership

### Scheduler brick

Owns only:

- schedule specification and lifecycle
- next-fire calculation
- durable fire sequence/claim
- due scanning and overlap exclusion
- pause/resume/remove
- failure count and auto-pause

It does not execute models, retry work, or own Workflow status.

### Agent and Workflow

Scheduler invokes the public operational Agent background-launch tool through caller-bound MCP with the stored verified envelope. Agent uses a deterministic `launch_id` derived from `(schedule_id, fire_sequence)`. Existing Agent→Workflow enrollment then guarantees replay returns the same run.

No new Workflow service caller or binding is needed.

## Models

`ScheduleRecord`:

- owner-scoped `tenant_id`, `owner_id`, `schedule_id`
- verified `origin_session_id`, `origin_thread_id`
- `agent_id`, bounded task
- kind: `interval | one_shot | cron`
- exactly one of interval seconds, one-shot UTC timestamp, cron expression
- timezone, skip dates, strict-schedule flag
- state: `active | paused | auto_paused | completed`
- `next_fire_at`, `last_fire_at`, `fire_sequence`
- `consecutive_failures`, revision, timestamps

`FireRecord`:

- owner/schedule/fire sequence identity
- deterministic `launch_id`
- state: `claimed | enrolled | failed`
- Workflow run ID when enrolled
- created/updated timestamps and revision
- DB uniqueness `(tenant_id, owner_id, schedule_id, fire_sequence)`

## Exactly-once fire protocol

1. Due scan revision-CAS claims the next fire and increments its sequence.
2. Claim persists before any cross-brick call.
3. Scheduler invokes `agent_spawn_background` through MCP with deterministic `launch_id=sched_<schedule-id>_<sequence>` and the stored origin envelope.
4. Agent/Workflow replay with the same launch ID returns the same Workflow run.
5. Scheduler stores the returned run ID and advances `next_fire_at` with revision CAS.
6. Crash after claim or enrollment leaves a recoverable claimed fire; startup replays the same launch ID.
7. A schedule with a claimed nonterminal fire cannot overlap itself.

## MCP surface

Strict brick-local Pydantic v2 ingress and typed `ToolResult` egress.

Deterministic:

- `scheduler_get`
- `scheduler_list`
- `scheduler_get_fire`

Operational:

- `scheduler_add`
- `scheduler_pause`
- `scheduler_resume`
- `scheduler_remove`
- `scheduler_trigger`

No authoring tools are needed.

## Runtime activation

The Scheduler brick registers one in-process due-scan service. API lifespan lazy-loads Scheduler and owns one periodic asyncio loop. The loop asks Scheduler for the next bounded batch and sleeps until the next due time or a short maximum poll interval. Shutdown cancels it deterministically.

Scheduler cross-brick calls use caller-bound MCP; in-process service registration is only the composition seam for timer ownership.

## Implementation slices

1. Scaffold Scheduler brick; strict models; SQLStore schedule/fire persistence; interval and one-shot validation/lifecycle with Hypothesis state machine.
2. Exactly-once claim/replay through `agent_spawn_background`; startup recovery of claimed fires.
3. API-owned recurring due loop; pause/resume/trigger and failure/auto-pause behavior.
4. Five-field cron calculation, timezone, skip dates, strict scheduling, and bounded next-run search.
5. Events/Notification integration; final UX deferred to M7.

## First-slice acceptance

- canonical compliant Scheduler brick, no monolith
- owner-scoped SQL tables and DB fire uniqueness
- strict schedule-kind exclusivity and 60-second interval floor
- revision-fenced add/pause/resume/remove lifecycle
- one-shot and interval next-fire calculation survives runtime reconstruction
- Hypothesis covers lifecycle/CAS/fire-sequence invariants
- no model execution or Workflow lifecycle in Scheduler
- files under 200 lines; targeted tests and Guardian pass
