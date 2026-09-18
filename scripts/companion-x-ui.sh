#!/usr/bin/env bash
# Launch Companion-X API + Next.js UI from anywhere — no containers needed.
#
# Usage:
#   ~/workplace/python-factory/scripts/companion-x-ui.sh
#
# Or add a shell alias:
#   alias companion-ui='~/workplace/python-factory/scripts/companion-x-ui.sh'
#
# All adapters are container-free (ChromaDB, SQLite, networkx, memory).
# The script always runs from the factory root so file-based storage
# (ChromaDB ./chroma_data, ./chroma_memory, events.db) writes to the
# correct location.
#
# Ctrl-C stops both processes.

set -euo pipefail

FACTORY_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEXT_DIR="$FACTORY_ROOT/frontends/next-dashboard"
API_PORT="${API_PORT:-8000}"
NEXT_PORT="${NEXT_PORT:-3000}"
ENV_FILE="$FACTORY_ROOT/projects/companion_x/.env"

# Ports 8000/3000 belong to the owner's live Companion-X. An agent (KiroCrew
# goal loop, sub-agent, cron) must smoke-launch on API_PORT=18000 NEXT_PORT=13000.
# Enforce here so a misread doc can never restart the owner's stack under them.
if [[ -n "${KIROCREW_SPAWNED:-}" || -n "${KIROCREW_SESSION_KEY:-}" ]]; then
    if [[ "$API_PORT" == "8000" || "$NEXT_PORT" == "3000" ]]; then
        echo "REFUSED: agent-spawned launch on owner ports (API_PORT=$API_PORT NEXT_PORT=$NEXT_PORT)." >&2
        echo "Agents must use API_PORT=18000 NEXT_PORT=13000 (LOOP-GUIDE safety rail). Nothing was started." >&2
        exit 2
    fi
fi

cleanup() {
    echo ""
    echo "Stopping Companion-X..."
    [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
    [[ -n "${NEXT_PID:-}" ]] && kill "$NEXT_PID" 2>/dev/null || true
    [[ -n "${API_PID_FILE:-}" ]] && rm -f "$API_PID_FILE"
    wait 2>/dev/null
    echo "Done."
}
trap cleanup EXIT INT TERM

# Source the env file so adapters resolve correctly. Preserve the
# ambient AWS_PROFILE first — the committed .env ships with
# AWS_PROFILE= (blank) as a template default, and `set -a; source`
# would otherwise unconditionally overwrite a real profile (e.g. one
# refreshed via `ada`) with that empty string, breaking every AWS SDK
# call in the API process ("config profile () could not be found").
_AMBIENT_AWS_PROFILE="${AWS_PROFILE:-}"
if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
fi
if [[ -z "${AWS_PROFILE:-}" && -n "$_AMBIENT_AWS_PROFILE" ]]; then
    export AWS_PROFILE="$_AMBIENT_AWS_PROFILE"
fi

# Never mistake a stale API's health response for this launch becoming ready.
# Mirror uvicorn's bind (SO_REUSEADDR, so TIME_WAIT leftovers don't count) and
# give a previous instance that is still draining connections up to 10s to exit
# before declaring the port genuinely taken.
port_free() {
    python3 -c 'import socket,sys
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1",int(sys.argv[1]))); s.close()' "$1" 2>/dev/null
}
for _attempt in $(seq 1 20); do
    port_free "$API_PORT" && break
    [[ $_attempt -eq 1 ]] && echo "API port $API_PORT still held by a previous instance; waiting for it to release..." >&2
    sleep 0.5
done
if ! port_free "$API_PORT"; then
    echo "API port $API_PORT is already in use; stop the owning process or choose API_PORT" >&2
    lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1{print "  held by:", $1, "pid", $2}' >&2 || true
    exit 1
fi

# The local UI always uses authenticated MCP through its server-side BFF.
export MCP_LOCAL_AUTH="${MCP_LOCAL_AUTH:-true}"
if [[ ! "$MCP_LOCAL_AUTH" =~ ^(1|true|yes)$ ]]; then
    echo "companion-x-ui.sh requires MCP_LOCAL_AUTH=true" >&2
    exit 1
fi
if [[ -z "${MCP_LOCAL_AUTH_TOKEN:-}" ]]; then
    export MCP_LOCAL_AUTH_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    echo "==> Generated ephemeral local MCP credential"
elif [[ ${#MCP_LOCAL_AUTH_TOKEN} -lt 16 || ${#MCP_LOCAL_AUTH_TOKEN} -gt 512 \
        || ! "$MCP_LOCAL_AUTH_TOKEN" =~ ^[A-Za-z0-9._~-]+$ ]]; then
    echo "MCP_LOCAL_AUTH_TOKEN must be 16..512 URL-safe characters" >&2
    exit 1
fi

# Select the project-owned Workflow engine registry, independent of cwd.
export WORKFLOW_CONFIG_DIR="${WORKFLOW_CONFIG_DIR:-$FACTORY_ROOT/projects/companion_x/config}"
export EVENTS_BACKEND="${EVENTS_BACKEND:-sqlite}"
export EVENTS_SQLITE_PATH="${EVENTS_SQLITE_PATH:-$FACTORY_ROOT/.storage/events.db}"
export FACTORY_API_PORT="$API_PORT"
export COMPANION_X_LAUNCH_ID="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
API_PID_FILE="$(mktemp -t companion-x-api-pid.XXXXXX)"
export COMPANION_X_API_PID_FILE="$API_PID_FILE"

echo "==> Starting API on :$API_PORT (cwd: $FACTORY_ROOT)"
cd "$FACTORY_ROOT"
uv run python projects/companion_x/main.py > >(sed 's/^/[api] /') 2>&1 &
API_PID=$!

echo "==> Waiting for API health..."
API_READY=0
for _ in $(seq 1 30); do
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "API process exited before becoming ready" >&2
        exit 1
    fi
    HEALTH_BODY="$(curl -sf "http://127.0.0.1:$API_PORT/api/health" 2>/dev/null || true)"
    if [[ -n "$HEALTH_BODY" && -s "$API_PID_FILE" ]]; then
        EXPECTED_API_PID="$(cat "$API_PID_FILE")"
        HEALTH_IDENTITY="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(str(d.get("process_id",""))+":"+str(d.get("launch_id","")))' <<<"$HEALTH_BODY" 2>/dev/null || true)"
        if [[ "$HEALTH_IDENTITY" == "$EXPECTED_API_PID:$COMPANION_X_LAUNCH_ID" ]]; then
            API_READY=1
            echo "==> API ready (pid $EXPECTED_API_PID)"
            break
        fi
    fi
    sleep 1
done
if [[ "$API_READY" != 1 ]]; then
    echo "API did not become ready on port $API_PORT" >&2
    exit 1
fi

echo "==> Starting Next.js on :$NEXT_PORT"
cd "$NEXT_DIR"
API_URL="http://127.0.0.1:$API_PORT" npx next dev --port "$NEXT_PORT" 2>&1 | sed 's/^/[next] /' &
NEXT_PID=$!

echo ""
echo "  Dashboard:  http://localhost:$NEXT_PORT"
echo "  API:        http://localhost:$API_PORT"
echo "  Adapters:   container-free (ChromaDB, SQLite, networkx, memory)"
echo "  Ctrl-C to stop."
echo ""

wait
