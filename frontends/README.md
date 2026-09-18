# Frontends

Non-Python frontend consumers of the Python Software Factory API base.

These are standalone applications that connect to the API base's HTTP endpoints
(`POST /api/tools/{tool_name}`, `GET /api/tools`, `POST /ag-ui/run`, `GET /api/health`).
They are NOT Polylith bricks — no BRICK.yaml, no MCP server, no `interface.py`.

## Available Frontends

- `next-dashboard/` — Next.js 15 + shadcn/ui + Magic UI dashboard
