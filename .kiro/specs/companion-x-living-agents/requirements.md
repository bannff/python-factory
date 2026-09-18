# Living Agents — Requirements

## Introduction

companion-x agents today are **invocation-scoped**: a Strands agent (or swarm/graph)
runs to completion and returns. Comparison against **MantisCore** (an internal
long-lived agent orchestrator) surfaced four capabilities companion-x lacks:

1. **Long-lived, process-grade agents** — persist across restarts, sleep/wake,
   append-only memory of every turn.
2. **Peer-to-peer comms + direct addressing** — agents message each other; the
   operator can talk to *any* agent, not just a root orchestrator.
3. **A standing self-improving agent** — a durable identity whose full-time job
   is maintaining the platform.
4. **Presence-gated tiered tool dispatch** — side-effecting tool calls are
   tier-classified and gated on operator presence, with a unified audit trail.

This feature ports those into companion-x **as domain-agnostic substrate** (North
Star #2/#3), landing in existing bricks plus one new runner primitive. The DiRT
closed-loop rule factory is the first consumer of the presence-gate + audit.

Non-goal: this is not a Mantis clone. companion-x keeps its MCP-first Polylith
shape, Strands coordination, and its learning/evals/RL edge (which Mantis lacks).

## Requirements

### Requirement 1 — Long-lived supervised agent runner

**User story:** As an operator, I want named agents to stay alive across restarts
and remember everything they've done, so I can return tomorrow to an agent that
recalls what it concluded yesterday and why.

**Acceptance criteria:**
1. WHEN a named agent is spawned THEN the system SHALL run it as a supervised loop
   (`drain inbox → invoke → run tools → persist → park`) hosted in `bases/worker`.
2. WHEN the host process restarts THEN every named agent's working history and
   status SHALL be restored from durable storage.
3. WHEN an agent completes a turn THEN the full turn SHALL be appended to an
   **append-only archive** that is never truncated or summarized.
4. WHEN an agent's working context exceeds a threshold THEN it SHALL compact
   (summarize) WITHOUT mutating the append-only archive.
5. WHEN an agent has no pending input THEN it SHALL park (sleep) and consume no
   model tokens until woken.
6. WHEN an agent is parked AND an `auto_wake_at` time passes OR a message arrives
   THEN the supervisor SHALL wake it.
7. WHERE concurrency is configured THEN the supervisor SHALL cap simultaneously
   active agents at `maxConcurrentAgents`.

### Requirement 2 — Self-written agent identity

**User story:** As an agent, I want to author my own identity (disposition,
calibration, open questions) so it persists across compaction and restarts.

**Acceptance criteria:**
1. WHEN an agent edits its identity THEN the identity SHALL persist independently
   of working history.
2. WHEN an agent's system prompt is assembled each turn THEN it SHALL include the
   current identity.
3. WHILE an agent compacts THEN identity SHALL survive unchanged.

### Requirement 3 — Peer-to-peer comms and direct addressing

**User story:** As an operator, I want to message any agent directly, and I want
agents to message each other, so collaboration isn't forced through a single root.

**Acceptance criteria:**
1. WHEN a message is sent to `agent_id` THEN it SHALL be enqueued to that agent's
   durable inbox and delivered at its next safe turn boundary.
2. WHEN a message targets a parked agent THEN delivery SHALL wake it.
3. WHEN an agent posts to a channel THEN subscribed agents SHALL receive it.
4. WHEN an agent is @-mentioned in a channel THEN it SHALL be woken even if not
   subscribed.
5. WHEN the operator surface (API/MCP base) receives `POST /agents/{id}/message`
   THEN it SHALL enqueue to that agent's inbox (not only spawn or chat-with-root).

### Requirement 4 — Presence-gated tiered tool dispatch

**User story:** As an operator, I want unattended agents to read freely but pause
real-world mutations until I'm present, so autonomous work is safe to leave running.

**Acceptance criteria:**
1. WHEN a tool call is dispatched THEN the system SHALL classify it into a tier
   (read / negative / write-bounded / write) before execution.
2. WHEN a write-tier call is dispatched AND operator presence is AWAY THEN it
   SHALL be queued (not executed) and the agent SHALL receive a `[queued]` marker
   and continue.
3. WHEN the operator returns (HERE) THEN queued calls SHALL be reviewable and
   releasable.
4. WHEN any side-effecting call is dispatched (run OR queued) THEN it SHALL be
   appended to a durable audit log with `{agent, tier, target, args_digest,
   rationale, ts}`.
5. WHERE a skill drops `shell`/`exec` THEN any tool that can reach equivalent
   side effects SHALL also be gated (no fail-open hole).

### Requirement 5 — Standing self-improving agent

**User story:** As an operator, I want a durable agent whose job is maintaining
companion-x itself, so platform improvement is continuous rather than a one-off loop.

**Acceptance criteria:**
1. WHEN the platform is provisioned THEN a seeded named agent MAY be started with
   the goal of maintaining companion-x.
2. WHEN it runs THEN its tool surface SHALL be the existing `builder` brick
   (search/edit/build/test/CR) plus a schedule.
3. WHILE it operates THEN all its write-tier actions SHALL pass through the
   Requirement 4 presence-gate (no unsupervised write access).

## Constraints

- Polylith-correct: changes land in existing bricks + `bases/worker`; the only new
  architectural primitive is the supervised runner.
- MCP-first: all new capability is reachable through the MCP boundary.
- Domain-agnostic: no security-specific assumptions in the substrate.
- Strands-native: lean on Strands `SessionManager`, conversation managers, and
  hooks rather than bespoke machinery.
