"""Tests for optional MCP authoring tools.

These tools are intentionally disabled by default and require an explicit enable flag.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
from collections.abc import Generator

import pytest

from factory.agent import SuperAgent
from factory.agent.authoring import AuthoringManager, AuthoringError


@pytest.fixture
def temp_config_dir_empty() -> Generator[Path, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_dir = Path(tmpdir)
        (config_dir / "agents").mkdir()
        (config_dir / "swarms").mkdir()
        (config_dir / "graphs").mkdir()
        (config_dir / "tools").mkdir()
        yield config_dir


@pytest.mark.asyncio
async def test_authoring_tools_enabled_by_env_var(temp_config_dir_empty, monkeypatch):
    monkeypatch.setenv("SUPER_AGENT_ENABLE_AUTHORING_TOOLS", "1")

    agent = SuperAgent(config_dir=str(temp_config_dir_empty))
    await agent.initialize()

    tool_names = {t.name for t in await agent.mcp.list_tools()}

    assert "authoring_status" in tool_names
    assert "list_config_items" in tool_names
    assert "write_config" in tool_names
    assert "read_config" in tool_names
    assert "delete_config" in tool_names
    assert "read_settings" in tool_names
    assert "write_settings" in tool_names
    assert "read_tool_module" in tool_names
    assert "write_tool_module" in tool_names
    assert "delete_tool_module" in tool_names
    assert "reload_config" in tool_names


@pytest.mark.asyncio
async def test_authoring_tools_do_not_escape_config_root(temp_config_dir_empty, monkeypatch):
    monkeypatch.setenv("SUPER_AGENT_ENABLE_AUTHORING_TOOLS", "1")

    agent = SuperAgent(config_dir=str(temp_config_dir_empty))
    await agent.initialize()

    author = AuthoringManager(temp_config_dir_empty)
    with pytest.raises(AuthoringError):
        author.read_tool_module("../secrets")
