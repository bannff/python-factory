# M6 Design — Versioned Artifacts

**Epic:** `python-factory-bp34j`  
**Milestone:** M6 — Artifacts

## Goal
Add a focused Artifacts brick so tenant-owned artifacts can be saved, updated,
versioned, organized, commented on, reopened, and restored through Companion-X
chat and UI. Port KiroCrew behavior, not its filesystem/aiohttp architecture.

## Scope frozen from upstream
KiroCrew's `ArtifactStore` and MCP tests establish these guarantees:

- Stable 1–80 character lowercase slugs; same-owner collisions suffix `-2`,
  `-3`; rename never changes identity.
- Text kinds: widget, HTML, Markdown, SVG, JSON, and text; explicit immutable
  snapshots retain the latest 50 versions.
- Revert writes an old version as a new head; history is never rewritten.
- Name/kind/tag filters, bounded folders, one-level comment threads, and
  open/review/resolved status. Agents may mark review but never resolve.
- Gallery/detail deep links use `/artifacts/<slug>`.

Remote publication/provider sync, forks, file-backed reload, auto-widget harvest,
binary/image assets, webapps, and deploy are explicitly deferred in `roadmap.md`.
Folder CRUD and comment triage are post-core M6 scope: they do not gate Tier-1's
save/version/list/reopen proof, but remain planned before M6 closure unless Gate 0
explicitly amends the roadmap.

Sources: `/Users/wdaniero/kirocrew-upstream/src/kiro_crew/artifacts.py`,
`src/kiro_crew/mcp_tools/artifacts.py`, and their artifact/folder/comment/MCP tests.

## Existing Factory rails

- Storage exposes `get_sql_store()` through `factory.storage.interface`; Session,
  Scheduler, and Lessons already own revision-CAS schemas over that public port.
- Storage protected artifacts remain encrypted immutable business-content
  records; Dataset, Evals, and ML retain their materialization authorities.
- No Artifacts brick, route, gallery, folder tree, or comment UI exists.
- Agent exact tool scopes, Events, CopilotKit v2 tools, and the secured MCP UI
  frame are reusable.

## Ownership

- **Artifacts:** identity, heads/versions, kinds/tags, folders, comments,
  tombstones, lifecycle policy, and typed events.
- **Storage:** persistence through public `SQLStore`; no Storage internals.
- **Agent:** invokes exact artifact tools; never owns artifact state.
- **Events:** carries content-free facts after durable mutation.
- **Companion-X:** gallery/detail rendering and navigation.
- **Workflow:** no ordinary CRUD role; only future long-running import/export.

## Models and bounds
All records derive `(tenant_id, owner_id)` from verified ambient MCP authority;
client authority and actor kind are not ingress fields.

- `ArtifactRecord`: slug, name, description, kind, tags, folder, head version,
  revision, timestamps, tombstone.
- `ArtifactVersion`: scope, positive version, immutable UTF-8 content and SHA-256,
  kind, server-derived actor, event type, timestamp.
- `ArtifactFolder`: opaque ID, parent, name, position, revision, timestamps.
- `ArtifactComment`: opaque ID, slug, root/parent IDs, body, server-derived actor,
  status, revision, timestamps.

Brick-local Pydantic v2 DTOs are strict and `extra="forbid"`. Initial kinds are
`widget|html|markdown|svg|json|text`. Content must encode as UTF-8 with
`len(content.encode("utf-8")) <= 1_048_576`; lone surrogates reject. Bounds:
name 200, description 2,000, tags 16, folder depth 20, versions 50, comments 500.

## Persistence contract
The initial SQLite adapter receives Storage's public `SQLStore`. The port commits
each call, so every mutation is one atomic SQL statement; no public multi-statement
transaction is claimed. SQLite triggers execute inside the triggering statement's
implicit transaction, following Scheduler's existing precedent.

Persistence is a runtime/port guarantee, not an accidental SQLite feature. Each
adapter must pass the same atomic snapshot/CAS contract suite. Unsupported adapters
fail loudly at composition; they never silently lose version guarantees. Slice 1
splits schema/rows, artifact CAS, versions, folders, and comments into focused files
under 200 lines.

### Create and idempotency

- Unique keys are `(tenant_id, owner_id, slug)` and nullable
  `(tenant_id, owner_id, idempotency_key)`.
- Slug allocation performs bounded owner-scoped `INSERT ... ON CONFLICT DO
  NOTHING` attempts for base then suffixes through `-64`; it never selects a
  foreign row, catches raw integrity errors, or does `SELECT max → INSERT`.
- Separate owners may both receive the base slug. Exhaustion returns typed
  `slug_exhausted` without exposing collisions.
- Idempotency binds the key to normalized name, description, kind, ordered tags,
  and content SHA-256. Equal replay returns the previously allocated artifact
  without a new version; any differing bound field returns typed conflict and no
  mutation.
- `AFTER INSERT` writes immutable version 1 in the same statement.

### Update, history, and tombstones

- Content update is one owner-scoped `UPDATE ... WHERE revision=:expected` that
  increments version and revision. `row_count=0` is an opaque typed conflict.
- `AFTER UPDATE WHEN NEW.version > OLD.version` inserts the snapshot and deletes
  only rows of that artifact with `version <= NEW.version - 50`.
- `BEFORE UPDATE` on version rows always aborts. `BEFORE DELETE` allows only
  already-expired rows outside the retained head-relative 50-window; no version
  delete tool exists.
- Metadata updates increment revision but not content version.
- Revert reads an immutable owner-scoped version, then uses the same fenced head
  update; a concurrent winner causes conflict, never overwrite.
- Tombstones keep the slug reserved and disappear from get/list/version/comment
  reads with the same result as never-existing/foreign. Slug reuse is out of M6.
- Permanent purge is authoring-gated and human-only. M6 does not claim a
  separate durable audit record for purge.

### Folders and comments

- Folder reads/mutations are authority-scoped. Move rejects self/descendant cycles
  and results deeper than 20. Foreign IDs are opaque not-found.
- Non-cascade folder delete is one fenced tombstone statement whose trigger
  reparents children/artifacts to the deleted folder's parent.
- Cascade remains disabled until an authoring-gated, bounded owner-scoped single-
  statement recursive plan and isolation tests exist.
- Comment insertion conditionally enforces the 500 cap in the same statement.
  Replies require a same-owner root parent (`parent_id IS NULL`) in that statement;
  reply-to-reply rejects.
- Actor kind is derived from ambient authority (`agent_id` means agent). Agents can
  only mark review. Resolve/delete are authoring tools and reject agent actors.

## MCP surface
Deterministic: `artifacts_get`, `artifacts_list`, `artifacts_versions`,
`artifacts_get_comments`, `artifacts_folder_list`.

Operational: `artifacts_save`, `artifacts_update`, `artifacts_revert`,
`artifacts_post_comment`, `artifacts_reply_comment`,
`artifacts_mark_comment_review`, folder create/rename/move/safe-delete, and
`artifacts_move`.

Authoring: human-only comment resolve/delete, artifact purge, and any future
cascade. Every tool has strict ingress and typed `ToolResult[OutputDTO]` egress;
not-found, foreign, tombstoned, and unauthorized results are opaque.

## Events
Typed strict event DTOs allow exactly authority, slug, version, revision, kind,
optional folder/comment ID, and optional content SHA-256. They have no content,
name, description, tags, or comment body fields. Comment events never carry body
digests. After source commit, Artifacts emits
`artifact.created|updated|reverted|commented|moved|deleted`; publication failure is
truthful and cannot roll back durable state.

## UI and navigation
The default persona receives only required artifact tools. CopilotKit frontend
tools navigate to `/artifacts` and `/artifacts/<slug>`; stubs never mutate state.
Gallery/detail refresh from authoritative MCP results and render stale CAS conflict.

Markdown/text/JSON are escaped/parsed. HTML, widget, and SVG all pass as untrusted
`text/html`/srcdoc through the existing `McpUiFrame` iframe. Its sandbox is exactly
`allow-scripts` with `referrerPolicy=no-referrer` and never `allow-same-origin`;
CSP remains a separate nonce/object/frame layer. No artifact payload reaches React
`dangerouslySetInnerHTML` in the dashboard origin.

Each shipping surface gets a view-only screenshot. Responsive/motion/new-user
polish remains M7.

## Acceptance

- Hypothesis: owner-isolated slug allocation, exact idempotency, stale CAS, atomic
  snapshot monotonicity, and restart parity across every adapter.
- Prune property: after 60 updates the current head and contiguous latest 50 remain,
  retained bytes are unchanged, other artifacts are untouched, and restart matches.
- Two concurrent same-name saves yield base+suffixed (or typed conflict), never
  duplicate/lost; different owners both get the base slug without leakage.
- Direct retained-version update/delete aborts; only expired retention rows prune.
- Typed events expose only the allowlist and ambient authority; comment body/digest
  and artifact content/name/description/tags are absent.
- Agent resolve/delete denies; mark-review succeeds; forged actor field and nested
  reply reject. Concurrent comment 500/501 stores exactly 500.
- 1 MiB+1 and lone-surrogate content reject.
- Tombstoned/foreign/nonexistent reads are indistinguishable and slug stays reserved.
- Folder descendant/depth/foreign tests prove scoped fail-closed behavior.
- HTML event-handler/script and hostile SVG payloads cannot access parent DOM or
  cookies; iframe canary asserts sandbox never contains `allow-same-origin`.
- Chat-only save→update→versions→comment→revert→reopen→navigate passes; revert adds
  a version and preserves prior bytes. Gallery/detail screenshots are inspected.
- Protected Storage artifacts, Dataset, Evals, ML, Memory, KB, and existing views
  remain green. Gate B security re-reviews tenant and untrusted-rendering code.

## Slices

1. Scaffold split Artifacts brick; strict models, SQLite adapter, save/get/list,
   owner-scoped slug/idempotency, trigger v1, CAS and adapter-contract properties;
   immediate Gate A.5 for the new persistence seam.
2. Updates, immutable versions, prune, revert, tombstone, typed lifecycle events.
3. Folder/comment lifecycle and authoring gates; Gate A.5.
4. Agent exact-tool composition, gallery, navigation, sandbox canary/screenshot.
5. Detail/version/comment/revert UI and chat-only acceptance; then Gate 0/B.
