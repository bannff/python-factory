from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts" / "companion-x-ui.sh"


def test_launcher_refuses_an_already_owned_api_port() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    env = {**os.environ, "API_PORT": str(port), "NEXT_PORT": "39999"}
    try:
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=15, check=False,
        )
    finally:
        listener.close()
    assert result.returncode != 0
    assert f"API port {port} is already in use" in result.stderr
    assert "Starting API" not in result.stdout


def test_launcher_requires_one_shared_server_only_local_token() -> None:
    text = SCRIPT.read_text()
    assert 'export MCP_LOCAL_AUTH="${MCP_LOCAL_AUTH:-true}"' in text
    assert "export MCP_LOCAL_AUTH_TOKEN=" in text
    assert 'API_URL="http://127.0.0.1:$API_PORT" npx next dev' in text
    assert "NEXT_PUBLIC_MCP_LOCAL_AUTH_TOKEN" not in text
    assert "COMPANION_X_API_PID_FILE" in text
    assert 'export EVENTS_BACKEND="${EVENTS_BACKEND:-sqlite}"' in text
    assert "EVENTS_SQLITE_PATH" in text
    assert "process_id" in text and "COMPANION_X_LAUNCH_ID" in text
