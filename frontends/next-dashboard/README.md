# Companion X — Next.js Dashboard

Next.js 15 + shadcn/ui + Magic UI dashboard for Companion X.

Universal MCP-driven UI — the in-app agent, Kiro, CLI, or any MCP client
can drive actions. Everything flows through the MCP server.

## Prerequisites

- Node.js 20+
- Python Software Factory unified server running on `http://localhost:8000`

The API can run without Docker — just start it with the lightweight local adapters:

```bash
# From the repo root (uses the no-container .env defaults)
uv run python projects/companion_x/main.py
```

See `projects/companion_x/README.md` → "Local Dev (No Containers)" for the full adapter table and env vars.

## Setup

```bash
npm install
```

## Development

```bash
cp .env.local.example .env.local
# Set MCP_LOCAL_AUTH_TOKEN to the same ephemeral value used by the API.
npm run dev
```

Opens at [http://localhost:3000](http://localhost:3000). API and native MCP
calls are proxied by Next.js Route Handlers. The local MCP bearer remains
server-side and is never stored by browser JavaScript.

## Build

```bash
npm run build
npm start
```

## Docker

```bash
docker build -t next-dashboard .
docker run -p 3000:3000 -e API_URL=http://host.docker.internal:8000 next-dashboard
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_URL` | `http://localhost:8000` | Backend API base URL (server-side, read at runtime) |
| `MCP_LOCAL_AUTH` | — | Must be `true` for the localhost-only MCP BFF |
| `MCP_LOCAL_AUTH_TOKEN` | — | Exact API local token; server-only, never `NEXT_PUBLIC` |

### Backend env vars (set on the API process, not here)

The dashboard's CopilotKit chat sidebar renders the AG-UI `REASONING_MESSAGE_*` Thinking panel only when the **Python API** is configured for extended thinking. These vars live in `projects/companion_x/.env` (the API side), not in `.env.local`:

| Variable | Required for Thinking panel | Description |
|----------|------------------------------|-------------|
| `COMPANION_X_CHAT_MODEL` | yes | Must be a thinking-capable chat model. Sonnet 3.7+ or Opus 4+ supported (e.g. `us.anthropic.claude-sonnet-4-6`). Haiku / Nova / Llama / GLM5 / GPT-OSS work for chat but no-op the Thinking panel. |
| `COMPANION_X_CHAT_THINKING_BUDGET` | yes | Bedrock minimum 1024; 16000 recommended. Unset or `0` builds `BedrockModel` without `additionalModelRequestFields.thinking={...}`, so Sonnet emits no `reasoning_text` and the AG-UI mapper has nothing to translate. |

If the panel stays silent, check the API env first — bd:python-factory-sopw landed sane defaults for both vars in `.env` and `.env.example` so a fresh clone doesn't regress.

## API Endpoints (proxied)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/tools` | List all MCP tools |
| `POST` | `/api/tools/{name}` | Execute an MCP tool |
| `GET` | `/api/health` | Gateway health check |
| `POST` | `/ag-ui/run` | AG-UI SSE stream |

## Architecture

IDE-like workbench layout with three columns:

```
ActivityBar │ Canvas                          │ ChatSidebar (resizable)
(icon rail) │ (tabbed views)                  │ (440px default, collapsible)
            │ Welcome · Graph · Timeline      │
            │ Findings · Evals · ML           │
```

- **ActivityBar** — Left icon rail for view switching.
- **Canvas** — Center panel with tabbed views: Welcome, Graph (React Force Graph 3D), Timeline, Findings, Evals, ML. A2UI pushes rich views here.
- **ChatSidebar** — Right panel, visible by default and collapsible. Default width is 440px; users can drag the left edge to resize, clamped between 440px and 70% of viewport width. The chosen width persists across reloads via `localStorage` (key `companion-x:chat-width`) and auto-clamps on viewport resize. AG-UI SSE streams agent work into the chat.

  Built on **CopilotKit v2** (`@copilotkit/react-core/v2`, `<CopilotChat agentId="companion_x">`). Reasoning is rendered via the built-in `CopilotChatReasoningMessage` Thinking panel, which auto-handles the canonical AG-UI `REASONING_MESSAGE_START / CONTENT / END` trio emitted by the backend chat-stream mapper (bd:python-factory-eyuj). Upstream emission is now wired (bd:python-factory-tpfk) — set `COMPANION_X_CHAT_THINKING_BUDGET` (int, Bedrock min 1024) and a thinking-capable chat model (Sonnet 3.7+ or Opus 4+) in the API env to actually light up the Thinking panel; Haiku / Nova / Llama / GLM5 / GPT-OSS chat models are no-op. Tool-call rendering uses `useRenderTool` / `useDefaultRenderTool` against a shared `<ToolCallCard>` (Radix Collapsible) that produces Kiro / VS Code Copilot-style status pills uniformly across instrumented tools (`kb_search`, `cache_get`, `veritas_check`, …) and the wildcard catch-all for the other ~650 tools. The `<InlineView>` A2UI fallthrough is preserved (bd:python-factory-47sl). Chat is now canvas-aware: `<CanvasContextBridge />` pushes `{activeView, activeTabId, openTabs, recentTools[≤10]}` into the agent context every turn via CopilotKit v2's `useAgentContext` (bd:python-factory-vw04), and `<FrontendTools />` registers `fe_navigate_canvas` (the seed tool) via `useFrontendTool` so the chat agent can drive the workbench through a CopilotKit re-POST round-trip — backend stub defers, FE handler runs, conversation continues with the `role=tool` reply (bd:python-factory-115z). See `.agents/recipes/canvas-aware-chat.md` for the end-to-end walkthrough.

  **Local agent registration via `selfManagedAgents` (bd:python-factory-sopw).** The provider registers `companion_x` locally with `selfManagedAgents={{ [COMPANION_X_AGENT_ID]: agent }}` instead of passing `runtimeUrl`. Both props together cause `core.agents.companion_x` to be replaced by a `ProxiedCopilotRuntimeAgent` from the `/info` handshake (`@copilotkitnext/core` `index.mjs::updateRuntimeConnection`'s `{...localAgents, ...remoteAgents}` merge — remote wins), shadowing the `HttpAgent` the chat sidebar and the dev inspector both subscribe to. Dropping `runtimeUrl` keeps the runtime-status badge at "Disconnected" (cosmetic — there's no remote runtime to be connected to) and collapses chat + inspector onto the same `HttpAgent` instance, so the inspector's AG-UI Events / Agent / State tabs populate after a run. The shared agent ID lives in `lib/copilotkit/companion-agent.ts` so the FE provider and the BE runtime route at `app/api/copilotkit/[[...path]]/route.ts` never drift. A small `<InspectorAttachWorkaround />` companion in `lib/copilotkit/inspector-attach-workaround.tsx` toggles `<cpk-web-inspector>.core` once after mount to bridge an upstream `@copilotkitnext/[email protected]` gap where `set core(value)` doesn't fire `attachToCore` on initial React-driven assignment; it's idempotent and removable when the upstream patch ships.

Any MCP client can drive actions — the in-app chat agent, Kiro IDE, CLI tools,
or external agents. Everything flows through MCP.

Built with shadcn/ui + Magic UI + Framer Motion. Glass morphism styling,
spring animations. All brick views rendered from ReactAdapter JSON.
