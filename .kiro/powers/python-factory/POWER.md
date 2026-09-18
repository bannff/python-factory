---
name: "python-factory"
displayName: "Python Software Factory"
description: "Polylith monorepo governance for the Python Software Factory. Scaffold bricks, run compliance checks, manage the BRICKS_INDEX, resolve dependencies, and create projects."
keywords: ["polylith", "foreman", "brick", "factory", "scaffold", "compliance"]
author: "wdaniero"
---

# Python Software Factory

## Overview

Foreman is the governance and scaffolding MCP server for the Python Software Factory Polylith monorepo. It handles brick creation, compliance checks, dependency resolution, and project wiring.

Use this power when you need to create new bricks, verify workspace compliance, manage the BRICKS_INDEX, resolve transitive dependencies, or scaffold deployable projects.

Workspace-level steering files (in `.agents/steering/`) provide the full architectural context, dev principles, and brick inventory. This power focuses on the foreman tooling itself.

## Onboarding

### Prerequisites
- Python 3.11+ with `uv` package manager
- The python-factory workspace checked out locally
- `uv run` must work from the workspace root

### Verify Setup
Run `health_check` to confirm the foreman server is responding, then `foreman_info` to see the workspace structure.

## Tools Reference

### Brick Contract (standard on every brick)
- `get_capabilities` — Machine-readable feature list
- `health_check` — Fast readiness probe
- `describe_config_schema` — JSON schema for configuration options

### Workspace Inspection
- `foreman_info` — Workspace overview via `poly info` (components, bases, projects)
- `foreman_check` — Polylith structure check (informational, not authoritative)
- `foreman_guardian_check` — **The compliance gate.** Checks import integrity, branch naming, file LOC limits, and BRICKS_INDEX sync. Run this before every commit.
- `foreman_get_repo_guardrails` — Returns the repo operating model and guardrails for agents

### Scaffolding
- `foreman_create_component` — Create a new component brick (params: `name`)
- `foreman_create_base` — Create a new base brick (params: `name`)

### Index Management
- `foreman_build_bricks_index` — Build BRICKS_INDEX from all BRICK.yaml files (returns data, does not write)
- `foreman_write_bricks_index` — Write BRICKS_INDEX.yaml to workspace root

### Dependency Resolution & Projects
- `foreman_resolve_dependencies` — Resolve transitive brick dependencies by scanning actual Python imports. Params: `bricks` (list), optional `include_adapters`
- `foreman_create_project` — Scaffold a new project wiring the given bricks. Generates `projects/<name>/` with pyproject.toml and README. Params: `name`, `bricks` (list), optional `description`, `include_adapters`
- `foreman_sync_brick_deps` — Deep-scan brick imports (AST walk) and write `pip_packages` into BRICK.yaml. Params: optional `bricks` (list), `dry_run` (bool)

## Common Workflows

### Create a New Brick
1. `foreman_create_component` with the brick name
2. Add BRICK.yaml, runtime/ports.py, mcp/ primitives, interface.py (see workspace steering for patterns)
3. `foreman_guardian_check` to verify compliance
4. `foreman_write_bricks_index` to update the index

### Pre-Commit Compliance
Run `foreman_guardian_check`. It validates:
- No cross-component imports of internals (only `factory.<brick>.interface` allowed)
- Branch naming conventions (`feat/`, `fix/`, `chore/`)
- All files under 200 LOC
- BRICKS_INDEX.yaml matches current BRICK.yaml files

### Scaffold a Deployable Project
1. `foreman_sync_brick_deps` to ensure pip_packages are current in BRICK.yaml
2. `foreman_resolve_dependencies` with your brick list to get the full transitive closure
3. `foreman_create_project` to generate pyproject.toml and README

### Regenerate BRICKS_INDEX
1. `foreman_build_bricks_index` to preview (returns data without writing)
2. `foreman_write_bricks_index` to persist

## Troubleshooting

### Guardian Check Fails: Import Integrity
A brick is importing another brick's internals. Change `from factory.other.runtime.foo import Bar` to `from factory.other.interface import Bar`.

### Guardian Check Fails: BRICKS_INDEX Out of Sync
Run `foreman_write_bricks_index` to regenerate from current BRICK.yaml files.

### Guardian Check Fails: LOC Limit
Split the file. Move business logic to `runtime/` subdirectory, MCP tools to `mcp/` subdirectory.

### foreman_resolve_dependencies Returns Unexpected Results
Run `foreman_sync_brick_deps` first — it deep-scans imports and updates BRICK.yaml pip_packages. Then re-resolve.

## MCP Config Placeholders

This power runs the foreman server locally via `uv run`. The `cwd` must point to your workspace checkout:

- `PYTHON_FACTORY_WORKSPACE_PATH`: Absolute path to your python-factory workspace (your checkout root; the `mcp.json` here omits `cwd` — run the server from that root)
