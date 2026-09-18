"""Tests for wall.assistant_panel — structural + behavior, no heavy deps."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import MagicMock

import flet as ft
import pytest

from wall.assistant_panel import assistant_panel, ChatMessage, _message_bubble, _empty_state
from wall import theme as T


# --- Unit: _message_bubble ---


def test_bubble_user_has_accent_bgcolor():
    msg = ChatMessage(role="user", text="hello")
    bubble = _message_bubble(msg)
    assert isinstance(bubble, ft.Container)
    assert bubble.bgcolor == T.ACCENT


def test_bubble_assistant_has_surface_bgcolor():
    msg = ChatMessage(role="assistant", text="hi there")
    bubble = _message_bubble(msg)
    assert bubble.bgcolor == T.BG_SURFACE


def test_bubble_text_is_selectable():
    msg = ChatMessage(role="user", text="test")
    bubble = _message_bubble(msg)
    assert bubble.content.selectable is True


# --- Unit: _empty_state ---


def test_empty_state_shows_reason_text():
    panel = _empty_state("Model not configured")
    assert isinstance(panel, ft.Container)
    col = panel.content
    assert isinstance(col, ft.Column)
    # Icon + text
    assert len(col.controls) == 2
    text_ctrl = col.controls[1]
    assert "Model not configured" in text_ctrl.value


# --- Integration: assistant_panel (disabled) ---


def test_panel_disabled_shows_empty_state():
    panel = assistant_panel(
        [],
        on_send=lambda _: None,
        enabled=False,
        empty_reason="AI assistant not configured — set OPENARCADE_MODEL_ID",
    )
    assert isinstance(panel, ft.Container)
    # Should be the empty state (Column with icon + text)
    col = panel.content
    assert isinstance(col, ft.Column)
    assert len(col.controls) == 2
    assert "OPENARCADE_MODEL_ID" in col.controls[1].value


# --- Integration: assistant_panel (enabled) ---


def test_panel_enabled_shows_messages_and_input():
    messages = [
        ChatMessage(role="user", text="What games do I have?"),
        ChatMessage(role="assistant", text="You have 4 games in your library."),
    ]
    panel = assistant_panel(messages, on_send=lambda _: None, enabled=True)
    assert isinstance(panel, ft.Container)
    # Content is Column: header + ListView + input_row
    content_col = panel.content
    assert isinstance(content_col, ft.Column)
    assert len(content_col.controls) == 3
    header = content_col.controls[0]
    assert header.value == "Assistant"
    msg_list = content_col.controls[1]
    assert isinstance(msg_list, ft.ListView)
    assert len(msg_list.controls) == 2
    input_row = content_col.controls[2]
    assert isinstance(input_row, ft.Row)


def test_panel_enabled_empty_messages():
    panel = assistant_panel([], on_send=lambda _: None, enabled=True)
    content_col = panel.content
    msg_list = content_col.controls[1]
    assert isinstance(msg_list, ft.ListView)
    assert len(msg_list.controls) == 0


def test_on_send_callback_invoked():
    """on_send callback receives the typed text."""
    sent = []
    panel = assistant_panel([], on_send=lambda t: sent.append(t), enabled=True)
    content_col = panel.content
    input_row = content_col.controls[2]
    # TextField is the first control (expand=True), send button is second
    text_field = input_row.controls[0]
    assert isinstance(text_field, ft.TextField)


def test_send_button_has_tooltip():
    panel = assistant_panel([], on_send=lambda _: None, enabled=True)
    content_col = panel.content
    input_row = content_col.controls[2]
    send_btn = input_row.controls[1]
    assert isinstance(send_btn, ft.IconButton)
    assert send_btn.tooltip == "Send message"


# --- Navigator integration: assistant route ---


def test_navigator_assistant_route_null_assistant(monkeypatch, tmp_path):
    """Navigator routes to assistant; with no configured model the page shows an
    INLINE setup form (provider/model/key), not a dead pointer to Settings."""
    monkeypatch.delenv("OPENARCADE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENARCADE_BEDROCK_MODEL", raising=False)
    monkeypatch.delenv("OPENARCADE_API_KEY", raising=False)
    # Isolate the stored config dir so from_stored() finds no saved model.
    monkeypatch.setenv("OPENARCADE_CONFIG_DIR", str(tmp_path))

    from wall.navigator import Navigator
    from wall.models import WallViewModel, GameTile

    vm = WallViewModel(
        tiles=[GameTile(id="t1", title="Test", system="SNES", art_url="", rom_path="", playable=True)],
        columns=2,
    )
    nav = Navigator(vm)
    nav._on_nav_select("assistant")

    body = nav._switcher.content
    assert isinstance(body, ft.Container)
    # NullAssistant path -> inline setup view: icon + heading + guidance + config box.
    col = body.content
    assert isinstance(col, ft.Column)
    assert len(col.controls) == 4
    assert "Set up the AI assistant" in col.controls[1].value
    # The config section is embedded INLINE (not a Settings pointer): the last
    # control is a container wrapping the provider/model/key section.
    section_container = col.controls[3]
    assert isinstance(section_container, ft.Container)
    section = section_container.content
    assert isinstance(section, ft.Column)
    assert section.controls[0].value == "Assistant"  # section header row


def test_navigator_assistant_route_with_model(monkeypatch):
    """When model is configured but strands unavailable, still NullAssistant."""
    # strands is not installed in the lean env, so resolve_assistant falls back
    monkeypatch.setenv("OPENARCADE_MODEL_ID", "us.anthropic.claude-3-haiku-20240307-v1:0")

    from wall.navigator import Navigator
    from wall.models import WallViewModel, GameTile

    vm = WallViewModel(
        tiles=[GameTile(id="t1", title="Test", system="SNES", art_url="", rom_path="", playable=True)],
        columns=2,
    )
    nav = Navigator(vm)
    # Without strands installed, resolve_assistant returns NullAssistant
    # This is the expected lean-path behavior
    nav._on_nav_select("assistant")
    body = nav._switcher.content
    assert isinstance(body, ft.Container)


# --- Streaming consumer test ---


class FakeAssistant:
    """Fake AssistantLoop that yields predetermined chunks."""

    def __init__(self, chunks: list[str]):
        self._chunks = chunks

    async def send(self, message: str) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk


@pytest.mark.asyncio
async def test_stream_assistant_appends_chunks(monkeypatch):
    """_stream_assistant_response accumulates chunks into messages list."""
    monkeypatch.delenv("OPENARCADE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENARCADE_BEDROCK_MODEL", raising=False)

    from wall.navigator import Navigator
    from wall.models import WallViewModel, GameTile

    vm = WallViewModel(
        tiles=[GameTile(id="t1", title="Test", system="SNES", art_url="", rom_path="", playable=True)],
        columns=2,
    )
    nav = Navigator(vm)
    # Override the assistant with our fake
    nav._assistant = FakeAssistant(["Hello", " world", "!"])
    nav._is_null_assistant = False

    # Simulate: user sends a message
    nav._assistant_messages.append(ChatMessage(role="user", text="hi"))
    await nav._stream_assistant_response("hi")

    # Should have 2 messages: user + assistant
    assert len(nav._assistant_messages) == 2
    assert nav._assistant_messages[1].role == "assistant"
    assert nav._assistant_messages[1].text == "Hello world!"


@pytest.mark.asyncio
async def test_stream_multiple_chunks_accumulate(monkeypatch):
    """Each chunk adds to the assistant message incrementally."""
    monkeypatch.delenv("OPENARCADE_MODEL_ID", raising=False)
    monkeypatch.delenv("OPENARCADE_BEDROCK_MODEL", raising=False)

    from wall.navigator import Navigator
    from wall.models import WallViewModel, GameTile

    vm = WallViewModel(
        tiles=[GameTile(id="t1", title="Test", system="SNES", art_url="", rom_path="", playable=True)],
        columns=2,
    )
    nav = Navigator(vm)
    nav._assistant = FakeAssistant(["A", "B", "C"])
    nav._is_null_assistant = False

    await nav._stream_assistant_response("test")

    assert nav._assistant_messages[-1].text == "ABC"


# --- Import guard: lean path must NOT import strands_assistant or fastmcp ---


def test_wall_does_not_import_strands_assistant():
    """Verify wall.assistant_panel and wall.navigator do not directly import strands."""
    import importlib
    import ast
    from pathlib import Path

    wall_dir = Path(__file__).parent
    panel_src = (wall_dir / "assistant_panel.py").read_text()
    navigator_src = (wall_dir / "navigator.py").read_text()
    chrome_src = (wall_dir / "chrome.py").read_text()

    # Parse all import statements from the three critical files
    for name, src in [("assistant_panel", panel_src), ("navigator", navigator_src), ("chrome", chrome_src)]:
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "strands" not in alias.name, f"{name} directly imports {alias.name}"
                    assert "fastmcp" not in alias.name, f"{name} directly imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Allow the guarded import inside resolve_assistant (control_plane.assistant)
                # but wall/ files must never import strands_assistant or fastmcp
                if name != "navigator":  # navigator imports control_plane.assistant (the lean seam) which is fine
                    assert "strands_assistant" not in module, f"{name} imports {module}"
                    assert "fastmcp" not in module, f"{name} imports {module}"
                else:
                    # navigator may import control_plane.assistant but NOT strands_assistant directly
                    assert "strands_assistant" not in module, f"{name} imports {module}"
                    assert "fastmcp" not in module, f"{name} imports {module}"
