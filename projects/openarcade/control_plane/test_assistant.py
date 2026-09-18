"""Tests for control_plane.assistant — behavior-named, AAA structure.

All tests run WITHOUT strands-agents installed. They exercise the lean
contract: NullAssistant behavior, resolve_assistant factory logic, and
protocol shape compliance.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from control_plane.assistant import (
    AssistantConfig,
    AssistantLoop,
    NullAssistant,
    resolve_assistant,
)


# ---------------------------------------------------------------------------
# NullAssistant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_null_assistant_send_yields_unavailable_message():
    """NullAssistant.send yields a single honest 'unavailable' message."""
    assistant = NullAssistant()
    chunks: list[str] = []
    async for chunk in assistant.send("hello"):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert "unavailable" in chunks[0].lower()
    assert "OPENARCADE_MODEL_ID" in chunks[0]


@pytest.mark.asyncio
async def test_null_assistant_send_yields_same_message_for_any_input():
    """NullAssistant always yields the same fallback regardless of input."""
    assistant = NullAssistant()
    chunks_a = [c async for c in assistant.send("launch game")]
    chunks_b = [c async for c in assistant.send("")]

    assert chunks_a == chunks_b


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


def test_null_assistant_satisfies_assistant_loop_protocol():
    """NullAssistant is a runtime-checkable instance of AssistantLoop."""
    assistant = NullAssistant()
    assert isinstance(assistant, AssistantLoop)


# ---------------------------------------------------------------------------
# resolve_assistant — no model configured
# ---------------------------------------------------------------------------


def test_resolve_assistant_returns_null_when_no_model_configured():
    """resolve_assistant returns NullAssistant when model_id is None."""
    config = AssistantConfig(model_id=None)
    assistant = resolve_assistant(config)
    assert isinstance(assistant, NullAssistant)


def test_resolve_assistant_returns_null_when_model_id_empty():
    """resolve_assistant treats empty string model_id as unconfigured."""
    config = AssistantConfig(model_id="")
    assistant = resolve_assistant(config)
    assert isinstance(assistant, NullAssistant)


# ---------------------------------------------------------------------------
# resolve_assistant — strands import unavailable
# ---------------------------------------------------------------------------


def test_resolve_assistant_returns_null_when_strands_import_fails():
    """resolve_assistant returns NullAssistant when strands is not installed.

    Simulates ImportError by patching the import path.
    """
    config = AssistantConfig(model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0")

    # Remove strands_assistant from sys.modules if cached, then block import
    modules_to_block = [
        "control_plane.strands_assistant",
        "strands",
        "strands.models.bedrock",
        "mcp",
        "strands.tools.mcp",
    ]
    saved = {}
    for mod in modules_to_block:
        if mod in sys.modules:
            saved[mod] = sys.modules.pop(mod)

    original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

    def _blocked_import(name, *args, **kwargs):
        if name == "control_plane.strands_assistant" or name.startswith("strands"):
            raise ImportError(f"Simulated: {name} not installed")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=_blocked_import):
        # Clear cached module so the fresh import triggers
        sys.modules.pop("control_plane.strands_assistant", None)
        assistant = resolve_assistant(config)

    # Restore
    for mod, val in saved.items():
        sys.modules[mod] = val

    assert isinstance(assistant, NullAssistant)


# ---------------------------------------------------------------------------
# AssistantConfig.from_env
# ---------------------------------------------------------------------------


def test_config_from_env_reads_model_id(monkeypatch):
    """AssistantConfig.from_env reads OPENARCADE_MODEL_ID."""
    monkeypatch.setenv("OPENARCADE_MODEL_ID", "us.meta.llama3-1-8b-instruct-v1:0")
    monkeypatch.delenv("OPENARCADE_BEDROCK_MODEL", raising=False)
    config = AssistantConfig.from_env()
    assert config.model_id == "us.meta.llama3-1-8b-instruct-v1:0"


def test_config_from_env_falls_back_to_bedrock_model(monkeypatch):
    """AssistantConfig.from_env falls back to OPENARCADE_BEDROCK_MODEL."""
    monkeypatch.delenv("OPENARCADE_MODEL_ID", raising=False)
    monkeypatch.setenv("OPENARCADE_BEDROCK_MODEL", "anthropic.claude-v2")
    config = AssistantConfig.from_env()
    assert config.model_id == "anthropic.claude-v2"


def test_config_from_env_returns_none_model_when_unset(monkeypatch):
    """AssistantConfig.from_env returns model_id=None when no env set."""
    monkeypatch.delenv("OPENARCADE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENARCADE_BEDROCK_MODEL", raising=False)
    config = AssistantConfig.from_env()
    assert config.model_id is None
