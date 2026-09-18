# M2.5 Design — Project-Scoped Developer Tools

**Epic:** `python-factory-bp34j`  
**Milestone:** M2.5 — developer tools and project scoping  
**Upstream research:** `89b0a798`  
**Factory gap map:** `519bfec4`

## Goal

From Companion-X chat, an authorized Agent can read and edit files, search a project, run bounded development commands, and inspect git status/diff/log. Every operation is confined to the project bound to the active Session. A minimal Terminal activity view renders streamed command output. Final visual polish remains M7.

## Ownership

### Devtools brick

A new focused `devtools` capability brick owns host-local project operations:

- project-root resolution and path confinement
- bounded text file reads, creates, and compare-and-swap edits
- bounded directory listing and source search
- argv-only command execution, process lifecycle, timeout, and output bounds
- project-local git read and gated write operations
- normalized command/output lifecycle events

It does not own sessions, model reasoning, durable workflow attempts, or remote sandboxes.

### Existing rails

- **Session** owns which project is bound to a conversation.
- **Agent** decides which tool to call and scopes tools by persona.
- **Workflow** owns durable attempts/retries when a command belongs to background work.
- **Sandbox** remains the `env_id`-scoped remote/container environment executor.

Devtools does not import Sandbox internals across the brick boundary. Its host-local descriptor-pinned file/process adapters deliberately differ from Sandbox's provisioned-environment adapters. Shared behavior is held by contract parity tests (output caps, argv execution, git diff shaping), not a hidden cross-brick utility import; promote a neutral primitive only if repeated implementation evidence later justifies one.
- **API/AG-UI/CopilotKit** carry tool activity and command output to the cockpit.

## Why not Sandbox

Sandbox requires a provisioned `env_id` and runs commands/uploads inside Docker, EC2, LocalStack, or another adapter. Its workspace is environment staging, not the user's active host project. Mixing host-local authority into it would combine two security models and lifecycles. Devtools is a focused connector brick, not another runtime.

## Project binding

No Devtools tool accepts an absolute project root. Every call carries ambient tenant/owner/thread identity. Devtools resolves the canonical Session through caller-bound Session MCP and reads its persisted `project` value.

Add an operational Session project-binding tool and one shared project validator. It becomes the sole writer: `session_create` must call the same validator when `project` is supplied (or leave project unbound), so raw free-text project values cannot bypass binding policy. The validator:

- accepts a candidate directory only from an authenticated user/Agent context
- resolves it under deployment-configured allowed roots
- requires an existing directory and repository/project marker
- persists canonical absolute path by owner/tenant/revision CAS
- rejects relative roots, traversal, sensitive roots, and symlink escapes

Every Devtools call re-resolves the stored root and verifies it remains beneath an allowed root. Missing, moved, revoked, or invalid roots fail closed.

## Path confinement

All file paths are project-relative UTF-8 strings. Reject absolute paths, empty components, `.`/`..`, NUL/control characters, drive/UNC forms, and excessive depth before filesystem access.

The resolver checks lexical and canonical forms, then requires `resolved.relative_to(project_root)`. Existing-target reads/edits use `O_NOFOLLOW` and descriptor `fstat`; regular files only. Writes resolve and pin the parent directory, reject final-component symlinks/hardlinks/non-regular files, and publish through same-directory atomic replacement. Resolution errors or stalls refuse—never fall back to lexical trust.

Sensitive files remain denied even inside a project: credential files, private keys, `.env*`, git credential/config trust files, and configured secret patterns. Bulk list/search omits denied children and never descends `.git`, dependency caches, build outputs, or ignored paths by default.

## File and search contracts

- Read cap defaults to 1 MiB text; binary/NUL content returns typed `binary_file`, not decoded garbage.
- Reads support bounded line offset/limit and return SHA-256 for edit CAS.
- Create/write accepts bounded UTF-8 content and an explicit `create | overwrite` mode.
- Edit requires the caller's previously observed SHA-256. A changed file returns typed `conflict`; newer content wins.
- Directory listing has depth, entry-count, and rendered-byte caps.
- Search supports both content matching and bounded filename/glob discovery (`rg --files -g` when available, bounded Python fallback); no separate hidden file-discovery path exists. Match/file/byte/time limits are mandatory.

## Command execution

`run_command` accepts `argv: list[str]`, never a shell string. It accepts an optional project-relative working directory but no environment map. The runtime constructs a minimal inherited environment and runs with `shell=False`, cwd pinned beneath the project root, a new process group, bounded timeout, bounded concurrent processes, and capped stdout/stderr.

The allowed command registry starts with development families needed by repository workflows: Python/uv/pytest, configured linters/type checkers, Node package/test/build tools, and safe read-only utilities. Executable resolution must be absolute and cannot resolve from the writable project tree. Structural deny rules reject shell interpreters, command substitution, redirection/pipelines, destructive filesystem commands, package publication, credential tooling, network listeners, infrastructure teardown, and git mutation through `run_command`.

Timeout/cancel closes pipes and terminates the process group (`TERM`, bounded grace, then `KILL`). Output truncation is explicit in typed egress; no successful empty fallback.

## Git contracts

Git always uses `git -C <canonical-project-root>` with argument arrays and disabled external diff/textconv/pagers.

Deterministic reads:

- status porcelain
- bounded diff with explicit path filters
- bounded log/show/blame

Writes are separate tools—never reachable through `run_command`:

- stage explicit confined paths only; no implicit `git add .` or `-A`
- commit requires explicit user-approved authoring, a bounded message, and staged-file list; repository hooks run normally, and `--no-verify` is allowed only when the user explicitly requests skipping them
- push is authoring-gated, requires explicit remote and branch, rejects `HEAD`, `@`, wildcard/all/mirror, force, and protected branches, and uses `-u` only for a new branch
- reset-hard, clean, destructive checkout/restore, and branch deletion are not exposed

## MCP surface

Strict brick-local Pydantic v2 ingress and typed `ToolResult` egress.

Deterministic:

- `devtools_read_file`
- `devtools_list_dir`
- `devtools_search`
- `devtools_git_status`
- `devtools_git_diff`
- `devtools_git_log`

Operational:

- `devtools_write_file` — `op_kind("write")`
- `devtools_edit_file` — `op_kind("write")`
- `devtools_run_command` — `op_kind("shell")`

All deterministic file/search/git reads use `op_kind("read")`; all git mutations use `op_kind("authoring")`. Runtime is decomposed from the first slice into `path_resolver`, `sensitive_policy`, `file_ops`, `command_runner`, `output_safety`, and `git_ops`; no source file may reach 200 lines.

Authoring:

- `devtools_git_stage`
- `devtools_git_commit`
- `devtools_git_push`

Authoring tools remain disabled unless the existing operator gate is enabled. The Agent cannot self-approve them.

## Streaming and Terminal activity

Use the existing in-process tool invocation stream and AG-UI activity mapping. `run_command` publishes ordered content-free start metadata, bounded stdout/stderr chunks, and one terminal event keyed by tool-call/run identity. The final typed result repeats the bounded tail and exit status for model reasoning.

The minimal M2.5 Terminal panel is an activity renderer, not an unrestricted interactive PTY. It shows command, cwd relative to project, live output, duration, exit status, timeout/truncation state, and cancel where supported. It reuses the existing shell/terminal visual vocabulary but removes stale Strands interrupt language. Full tabs, resizing, history UX, and animation polish remain M7.

## Agent integration

- Add Devtools tools to the `developer` persona through exact tool scoping.
- Reuse Evals policy/acceptance ownership through Workflow; do not create ad-hoc reviewer personas. QA/meta gates are discoverable graph definitions with one personaless inline LangGraph node (`agent_id=None`) whose rubric, model, and exact Devtools scope are sealed into `ExecutionManifestV1` before Workflow enrollment through `launch_managed_graph(origin_kind="dynamic")`. The node is `read_only=True` and receives only `devtools_read_file`, `devtools_list_dir`, `devtools_search`, `devtools_git_status`, `devtools_git_diff`, and `devtools_git_log`—never write/edit/run-command/authoring tools. Builder-run deterministic checks are immutable evidence inputs, not commands the reviewer executes. Evals applies thresholds and writes the immutable content-addressed report through a focused `evals_review_and_record` operation; Workflow owns durable attempt/retry. Legacy `EvalAgentConfig` execution in `agent_task.py`/`simulator_adapter.py` is Strands-based, ignores tool scope, and is explicitly outside this Track B path.
- M4 goal loops inherit their persona's exact tool scope and Session project binding; no special loop branch.
- Update the developer prompt so it no longer claims filesystem/shell are unavailable when Devtools is configured.

## Security and audit

ARCC was unavailable before research; apply the established fail-closed boundary and record the outage.

- Ambient transport identity wins over explicit identity.
- Project binding and every operation are owner/tenant/session checked.
- Read/write/command/git results use stable typed refusal codes without leaking denied absolute paths or secret content.
- Command lifecycle audit records executable, argument digest, relative cwd, exit state, duration, and output digest—not environment values.
- Output passed from Terminal to model is bounded, strips ANSI and non-printable controls except newline/tab, and is credential/redaction scanned; scan ambiguity refuses model handoff.
- Symlink, hardlink, FIFO/device, resolution timeout, and owner mismatch tests are mandatory.

## Acceptance

Through Companion-X chat on a bound fixture project, the developer persona:

1. reads a source file and receives content plus SHA-256
2. edits it using that hash
3. runs the project's targeted test command and receives ordered terminal chunks plus exit status
4. reads git diff showing the edit
5. is refused when reading/editing a path or symlink outside the project

Additional acceptance:

- stale edit hash never overwrites newer content
- timeout kills the whole child process group
- output caps and binary refusal are truthful
- git external diff/textconv and protected-branch push are refused
- another owner/session cannot reuse the project binding
- Workflow-managed QA/meta review graphs are discoverable, compile to sealed personaless LangGraph manifests with exactly the six read-only Devtools tools, and persist thresholded immutable results through `evals_review_and_record`; builder test results are supplied as evidence and no reviewer receives command/write/authoring tools
- Hypothesis covers path normalization/confinement, edit CAS, argv policy, and output caps

## Slices

1. Scaffold Devtools; project-root resolver, sensitive-path policy, text read/list/search, Hypothesis confinement.
2. Atomic create/edit with SHA-256 CAS and owner-scoped Session project binding.
3. Bounded argv command runner, process-group timeout/cancel, and streaming events.
4. Git read tools plus authoring-gated stage/commit/push.
5. Agent developer/QA/meta persona scoping and minimal Terminal activity renderer.
6. Chat-only fixture acceptance; final visual polish deferred to M7.
