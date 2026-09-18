# M6.5 Design — Crews, Workspaces, and Provider Choice

**Epic:** `python-factory-bp34j`  
**Milestone:** M6.5 — Crews + model picker

## Goal
A user can define a Crew as typed data, start or resume a Session on it, choose a
model per Session, and let that agent work only inside the Crew's project through
existing Devtools. Live acceptance uses a Crew-selected model differing from the
session default on an already-proven provider—another OpenRouter model or Ollama
(owner decision 2026-09-13; no non-OpenRouter endpoint required). No new agent
runtime or Crew brick is introduced.

## Scope frozen from upstream
KiroCrew's relevant Crew is a named configuration bundle, not `CrewOrchestrator`:
identity/name, explicit agent template, workspace, memory store, model,
description/triggers, CRUD/default/resolved binding, cards/list UI, and
per-session model selection. Empty/`auto` model inherits through fixed precedence;
unknown Crew/template/model and unavailable catalogs fail truthfully.

Deferred: `crew_chat.py` multi-topic orchestration, avatars/sounds/colors,
favorites, watchdog/channel/remote-crew features, template publishing/forking,
kiro-cli model listing, and KiroCrew's inbound OpenAI-compatible server.

Evidence: `/Users/wdaniero/kirocrew-upstream/src/kiro_crew/config/{sections.py,loader.py}`,
`/Users/wdaniero/kirocrew-upstream/src/kiro_crew/mcp_core.py`,
`/Users/wdaniero/kirocrew-upstream/src/kiro_crew/dashboard/handlers/agents.py`, and
`/Users/wdaniero/kirocrew-upstream/website/src/pages/KiroCrewAgentsPage.tsx`.

## Existing rails and gaps

Reuse Agent's unified persona registry and exact scopes; Session's owner-scoped
CAS/project validation; Devtools' allowed-root/project-marker/no-follow policy;
LLM Gateway's secret-free `ChatProfile`; official LangChain model clients; and
CopilotKit v2 properties, SessionDeck, frontend tools, and authenticated MCP BFF.

Gaps: no Crew store/CRUD/default, no Session memory scope, no
`openai-compat/<name>`, one process-wide model, model absent from graph cache
identity, Session model ignored at inference, no safe catalog/page/picker, and
SessionDeck does not restore the complete binding.

## Ownership

- **Agent:** `CrewConfig`, owner-scoped `CrewStore`, resolution, and persona/model
  binding supplied to the existing runtime.
- **Session:** sole authoritative materializer for crew/persona/model/project/
  workspace/memory scope; Agent never creates a parallel Session record.
- **LLM Gateway:** profile parsing and safe catalog metadata; no SDK execution.
- **Memory:** project-selected adapter remains fixed; Crew selects only a logical,
  owner-partitioned namespace.
- **Devtools:** unchanged project authority and file/command/git execution.
- **Companion-X:** typed routes, Crews page, footer picker, and navigation.
- **Workflow:** no ordinary Crew CRUD role.

## Strict Crew storage

Agent adds frozen `CrewConfig`: ambient-derived `tenant_id`/`owner_id`; identifier
`id`; bounded `name`/`description`; required existing `persona_id`; required
Devtools-validated canonical `project`; bounded `workspace`; `memory_scope`;
optional inheritable `model`; bounded `triggers`; positive `revision`. Crew ID,
memory scope, and profile name use strict lowercase grammar plus the existing
credential-shape rejection. Raw client authority is never accepted.

Do **not** widen persona-only `RegistryStore`. Add focused Agent-owned `CrewStore`
with only owner-scoped load/get, CAS save/delete/default operations and separate
disk/in-memory adapters mirroring the persona pattern. Every method requires
`(tenant_id, owner_id)`; no global list/get fallback exists. Disk records live in
an authority-partitioned `crews/` namespace whose directory key is a fixed-width
hash of validated authority, not raw owner text.

Disk update/delete uses a process-local owner lock, compares `expected_revision`,
writes a same-directory temporary file, fsyncs, and atomically `os.replace`s.
The local deployment is single-process; a distributed adapter MUST provide
storage-native conditional-write fencing. In-memory uses the same local CAS
contract. Create is exclusive. Default pointer set/delete is fenced under the
same owner lock so it cannot reference a deleted Crew. Conflicts are typed;
revision is never decorative. Existing materialized Sessions remain usable
after Crew deletion; new resolution of a missing Crew is typed not-found.

## Session authority and resolution

Extend Session's existing creation/lifecycle path with `crew_id` and
`memory_scope` defaults. Agent resolves Crew through its public interface and
passes materialized fields into Session; there is no Agent-owned session-create
store/tool. Project is canonicalized once through `validate_project`. Later Crew
edits affect new Sessions only; explicit owner-scoped CAS rebind is required.

Effective model precedence:

1. explicit persisted Session selection;
2. Crew model;
3. referenced persona model;
4. `COMPANION_X_CHAT_MODEL`.

An empty final result is a typed failure and cannot create an invalid Session.
The picker writes through owner-scoped Session CAS after server-side model
validation. Chat resolves Session by tenant/owner/thread and passes its persisted
model to `RuntimeInvocation`; frontend properties are hints, never authority.
Unknown Crew/persona/model rejects before execution.

Roster discovery omits the default Crew and Crews without triggers. Unknown bind
returns a typed error plus safe available IDs. Deleting the current default is
atomically refused or clears it in the same fenced operation; process default is
used only when no valid default Crew is configured.

## OpenAI-compatible profiles

`resolve_chat_profile` handles `openai-compat/<name>` before Bedrock fallback.
Name matches `^[a-z0-9][a-z0-9-]{0,31}$`, passes credential-shape rejection, and
must appear in an explicit non-secret operator allowlist **before** env-name
derivation or reads. It maps to `<STEM>_BASE_URL`, `<STEM>_API_KEY`, and
`<STEM>_MODEL`; all must be nonblank. Unallowlisted and missing/blank profiles
return byte-identical safe errors and never construct Bedrock.

`ChatProfile` stores only `api_key_env`; no secret/base URL/raw catalog payload is
logged or emitted. SDK construction reads the key and uses a fixed safe-error
enum. Sentinel secrets must be absent from profile repr, errors, tracebacks,
logs, AG-UI, MCP, and catalog output.

Base-URL policy lives in a focused helper. Reject userinfo/query/fragment and
non-HTTP(S). Loopback HTTP requires resolved addresses wholly inside 127.0.0.0/8
or `::1`; remote origins require HTTPS and membership in a nonempty operator
allowlist. Profile names are the only untrusted selector; base URLs are
operator-owned. SDK redirect/DNS behavior is residual operator trust; disable
redirects only if the official client exposes a supported primitive.

The safe catalog comes from an explicit configured profile list through
`llm_gateway.interface`; it returns IDs/provider labels or truthful unavailable,
never fabricated `[]`. Existing OpenRouter/Ollama/Bedrock behavior stays
byte-compatible. Split URL policy from `chat_profile.py` to preserve SRP/<200.

## LangChain execution

Add first-class frozen `RuntimeInvocation.model_id`; do not use string metadata.
It both selects the actual model instance and participates in graph cache identity
with persona/frontend/policy/scope. Extract model build/cache/targeted-eviction to
a small adapter module because `langchain_runtime.py` is already at the limit.
Two model IDs cannot share a model or graph; checkpoint key remains persona +
thread, preserving history.

The runtime accepts an injectable official-model builder and caches by model ID.
Bedrock token refresh evicts only that model and graphs bound to it; retire global
`replace_model` clearing. Update root chat construction, squad runner, and tests
as one scoped migration so no call site half-adopts the new contract. Streaming,
tool binding, structured output, and scope digest remain unchanged.

SDK pins: `langchain==1.3.17`, `langgraph==1.2.11`,
`langchain-openai==1.6.2`, `@copilotkit/react-core@1.53.0`. UI reuses
`frontends/next-dashboard/node_modules/@copilotkit/react-core/dist/`; no custom
dispatcher or wire protocol is added.

## Memory partition

Validate owner and scope separately, then derive adapter `user_id` exactly once
as `sha256(owner_utf8).hexdigest() + "." + memory_scope`. The fixed-width owner
component prevents delimiter ambiguity and metadata-filter bypass. Every Memory
adapter receives this partition key; scope is not a tag/post-filter/backend.
Unidentified, foreign, empty, or credential-shaped scope requests fail closed.

## MCP and UI

Agent deterministic tools: Crew list/get/resolve and delegated safe model catalog.
Operational: Crew create/update/default and Session start/rebind/set-model through
Session's lifecycle. Crew delete is authoring-gated. All use strict Pydantic v2,
ambient authority, CAS, and typed `ToolResult` safe-error enums.

Companion-X adds `/crews`, “new sessions use,” create/edit, and a chat-footer
model picker that groups mixed Bedrock, OpenRouter, Ollama, and compatible entries
by provider without assuming one catalog shape. Dedicated CopilotKit tools navigate
only; mutations remain MCP. Session summaries expose crew/persona/model so
SessionDeck can restore merged properties without clobbering existing context.
Degraded catalog, stale CAS, invalid project, and unavailable model render explicit
errors. The UI slice uses the frontend-design workflow and captures one view-only
frame.

## Acceptance

- Hypothesis: identifiers, profile parsing, owner-scoped Crew isolation, CAS race,
  default/delete fence, empty model, and Memory partition separation including
  delimiter-laden owners.
- Provider: allowlist-before-env, identical existence errors, URL policy,
  secret non-exposure, no Bedrock fallback, and unchanged existing providers.
- Runtime: concurrent Sessions on two compatible base URLs send only to their own
  model/graph; targeted Bedrock refresh leaves other models/graphs intact.
- Crew: owner-2 cannot list/get/update/delete/default owner-1 data; concurrent
  same-revision updates yield one winner; default/delete cannot dangle.
- Session restart preserves all materialized fields; Crew deletion does not break
  an existing Session; switch restores properties; set-model validates at write.
- UI tests list/create/default/picker/degraded/stale/property-merge behavior.
- Live acceptance uses a tool-capable crew-selected model (different OpenRouter model, or Ollama if running) for Devtools read →
  CAS edit → targeted test → git diff, refuses outside-root, and captures the
  Crews/footer frame on ports 18000/13000.

## Slices

1. Safe compatible profiles/URL policy/catalog/official ChatOpenAI/tests.
2. First-class model authority, model-keyed caches, targeted refresh migration.
3. Owner-scoped CAS CrewStore, Session materialization, Memory partition.
4. Crews page, picker, SessionDeck restore, frontend tools, render frame.
5. Restart/live project-edit acceptance with a crew-selected non-default model on a proven provider; then Gate 0/B.
