# Living Agents — Design

> Status: **APPROVED for build** (meta-architect gate + strands-expert SDK verdict,
> 2026-06-30). Both design forks are resolved in-text; all Strands API names are
> verified against the installed SDK (`.venv/.../strands/`). Remaining §9 items are
> operational, not blocking. qa-tester + security-engineer review still pending
> before code lands. See the Review Outcome appendix for verdicts.

## 1. Problem and framing

Mantis (`MantisCore`, internal) is a long-lived agent orchestrator: named agents
run as parked daemons (`drain inbox → one model call → run tools → persist →
park`), survive restarts, talk peer-to-peer over channels, and are gated by an
operator-presence + tier model. companion-x has the opposite default — Strands
agents are invocation-scoped (run-to-completion).

**Key insight (validated by review):** all four missing capabilities trace to ONE
absent primitive — a **long-lived supervised runner**. Build that, and peer comms,
direct addressing, presence-gating, and the self-improving agent are small features
layered on it. Build it in `bases/worker` (the host already exists).

What companion-x keeps that Mantis lacks: vector memory, evals, RL/reward learning
(games/learning bricks), MCP-first Polylith modularity. This design adds the
substrate they ride on; it does not touch them.

## 2. Inventory — what already exists (grounded)

- `bases/worker` — host process for long-running work (the runner's home).
- `bases/mcp_server`, `bases/api` — operator surfaces.
- `agent` brick: `registry_store_stateful`, `job_manager`,
  `multiagent_lifecycle_plugin`, `sub_agent_tool_bridge`, `chat_resume`,
  Strands graph/swarm spawn.
- `events`, `permissions`, `security`, `auth`, `telemetry`, `storage`, `memory`,
  `builder` bricks.

We extend bricks; we do not greenfield. Operational question (non-blocking): does
agent lifecycle/status live in `registry_store_stateful` or warrant its own
component? Decide during implementation.

## 3. The core primitive — supervised runner

```
┌─ worker base (one host process) ──────────────────────────┐
│  Supervisor                                                 │
│   ├ scan registry for due wakes (auto_wake_at, inbox non-empty)
│   ├ enforce maxConcurrentAgents                             │
│   └ AgentRunner × N (asyncio task each)                     │
│        loop: drain inbox → Strands agent invoke             │
│              → tool dispatch (hook-gated, §6)               │
│              → persist (session + archive)                  │
│              → compact-if-needed → park on inbox            │
└─────────────────────────────────────────────────────────────┘
```

- **One asyncio task per named agent** (matches Mantis's in-process model; accepts
  no agent-to-agent isolation — same single-tenant assumption).
- **Park** = await on the inbox queue (zero tokens while idle).
- **Status** (`active | sleeping | error`) + `auto_wake_at` persisted in the
  stateful registry; supervisor polls for due wakes.

Operational questions for implementation (non-blocking): asyncio-task-per-agent vs
worker-pool from a shared queue; backpressure/fairness at `maxConcurrentAgents`;
idempotent persist boundary so a crash mid-turn recovers cleanly.

## 4. Persistence — two tiers (Mantis's load-bearing idea)

| Layer | Purpose | Strands seam (verified) | Brick |
|---|---|---|---|
| Working history | what the model sees; compacts | `SessionManager` → `FileSessionManager` / `S3SessionManager` / `RepositorySessionManager` | `agent` + `storage` |
| Append-only archive | ground truth, never truncated; feeds `recall()` | **out-of-band** (SessionManager does NOT separate archive from working) | `storage` (`archive_append`) |
| Identity | self-written disposition; injected each turn | system-prompt assembly | `agent` |

- Compaction = `SummarizingConversationManager` (verified;
  `strands.agent.conversation_manager`) on the working history ONLY. Alternatives:
  `SlidingWindowConversationManager`, `NullConversationManager`. Archive is immutable.
- **Archive is persisted out-of-band** — confirmed by review: `SessionManager` has
  no archive/working split. Append to the archive from a `MessageAddedEvent` (and/or
  `AfterInvocationEvent`) hook, both in `strands.hooks.events`.
- `recall(query)` = `memory`/`storage` vector search over the archive — a strict
  upgrade over Mantis's keyword grep.

## 5. Peer-to-peer comms + direct addressing

**RESOLVED (both reviewers): the inbox is orthogonal to Strands Swarm/Graph — use
both.** Strands multi-agent (Swarm/Graph/Workflow/A2A/Agents-as-Tools) is
*invocation-scoped, synchronous, within-one-turn* coordination. The inbox is
*async, cross-invocation* messaging between agents that persist independently. They
compose: a standing agent MAY spawn a Strands Swarm/Graph inside a single turn. We
do not shoehorn the inbox into Swarm semantics — different time-horizons.

- **Inbox per agent** — durable queue (`events` or `storage`). Runner drains at loop
  top. This is the flip from call/return (`sub_agent_tool_bridge`) to message-passing.
- **Channels + DM** as `events` brick primitives: `post(channel)`, `read_channel`,
  `send_message(to_agent_id)`, `subscribe`, `who`. @-mention wakes a parked agent.
- **Direct addressing** — `api` + `mcp_server` bases gain
  `POST /agents/{id}/message` → enqueue to that agent's inbox. This is "the user
  talks directly to a sub-agent."
- Group discussion / adversarial pairing are LATER patterns on inbox+channels — out
  of scope here.

## 6. Presence-gated tiered tool dispatch (the novel safety bit)

Mantis's "capability broker + inject-filter" maps to a **Strands `HookProvider`**
(registration confirmed correct — register via `Agent(hooks=[provider])` or
`HookRegistry`):

- Register on **`BeforeToolCallEvent`** (verified name; `strands.hooks.events` —
  the spec's earlier `BeforeToolInvocation` was wrong). Classify the call → tier.
- **The gate seam is `BeforeToolCallEvent.cancel_tool`** (writable `bool | str`):
  set it to a `[queued: id]` reason string to block/queue the call without executing
  it. Cleaner than intercept-and-reroute. Matching after-event: `AfterToolCallEvent`.
- Read operator presence (HERE/AWAY) from `config`/`events`. write-tier + AWAY →
  set `cancel_tool`, enqueue to a "queued probes" store; HERE → run.
- Every side-effecting call (run or queued) → audit append via `telemetry`/`logger`.

**RESOLVED (meta-architect): tier is manifest-resolved, NOT agent-declared, from day
one.** Each tool's tier comes from a per-tool manifest, not the agent's word.
Rationale: DiRT submits real SAST rules to production scanners — self-declared tier
(Mantis's honest-but-imperfect model) is unacceptable here. This is a place
companion-x deliberately beats Mantis.

Tier taxonomy: `read` (own/public read), `negative` (live request with fabricated
IDs, designed to fail), `write-bounded`, `write`.

Guard against the fail-open trap (Mantis §15): a skill that drops `shell` but keeps
a JS/eval/MCP-invoke tool reaching equivalent side effects. Manifest-resolved tiers
close this by construction — the gate keys on the resolved tier of the *actual*
tool, not a self-declaration.

## 7. Self-improving standing agent

No new brick. A seeded named agent: goal = "maintain companion-x," tools = `builder`
brick + schedule, all writes through the §6 gate. The existing goal-loop nudge
daemon is absorbed — it becomes one standing agent with durable identity + memory.

Hard dependency: MUST NOT start until §3 (runner) and §6 (gate) exist, or it is an
unsupervised long-lived agent with write access and no presence brake.

## 8. Sequencing

`#1 runner → #2 identity → #3 comms → #6 gate → #7 self-improving agent`
(meta-architect: "the only valid topological order"). Each is independently
shippable and testable. The DiRT closed-loop consumes #6.

## 9. Open items (operational, non-blocking)

1. asyncio-task-per-agent scaling and fairness at `maxConcurrentAgents`.
2. Idempotent persist boundary for crash recovery mid-turn.
3. Standing-inbox lifecycle could reuse the `AfterInvocationEvent.resume` hook for
   the inner turn loop, but supervisor/park stays bespoke — confirm during build.
4. Single-tenant / no agent-to-agent isolation — accepted (matches Mantis).
5. Token-cost of N parked agents waking on schedule — need a budget/quiesce story.

(Resolved during review and removed from this list: inbox-vs-Swarm overlap →
orthogonal; declared-vs-manifest tier → manifest; Strands API names → verified.)

## 10. Out of scope

Cross-instance federation (Mantis's "Speakeasy"), group-discussion/pairing patterns,
bespoke operator UI. Tracked separately if pursued.

## Appendix — Review outcome (2026-06-30)

**meta-architect: APPROVED with changes.** Core thesis sound ("the right
decomposition, NOT an oversimplification"); use case is "substrate, not
gold-plating"; Polylith-coherent; persistence and sequencing correct. Forced two
decisions: inbox/Swarm orthogonal (use both); manifest-resolved tier from day one.

**strands-expert: IDIOMATIC.** Confirmed the parked-inbox runner does NOT reinvent
Strands (Swarm/Graph/A2A/Workflow/Agents-as-Tools are all invocation-scoped).
Verified API names against the installed SDK:

| Earlier spec name | Correct | Import |
|---|---|---|
| `BeforeToolInvocation` | `BeforeToolCallEvent` (has `cancel_tool`) | `strands.hooks.events` |
| `AfterInvocation` | `AfterInvocationEvent` | `strands.hooks.events` |
| `MessageAdded` | `MessageAddedEvent` | `strands.hooks.events` |
| `SummarizingConversationManager` | ✓ correct | `strands.agent.conversation_manager` |
| `SessionManager` / `HookProvider` / `HookRegistry` | ✓ correct | `strands.session.*` / `strands.hooks.*` |
