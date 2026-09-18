---
name: factory-fundamentals
description: Core skills every agent needs — Beads issue tracking, Companion-X memory, progressive discovery, powers, and shell safety.
inclusion: auto
---
# Factory Fundamentals — Shared Agent Skills

> These tools are accessed via the `companion-x` and `python-factory` Kiro powers.

Every agent in this workspace MUST know these systems. They are your operational backbone.

## Skill 1: Beads Issue Tracking

Beads (`bd`) is the single source of truth for work tracking. No markdown TODOs.

```bash
bd ready --json           # Find unblocked work
bd show <id>              # View issue details
bd update <id> --claim    # Claim work atomically (do this BEFORE starting)
bd close <id> --reason "" # Complete work (do this AFTER finishing)
bd create "Title" -p 2 --deps discovered-from:<parent-id> --json  # Log discovered work
bd sync                   # Sync with git
```

Session protocol:
1. Check `bd ready` for available work
2. Claim before starting: `bd update <id> --claim`
3. Work on it
4. Discovered new work? `bd create ... --deps discovered-from:<parent-id>`
5. `bd close <id> --reason "Done: <summary>"`
6. Push: `git pull --rebase && bd sync && git push`

Log EVERYTHING as a bead. If you find a bug, create a bead. If you discover tech debt, create a bead. If you have a follow-up idea, create a bead.

## Skill 2: Companion-X Memory (NOT a-mem)

Store and retrieve persistent memory via the companion-x memory brick. NEVER use `mcp_a_mem_*` tools.

### Store a memory
```
call_brick_tool(
  brick_name="memory",
  tool_name="memory_store",
  arguments='{"content": "...", "user_id": "kiro-agent", "category": "fact", "metadata": {"source": "agent"}}'
)
```
Categories: `preference`, `fact`, `summary`, `context`, `custom`

### Retrieve memories (semantic search)
```
call_brick_tool(
  brick_name="memory",
  tool_name="memory_retrieve",
  arguments='{"query": "...", "user_id": "kiro-agent", "limit": 5}'
)
```

### Search by time
```
call_brick_tool(
  brick_name="memory",
  tool_name="memory_search_by_time",
  arguments='{"user_id": "kiro-agent", "time_from": "2026-03-01T00:00:00Z", "time_to": "2026-03-12T00:00:00Z", "limit": 10}'
)
```

ALWAYS pass `"user_id": "kiro-agent"`. Store decisions, findings, and session summaries as memories.

## Skill 3: Companion-X Progressive Discovery

The MCP gateway exposes 9 meta-tools. Bricks lazy-load — `tools_count: -1` means registered but not loaded.

```
list_bricks()                                     # See what's available
get_brick_tools(brick_name="X")                   # Load brick + get tool schemas
call_brick_tool(                                   # Invoke a tool
  brick_name="X", tool_name="tool_name",
  arguments='{"key": "value"}'
)
get_brick_resources(brick_name="X")               # Get resources
read_brick_resource(brick_name="X", uri="X://docs/overview")
get_brick_prompts(brick_name="X")                 # Get prompts
render_brick_prompt(brick_name="X", prompt_name="create_thing", arguments='{}')
```

Discovery flow: `list_bricks` → `get_brick_tools(name)` → `call_brick_tool(name, tool, args)`

## Skill 4: Kiro Powers

Powers extend your capabilities. Key powers in this workspace:

- **builder-mcp** — Amazon internal tooling (code reviews, Brazil, Taskei/SIM, pipelines, oncall). Activate with `kiroPowers(action="activate", powerName="builder-mcp")` before using.
- **playwright** — Browser automation for visual testing. Activate before use.
- **aws-infrastructure-as-code** — CDK, CloudFormation, compliance checks.
- **code-power** — GitHub, filesystem, Hugging Face models.

Always `activate` a power before `use`. Never guess tool names.

## Skill 5: Shell Safety

ALWAYS use non-interactive flags:
```bash
cp -f source dest         # NOT: cp source dest
mv -f source dest         # NOT: mv source dest
rm -f file                # NOT: rm file
rm -rf directory          # NOT: rm -r directory
```

## Skill 6: Foreman Tools (python-factory power)

Use foreman for workspace governance:
- `foreman_info` — Workspace overview
- `foreman_check` — Polylith structure info
- `foreman_guardian_check` — Full compliance gate (THE quality gate)
- `foreman_create_component` — Scaffold new component
- `foreman_build_bricks_index` — Regenerate BRICKS_INDEX
- `foreman_sync_brick_deps` — Scan imports, write pip_packages to BRICK.yaml
- `foreman_resolve_dependencies` — Resolve transitive deps for a project
