# Tasks: Standalone Brick MCP Servers

## Tasks

- [ ] 1. Add standalone entry point to Veritas brick: create `components/veritas/src/factory/veritas/mcp/server.py` (thin shell calling `create_mcp_server().run()`) and `components/veritas/src/factory/veritas/mcp/__main__.py` (enables `python -m factory.veritas.mcp.server`). Verify it runs: `VERITAS_BACKEND=memory uv run python -m factory.veritas.mcp.server`.
  - Requirements: 1, 2
  - Files: `components/veritas/src/factory/veritas/mcp/server.py`, `components/veritas/src/factory/veritas/mcp/__main__.py`

- [ ] 2. Add standalone entry point to SIPP brick: same pattern as task 1. Create `mcp/server.py` + `mcp/__main__.py`. Verify: `SIPP_BACKEND=memory uv run python -m factory.sipp.mcp.server`.
  - Requirements: 1, 2
  - Files: `components/sipp/src/factory/sipp/mcp/server.py`, `components/sipp/src/factory/sipp/mcp/__main__.py`

- [ ] 3. Update `.kiro/settings/mcp.json` to split topology: remove `veritas` (and `sipp` when ready) from `MCP_INCLUDE_BRICKS`, add separate `veritas` and `sipp` server entries with `VERITAS_BACKEND=midway` and `SIPP_BACKEND=midway`. Test that Kiro sees tools from all three servers.
  - Requirements: 3
  - Files: `.kiro/settings/mcp.json`

- [ ] 4. Update the Kiro Power packaging spec (`kiro-power-packaging/design.md`) to document the split topology `mcp.json` pattern. The Power's `mcp.json` should show companion-x (aggregator) + veritas (local) + sipp (local) as the default config.
  - Requirements: 3, 5
  - Files: `.kiro/specs/kiro-power-packaging/design.md`

- [ ] 5. Document the standalone entry point pattern in `.agents/steering/brick-anatomy.md` so future bricks can be made standalone in under 5 minutes. Include the two-file template and the `python -m` invocation.
  - Requirements: 4
  - Files: `.agents/steering/brick-anatomy.md`

- [ ] 6. (v2) Add `--transport` CLI flag to standalone entry points supporting `stdio` (default), `sse`, and `streamable-http` for non-local use cases. Use `argparse` or FastMCP's built-in transport selection.
  - Requirements: 1
  - Files: `components/veritas/src/factory/veritas/mcp/server.py`, `components/sipp/src/factory/sipp/mcp/server.py`
