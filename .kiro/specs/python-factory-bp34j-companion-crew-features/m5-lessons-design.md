# M5 Design — Typed Lessons and Active Recall

**Epic:** `python-factory-bp34j`  
**Milestone:** M5 — typed lessons and active learning curation  
**Upstream research:** `fbbfcda9`  
**Factory gap map:** `848c6290`

## Goal

Explicit user feedback creates one typed, owner-scoped lesson. Curation assigns a durable status, accepted lessons project into existing Memory retrieval, and a later Agent turn injects the applicable lesson before model invocation. Restart preserves identity, status, and recall.

Final Lessons page, cross-feature navigation, and visual acceptance remain M7 work.

## Ownership

### Lessons brick

A new focused `lessons` capability brick owns:

- typed lesson identity and lifecycle
- exact-match enrichment and scope-local semantic dedup
- authority/confidence ordering
- revision-CAS curation and supersession
- accepted-to-Memory projection bookkeeping

It executes no model and owns no general memory retrieval.

### Existing bricks

- **Learning** remains the domain-neutral reward-signal seam. It does not become a record store.
- **Events** routes feedback/reward and lesson lifecycle events; it does not decide lesson truth.
- **Memory** stores accepted recall material and performs existing relevance/tag/metadata filtering. No Memory/KB/Graph consolidation occurs.
- **Agent** owns intelligent extraction when free-form feedback must become a rule and injects bounded accepted recall before model execution.
- **Storage** supplies durable SQLite primitives.

## Why a new brick

Lesson records have identity, authority, status transitions, supersession, and projection acknowledgement. Those semantics do not belong in generic Memory and are not reward computation. A focused brick prevents both components from accumulating unrelated lifecycle logic while still composing through their public MCP surfaces.

The upstream dual vector/JSONL stores are not ported. Lessons has one durable store behind a port; Memory remains the one retrieval projection.

## Model

`LessonRecord` is strict, frozen, and owner-scoped:

- `tenant_id`, `owner_id`, `lesson_id`
- `rule` (required, 1–500 characters; reject, never truncate)
- `negative` (optional, ≤500 characters)
- `category`: `tool | preference | knowledge`
- `scope`: `global | persona`
- `scope_id` required only for persona scope
- `source`: `user_explicit | feedback | outcome | import`
- `source_ref` and bounded evidence
- confidence in `[0,1]`
- status: `proposed | accepted | rejected | superseded`
- superseded lesson IDs
- Memory projection ID/revision when accepted
- revision and timestamps

Identity key is SHA-256 over canonical `{lower().strip(rule), scope, scope_id, tenant, owner}`. Use `lower`, not `casefold`; global and persona-scoped copies are distinct.

## Write outcomes

Typed egress uses the upstream vocabulary:

- `inserted`
- `enriched`
- `unchanged`
- `deduped`
- `refused`

Every write returns `outcome`, stable reason, current lesson when applicable, and the exact IDs of records superseded by this write. No-op resubmission remains successful and never strips a stored negative clause.

`category`, scope, source, and owner binding are immutable after insert. Enrichment may add a previously absent negative/evidence item and increments revision.

## Dedup and authority

Evaluation is two-pass and scope-local:

1. Exact normalized identity handles unchanged/enrichment deterministically.
2. Generic candidates apply containment and significant-word overlap against Lessons' own same-scope records. Memory-assisted semantic similarity applies only against already-accepted projections; proposed records never live in Memory.

A stored `user_explicit` lesson or strictly higher-confidence lesson blocks lower-authority replacement. Explicit user writes cannot be declined by inferred content. All candidate decisions are computed before mutations. Supersession and insertion commit atomically, and returned superseded IDs are safe identifiers—not raw retired rule text.

Initial core implementation may land exact identity and authority first; semantic candidate scoring is a later M5 slice and must use existing Memory similarity rather than a second vector index.

## Curation

- `user_explicit` lessons are accepted on insert because user authority is definitive.
- feedback/outcome candidates begin proposed.
- Events publishes `lesson.proposed`, `lesson.accepted`, `lesson.rejected`, and `lesson.superseded` after durable transitions.
- Add a dedicated `lesson.proposed` subscription using Events' existing registry and generic caller-bound dispatch mechanism. The existing graph-node learning-curation handler is unrelated and is not reused. Intelligent candidate extraction or ambiguous keep/suppress decisions run through Agent structured output; Events cannot invent rules or assert user authority.
- Curation is revision-CAS and idempotent by `(lesson_id, expected_revision, decision)`.

No public caller may mark another owner's lesson or overwrite immutable authority fields.

## Accepted Memory projection

After acceptance, a retryable projector calls caller-bound `memory_store` with:

- `user_id="kiro-agent"`
- content rendered from rule and optional negative
- tags including `lessons`, `accepted-lessons`, and persona tag when scoped
- metadata with owner-safe `lesson_id`, `status=accepted`, category, scope, and lesson revision

Projection uses canonical key `(lesson_id, revision)`. Because Memory has no idempotency key and Events history does not durably redispatch handlers, a Lessons-owned reconciler scans accepted-but-unprojected records at startup and on a bounded API-owned interval. It performs retrieve-before-store for the exact lesson ID/revision, stores only when absent, then records the returned Memory ID/revision by Lessons revision CAS. A crash after Memory write re-finds that exact projection instead of duplicating it. Rejection/supersession invalidates the prior projection through Memory's public surface. Projection failure leaves lesson truth accepted and pending; Events is observability, never retry ownership.

Companion-X Events configuration must select durable SQLite history so curation and projection dedup survive restart.

## Agent recall

Add a dedicated LangChain `AgentMiddleware` adjacent to steering. In `abefore_model` it calls caller-bound `lessons_recall` with the current query and persona. Lessons then:

1. resolves ambient tenant/owner and exact current persona
2. asks Memory to rank projected candidates using `user_id="kiro-agent"`, accepted lesson tags, and current query
3. verifies every returned `lesson_id` and projection revision against its own authoritative accepted record
4. discards raw Memory rows, stale projections, and owner/persona mismatches
5. returns a bounded typed list of rule/negative pairs

The middleware deduplicates by lesson ID, applies a strict count/character budget, and injects one system context block before the model. It never trusts `kind=lesson`, `status=accepted`, or `user_explicit` metadata alone; a caller writing lookalike rows through generic `memory_store` cannot enter model context.

The block states that explicit learned corrections override defaults, includes rule and negative clauses, and never exposes storage metadata. Rejected, superseded, other-owner, and other-persona lessons are excluded. Recall failure is visible in logs/events but does not fabricate an empty-success capability.

A `learning.applied` event records only lesson IDs and scope when recall is used—never the user text or full rule.

## MCP surface

Strict brick-local Pydantic v2 ingress and typed `ToolResult` egress.

Deterministic:

- `lessons_get`
- `lessons_list`
- `lessons_recall` — owner/persona-bound verified recall through Memory ranking

Operational:

- `lessons_add`
- `lessons_accept`
- `lessons_reject`
- `lessons_remove`

`lessons_add` does not expose `source`, confidence, status, owner, or projection metadata in its input schema; the public operation always writes `user_explicit` authority from ambient identity. Automated feedback/outcome sources use a closed caller-bound proposal service with exact source/evidence binding, so ordinary tools cannot forge user authority.

## Security

- Ambient tenant/owner identity always overrides explicit identity.
- Restricted/temporary/incognito Sessions refuse durable writes.
- Persona scope fails closed when the current persona is absent or mismatched.
- Evidence is bounded JSON and sanitized before Events/Notification egress.
- Recalled rules are delimited as learned user preferences inside a system-authored block, never interpolated into tool arguments or executable templates; higher-priority system/security policy always wins.
- Generic Memory metadata is not proof of lesson authority; recall requires an exact accepted Lessons record and matching projection revision.
- Raw superseded rules are never echoed from mutation tools.
- Memory calls replay the stored owner envelope; no synthetic service identity.
- Governance may disable memory writes, in which case projection remains pending and status is truthful.

ARCC must be queried before implementation. If unavailable, use the established exact-binding/fail-closed pattern and record the outage.

## Acceptance

- Explicit correction inserts one accepted lesson with typed fields and stable identity.
- Same rule/scope replay is unchanged or enriched, never duplicated.
- Lower-authority inferred candidate cannot replace explicit user truth.
- Proposed → accepted/rejected and accepted → superseded transitions are revision-fenced.
- Accepted projection survives restart and retries without duplicate Memory rows.
- A later turn for the same owner/persona injects the lesson before model invocation.
- Rejected/superseded/foreign-owner/foreign-persona lessons are not injected.
- A recall-applied event contains IDs, not lesson content.
- Hypothesis proves identity, enrichment, authority, transition, and dedup invariants.

## Slices

1. Scaffold Lessons brick; strict models, ports, SQLite persistence, exact identity/enrichment, Hypothesis.
2. Typed MCP lifecycle with ambient identity and authority/status transitions.
3. Durable Events curation activation and accepted Memory projection/retry.
4. Agent LangChain recall middleware and applied-event evidence.
5. Restart acceptance: explicit correction changes a later same-persona turn; final visual UX deferred to M7.
