"""Integration test for the live side-chat gateway wiring (feature-map row 19).

Proves ``register_side_chat`` composes a real SideChatService and mounts it
at the real HTTP paths, end-to-end through FastAPI's TestClient (which runs
sync endpoints in a worker thread — the same shape production requests take).
The aggregator + category lookup are faked (no live MCP server needed); the
LLM planner is exercised for its FAILURE path only (no API key in test env),
proving route registration and the panel still work with no model configured.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from factory.api.runtime.side_chat_wiring import register_side_chat


class _FakeAggregator:
    def invoke_tool(self, tool_name: str, **kwargs):
        return {"tool": tool_name, "kwargs": kwargs}


def _client() -> TestClient:
    app = FastAPI()
    with patch(
        "factory.api.runtime.bridge._get_aggregator", return_value=_FakeAggregator(),
    ), patch(
        "factory.mcp_server.runtime.category_lookup.build_category_lookup",
        return_value={"memory_stats": "deterministic"},
    ):
        register_side_chat(app)
    return TestClient(app)


def test_open_close_work_over_the_real_wiring():
    client = _client()
    r = client.post("/api/chat/slots/wired-slot/side/open")
    assert r.status_code == 200
    assert r.json() == {"slot": "wired-slot", "turns": []}
    assert client.post("/api/chat/slots/wired-slot/side/close").json() == {"closed": True}


def test_turn_degrades_to_no_tools_without_a_configured_model():
    """No OPENROUTER_API_KEY in the test environment -> planner build fails
    -> register_side_chat installs the empty-plan fallback -> the endpoint
    still answers 200 (never 500), just with no tool calls run."""
    client = _client()
    client.post("/api/chat/slots/s/side/open")
    r = client.post("/api/chat/slots/s/side/turn", json={"query": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] == []
    assert len(body["turns"]) == 1  # just the recorded user turn
