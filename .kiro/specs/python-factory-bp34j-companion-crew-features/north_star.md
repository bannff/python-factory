# Companion-X Crew Features — North Star

**Epic:** `python-factory-bp34j`

## Goal

Bring KiroCrew's best product capabilities into Companion-X using Python Factory's existing Polylith, MCP, Workflow, Agent, Storage, Memory, Learning, Notification, and CopilotKit v2 rails — so the owner can do day-to-day software development from Companion-X instead of KiroCrew, on any model provider.

The result should feel like Companion-X gained durable autonomous operations—not like KiroCrew was embedded inside it.

## User outcome

From Companion-X, a user can:

1. Chat through a provider-neutral agent using OpenRouter — or any OpenAI-compatible endpoint (opencode, Ollama, LM Studio, vLLM) — without `kiro-cli` or Bedrock lock-in.
2. Create, switch, resume, and manage persistent agent sessions.
3. Send guidance while an agent is working and have it enter the active conversation; if immediate steering is unavailable, queue it exactly once without loss or duplication.
4. Launch background subagents and observe, steer, cancel, and resume their work.
5. Schedule recurring or one-shot work conversationally.
6. Run bounded goal and monitor loops with explicit stopping conditions.
7. Store and recall typed lessons learned from feedback and outcomes.
8. Save, version, organize, comment on, and revisit artifacts.
9. Receive useful in-app notifications and navigate directly to relevant work.
10. Drive all of these capabilities through CopilotKit v2 frontend tools and dashboard pages.
11. **Do real development:** the agent reads, edits, and searches files, runs bounded shell commands and tests, and uses git — all confined to a scoped project directory, with output visible in a Terminal panel.
12. Define crews (persona + project workspace + memory store + model) and pick the model/provider per session from the UI.
13. Import existing KiroCrew memory, lessons, and schedules so nothing is lost in the switch.

## Non-negotiable decisions

- Track A (`crew-rs`) is independent and untouched.
- Track B remains Python; ADK is out of scope.
- Do not use `kiro-cli` for model execution.
- The agent runtime is LangChain/LangGraph on MCP v2. Strands was retired because it lacks MCP v2 support (stateless transport, MRTR-style workflow benefits). Do not reintroduce it or cite its primitives as the SDK-first baseline.
- `llm_gateway` resolves provider configuration; framework-native model clients retain streaming and tool behavior.
- CopilotKit v2 remains the chat/page-control rail.
- Do not create a monolithic KiroCrew component.
- Each capability follows factory conventions and exposes typed MCP contracts.
- Every new brick follows the existing compliant anatomy: `BRICK.yaml`, `runtime/ports.py`, adapters, `mcp/`, and `interface.py`.
- Every MCP operation is classified as `deterministic`, `operational`, or `authoring`, with strict brick-local Pydantic ingress (`extra="forbid"`) and typed `ToolResult[OutputDTO]` egress.
- Workflow owns durable attempts, retries, cancellation, recovery, and stopping.
- Agent owns intelligent work and bounded within-attempt composition.
- **Agent autonomy (owner ruling 2026-09-14 12:00):** agents do NOT ask the owner for approval by default. The Developer persona keeps its 13 Devtools tools (read/search/list, write/edit, allowlisted run/cancel, git status/diff/log, git stage/commit/push) and runs them unattended against the owner's own repositories; git push stays default-off behind its authoring gate and protected-branch policy. This grant is attributed to **M2.5 Developer tools** and ships in the single consolidated commit with the rest of the migration — never a separate commit, never a revert.
- **Approval is ONE simple list, not a tiered system (owner ruling 2026-09-14 12:00):** Companion-X already has an approval mechanism — the LangGraph interrupt mapped through `components/ui/.../ag_ui_mapper_chat_interrupt.py` to the chat `approval-card.tsx`. Reuse it: a single owner-editable list of tool names (Settings → Security; empty by default) routes through that card; anything not on the list executes. Do not build approval levels, risk tiers, per-persona matrices, or a second approval UI. A security reviewer may recommend additions to the list; it may not reintroduce prompts by default.
- **Real terminal, real commands — no bounding (owner ruling 2026-09-14 15:39):** "i need a real terminal, not some bounded bullshit. This is a local machine app, running and employed by me - i need these agents to do what i need to do. Thats what kirocrew gives, not some gimped version. I dont need some over-securitied BS feature, i need it straight." Therefore: (a) the Terminal dock is a **real interactive PTY shell** (owner's login shell, arbitrary stdin, tabs, default-shell picker, font, completion) — the same contract as KiroCrew's terminal; (b) the agents' command tool runs **any command** — the `command_policy.py` closed allowlist and the `--watch/--serve/interactive` denials are **removed**, not relaxed; (c) agents may read from and type into the terminal; (d) the ONLY gate anywhere is the single approval list (empty by default). Security reviewers may recommend additions to that list and must not reintroduce allowlists, sandboxes, "bounded" runners, or confirmation prompts. Any ledger row or review that uses the word "bounded" for a command surface is a defect against this ruling.
- **Unified graph memory (owner ruling 2026-09-15 06:25):** "i never 'deferred' unified graph for memory + memory, that's what i wanted that rust did well (rust used overgraph)… i just want them to have 1 target which is networkx. I think before they were both chromadb which isn't a graph. The point is to have a graph for memory/kb because… the agents accessing it get more power because everything is related. the trick is to have some embedding model (either super light on the machine like kirocrew does or elsewhere) to constantly make/update connections." Therefore: Memory and KB write to ONE persistent networkx graph (the `graph` brick) as new `graph` adapters on the existing `MemoryStore`/`VectorStore` ports; the graph holds chunks and relationships while large payloads live in Storage by reference; a light local embedder — **Qwen3-Embedding-0.6B GGUF in-process via llama.cpp, exactly as KiroCrew ships it** (tiny Ollama embedding model as the alternate; never inference) — continuously creates/updates similarity edges; agents recall by graph traversal; and the KiroCrew-style Memory/KB UI reads that graph. ChromaDB is not the target for either. This is roadmap **M7.7**, not "deferred" — any doc that still says deferred is wrong. **Scoping ruling (owner 2026-09-16 06:33):** ONE memory store, scoped by labels — never a store per agent. Every memory node carries `agent` (persona id), `scope` (`private`|`shared`), `source`, `confidence`, timestamps; default recall = own scope + shared, swarms may widen. This is the namespace model LangGraph Store, Mem0 (`agent_id`/`user_id`) and Letta shared blocks all use, and the only design that fits one graph. KiroCrew "members" map to persona scopes and "Global Memory" to `scope:shared`, on the tags/metadata filters the memory brick already has — rows 44/45 are a UI filter, not new stores. Memories are replaced by the curator (A-MEM evolution, later the similarity job), never by the owner: keep the previous version as a `superseded_by` edge and show history on the memory detail; no separate "replaced" list, no restore button (row 47).
- **One Terminal surface (owner ruling 2026-09-15 05:54):** Companion-X exposes exactly one Terminal: the global bottom dock. Do not add or restore a second per-chat/chat-sidebar Terminal, per-chat terminal tabs, or chat-scoped terminal state. The bottom dock owns all shells and tabs.
- **ONE memory store, scoped by labels — never a store per agent/persona (owner ruling 2026-09-16 06:32):** every memory node carries `agent` (persona id), `scope` (`private`|`shared`), `source`, `confidence`, `timestamps`, on the existing single M7.7 graph — not a separate store per member. Default recall = own scope + shared; swarms may explicitly widen. This matches how LangGraph Store namespaces, Mem0's `agent_id`/`user_id`, and Letta's shared blocks all work, and is the only design that fits M7.7's single graph. Rows 44/45 (KiroCrew "Store picker"/"Member memory") are therefore reframed as **"expose the scope filter in the Memory UI"** (member = persona; Global = `scope:shared`) on the tags/metadata filters that already exist on `MemoryQuery` (`components/memory/.../runtime/models.py`) — NOT new stores, NOT a picker between separate backends. Row 47 ("Replaced experiences"): the curator (A-MEM evolution today, the similarity job later) is what replaces memories, not a user action — keep old versions as a `superseded_by` edge in the graph and show history on the memory detail view; no separate replaced-items list, no restore button. Build on the graph backend only, `spawn_run(agent="compx-auditor")` review required before flipping any row's status, post one smoke note after. WakaTime (row 53) is **OWNER_NA/deferred** — owner does not use it and will not pay for the API key; do not build it, do not re-ask.
- Scheduler owns time only.
- Storage owns persistence primitives; Artifacts owns artifact semantics.
- Developer tools (file, shell, git) are typed MCP operations confined to a scoped project root; `run_command` is bounded and streams; git mutations (stage, commit, push) and destructive git are `@authoring`—operator-gated and never agent-self-approved.
- Crews are data (persona + workspace + memory store + model), never a parallel runtime.
- Existing Memory and KB remain functional throughout; their consolidation onto the one graph is **M7.7** (see Non-negotiables). A relationship-graph *projection* over them (M5.5) was a stepping stone, not the consolidation.
- Multiple adapters per brick are a feature, not debris: project composers choose backends. Never remove or collapse adapters in this program; hygiene targets dead, broken, or duplicate-capability code only.
- No domain-specific orchestration branches.

## Architecture pattern

```text
Capability brick → typed MCP contract → Companion-X API/AG-UI → dashboard page
                                              ↑
                                    CopilotKit frontend tools
```

## Tier-1 definition of done

Track B is a usable daily-driver experiment when:

- OpenRouter completes a real streaming chat turn and typed MCP tool call.
- Sessions survive process restart.
- A background subagent survives/reconciles restart and reports completion to its origin session.
- A scheduled job fires exactly once into a durable Workflow attempt.
- A goal loop advances work across cycles and halts on its stop file.
- A typed lesson is created from feedback and recalled on a later turn.
- An artifact is saved, versioned, listed, and reopened.
- Through chat alone, the agent edits a file in a scoped project, runs its tests in the Terminal panel, and shows a git diff; a path outside the project root is refused.
- A crew bound to a model other than the session default (any already-proven provider: OpenRouter or Ollama) completes a streamed tool-call turn. Non-OpenRouter OpenAI-compatible endpoints are supported in code; live proof waits until the owner adds one.
- Companion-X exposes coherent Sessions, Schedule, Lessons, Artifacts, Crews, Terminal, and activity UX.
- Every capability is operable through chat as well as direct UI.
- Existing Memory, KB, and current Companion-X views still pass regression checks, with no MCP 401 on any tab.

## Quality bar

- SDK-first and framework-native before bespoke code.
- Files remain under 200 lines.
- Stateful capabilities include Hypothesis properties.
- Existing tests run before implementation; targeted tests and Guardian run after changes.
- After every three implementation slices, one rotating QA or meta-architect reviewer checks goal fidelity, framework reuse, simplicity, and evidence; both review every milestone closure.
- At every milestone seam, a **program-fidelity review** (Gate 0 in `quality-gates.md`) checks that the roadmap still covers every user outcome above and that the steering docs match the code.
- No silent fallback that makes an unavailable capability appear healthy.
- Evidence, not narrative confidence, closes milestones.

## Halt condition

The loop halts when all milestone exit criteria in `roadmap.md` are proven, or immediately when `.stop-companion-crew-features` exists at the root of the normal `/Users/wdaniero/workplace/python-factory` checkout.
