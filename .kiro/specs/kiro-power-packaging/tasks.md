# Tasks: Companion-X Kiro Power

## Tasks

- [ ] 1. Generate the live brick catalog by calling `list_bricks`, then `get_brick_tools`/`get_brick_resources`/`get_brick_prompts` for each brick. Capture: name, one-line description, has_prompts, has_resources.
  - Requirements: 2
  - Files: none (data gathering)

- [ ] 2. Create `POWER.md` with frontmatter, overview, discovery flow, and brick catalog table. Target under 200 lines. Use the catalog data from task 1.
  - Requirements: 1, 2
  - Files: `powers/companion-x/POWER.md`

- [ ] 3. Create `mcp.json` with companion-x server config. Include env var placeholders for Neo4j, AWS, and backend selectors. Document both local (stdio) and remote (AgentCore URL) modes. Set autoApprove for all 9 meta-tools.
  - Requirements: 3
  - Files: `powers/companion-x/mcp.json`

- [ ] 4. Test the Power locally: install via Kiro Powers UI from `powers/companion-x/` directory. Verify keyword activation triggers on "memory", "security", "knowledge base", etc. Verify brick catalog is readable on activation.
  - Requirements: 1, 5
  - Files: none (testing)

- [ ] 5. (v2) Create steering files for high-value workflows: `security-review.md`, `memory-pipeline.md`, `ml-experiments.md`. Each under 100 lines — workflow steps with tool names.
  - Requirements: 4
  - Files: `powers/companion-x/steering/`

- [ ] 6. (v2) Add MCP Config Placeholders section to POWER.md documenting every env var that needs replacing, with instructions on how to obtain each value.
  - Requirements: 5
  - Files: `powers/companion-x/POWER.md`
