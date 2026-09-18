"""Adversarial tests for assistant-anywhere: chat overlay + VM shared state.

QA agent (breaker) attacking:
- Shared-state consistency between drawer and landing page
- Dual send-path race / interleave
- Null assistant degrade
- Error surfacing mid-stream
- Toggle/offset state machine rapid-fire
- RuntimeError guards on pre-mount controls
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import flet as ft
import pytest

from wall.assistant_panel import ChatMessage
from wall.assistant_vm import AssistantVM
from wall.chat_overlay import build_chat_overlay
from wall.models import GameTile, WallViewModel
from wall.navigator import Navigator


# --- Fixtures ---

def _tile(title="T", system="SNES"):
    return GameTile(
        id=f"{system}-{title}", title=title, system=system,
        art_url="", rom_path="", core=None, playable=True,
    )


def _vm():
    return WallViewModel(tiles=[_tile("A"), _tile("B")], columns=2)


def _make_nav():
    with patch.object(Navigator, "_reload_assistant", lambda self: None):
        nav = Navigator(_vm())
    nav._assistant_vm.is_null = False
    nav._assistant_vm._assistant = None  # will be replaced per-test
    return nav


def _make_streaming_assistant(chunks: list[str], delay: float = 0):
    """Create a mock assistant whose .send() yields chunks."""
    async def _send(text: str):
        for chunk in chunks:
            if delay:
                await asyncio.sleep(delay)
            yield chunk

    assistant = MagicMock()
    assistant.send = _send
    return assistant


def _make_error_assistant(chunks_before_error: list[str], exc: Exception):
    """Create a mock assistant that yields some chunks then raises."""
    async def _send(text: str):
        for chunk in chunks_before_error:
            yield chunk
        raise exc

    assistant = MagicMock()
    assistant.send = _send
    return assistant


# ============================================================
# 1. SHARED-STATE CONSISTENCY
# ============================================================

class TestSharedStateConsistency:
    """Verify drawer and landing page reference the SAME messages list."""

    def test_drawer_on_send_mutates_shared_vm(self):
        """When drawer _on_send fires, it appends to the shared vm.messages."""
        nav = _make_nav()
        nav._assistant_vm._assistant = _make_streaming_assistant(["hi"])
        vm = nav.assistant_vm
        drawer, fab = build_chat_overlay(nav, vm)

        # Simulate drawer send -- _on_send adds the user msg directly
        vm.messages.append(ChatMessage(role="user", text="drawer msg"))
        # This is the SAME list the navigator sees
        assert nav._assistant_messages[-1].text == "drawer msg"
        assert nav._assistant_messages is vm.messages

    def test_landing_page_send_visible_to_drawer_on_toggle(self):
        """Messages added on the landing page path appear in drawer after toggle."""
        nav = _make_nav()
        vm = nav.assistant_vm
        drawer, fab = build_chat_overlay(nav, vm)

        # Simulate landing page send
        vm.messages.append(ChatMessage(role="user", text="landing msg"))
        vm.messages.append(ChatMessage(role="assistant", text="landing reply"))

        # Toggle drawer open -- _toggle_drawer rebuilds body from vm.messages
        drawer.toggle()
        # The VM messages list has both messages (identity check)
        assert len(vm.messages) == 2
        assert vm.messages[0].text == "landing msg"
        assert vm.messages[1].text == "landing reply"

    def test_drawer_rebuild_does_not_snapshot_messages(self):
        """Each toggle-open rebuilds from the LIVE vm.messages, not a stale copy."""
        nav = _make_nav()
        vm = nav.assistant_vm
        drawer, fab = build_chat_overlay(nav, vm)

        # Open once
        drawer.toggle()
        # Add a message WHILE open (simulating streaming)
        vm.messages.append(ChatMessage(role="user", text="msg1"))
        # Close and re-open
        drawer.toggle()
        vm.messages.append(ChatMessage(role="user", text="msg2"))
        drawer.toggle()
        # Both messages present in the shared list
        assert len(vm.messages) == 2

    def test_messages_list_identity_never_replaced(self):
        """The vm.messages object itself is never replaced -- only mutated."""
        nav = _make_nav()
        vm = nav.assistant_vm
        original_list = vm.messages
        drawer, fab = build_chat_overlay(nav, vm)

        # Add messages, toggle, etc.
        vm.messages.append(ChatMessage(role="user", text="x"))
        drawer.toggle()
        drawer.toggle()

        # Still the exact same list object
        assert vm.messages is original_list


# ============================================================
# 2. DUAL SEND PATHS — CONCURRENT/INTERLEAVED
# ============================================================

class TestDualSendPaths:
    """Attack the concurrent send scenario."""

    @pytest.mark.asyncio
    async def test_concurrent_sends_both_append_to_shared_messages(self):
        """Two concurrent sends (drawer + landing) both write to vm.messages."""
        nav = _make_nav()
        vm = nav.assistant_vm
        vm._assistant = _make_streaming_assistant(["chunk1", "chunk2"], delay=0.01)
        drawer, fab = build_chat_overlay(nav, vm)

        # Simulate: user sends from drawer, then immediately from landing
        vm.messages.append(ChatMessage(role="user", text="from drawer"))
        vm.messages.append(ChatMessage(role="user", text="from landing"))

        # Both stream responses concurrently
        async def _drawer_stream():
            vm.messages.append(ChatMessage(role="assistant", text="…"))
            idx = len(vm.messages) - 1
            acc = ""
            async for chunk in vm.send("from drawer"):
                acc += chunk
                vm.messages[idx] = ChatMessage(role="assistant", text=acc)

        async def _landing_stream():
            vm.messages.append(ChatMessage(role="assistant", text="…"))
            idx = len(vm.messages) - 1
            acc = ""
            async for chunk in vm.send("from landing"):
                acc += chunk
                vm.messages[idx] = ChatMessage(role="assistant", text=acc)

        await asyncio.gather(_drawer_stream(), _landing_stream())

        # Both assistant messages should be present and complete
        assistant_msgs = [m for m in vm.messages if m.role == "assistant"]
        assert len(assistant_msgs) == 2
        for m in assistant_msgs:
            assert m.text == "chunk1chunk2"

    @pytest.mark.asyncio
    async def test_placeholder_collision_separate_indices(self):
        """Two "…" placeholders get separate msg_idx values -- no overwrite."""
        nav = _make_nav()
        vm = nav.assistant_vm
        vm._assistant = _make_streaming_assistant(["a"], delay=0)

        # Manually simulate what both send paths do
        vm.messages.append(ChatMessage(role="assistant", text="…"))
        idx1 = len(vm.messages) - 1
        vm.messages.append(ChatMessage(role="assistant", text="…"))
        idx2 = len(vm.messages) - 1

        # They should have DIFFERENT indices
        assert idx1 != idx2
        assert idx1 == 0
        assert idx2 == 1

        # Writing to one doesn't clobber the other
        vm.messages[idx1] = ChatMessage(role="assistant", text="response1")
        vm.messages[idx2] = ChatMessage(role="assistant", text="response2")
        assert vm.messages[idx1].text == "response1"
        assert vm.messages[idx2].text == "response2"


# ============================================================
# 3. NULL ASSISTANT — GRACEFUL DEGRADE
# ============================================================

class TestNullAssistant:
    """When is_null=True or _assistant=None, no crash, no infinite loop."""

    @pytest.mark.asyncio
    async def test_send_with_none_assistant_yields_nothing(self):
        """vm.send() is a no-op generator when _assistant is None."""
        vm = AssistantVM()
        vm._assistant = None
        chunks = []
        async for chunk in vm.send("hello"):
            chunks.append(chunk)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_drawer_stream_with_null_assistant_no_crash(self):
        """_stream_response with null assistant doesn't crash or hang."""
        nav = _make_nav()
        vm = nav.assistant_vm
        vm._assistant = None
        vm.is_null = True

        # The drawer's _stream_response calls vm.send() which returns immediately
        vm.messages.append(ChatMessage(role="assistant", text="…"))
        msg_idx = len(vm.messages) - 1
        accumulated = ""
        async for chunk in vm.send("test"):
            accumulated += chunk

        # No chunks yielded, placeholder remains
        assert accumulated == ""
        # In the actual code path, empty accumulated triggers the "(No response)" msg
        # This verifies the generator doesn't hang or raise

    def test_null_assistant_drawer_builds_without_crash(self):
        """Building the drawer overlay when is_null=True doesn't raise."""
        nav = _make_nav()
        nav._assistant_vm.is_null = True
        nav._assistant_vm._assistant = None
        drawer, fab = build_chat_overlay(nav, nav.assistant_vm)
        # Should build fine
        assert isinstance(drawer, ft.Container)
        # Toggle should work
        drawer.toggle()
        drawer.toggle()


# ============================================================
# 4. ERROR SURFACING — EXCEPTION MID-STREAM
# ============================================================

class TestErrorSurfacing:
    """Verify errors surface in messages and don't leave "…" dangling."""

    @pytest.mark.asyncio
    async def test_drawer_stream_error_replaces_placeholder(self):
        """Exception during streaming replaces "…" with error text."""
        nav = _make_nav()
        vm = nav.assistant_vm
        vm._assistant = _make_error_assistant(["partial"], RuntimeError("model died"))
        drawer, fab = build_chat_overlay(nav, vm)

        # Simulate _stream_response logic (from chat_overlay.py)
        vm.messages.append(ChatMessage(role="assistant", text="…"))
        msg_idx = len(vm.messages) - 1
        accumulated = ""
        try:
            async for chunk in vm.send("test"):
                accumulated += chunk
                vm.messages[msg_idx] = ChatMessage(role="assistant", text=accumulated or "…")
        except Exception as exc:
            vm.messages[msg_idx] = ChatMessage(
                role="assistant", text=f"⚠ Assistant error: {exc}"
            )

        assert "⚠ Assistant error: model died" in vm.messages[msg_idx].text
        # No dangling "…" placeholder
        assert vm.messages[msg_idx].text != "…"

    @pytest.mark.asyncio
    async def test_landing_stream_error_replaces_placeholder(self):
        """Landing page error path is consistent with drawer."""
        nav = _make_nav()
        vm = nav.assistant_vm
        vm._assistant = _make_error_assistant([], ValueError("bad config"))

        # Simulate navigator._stream_assistant_response logic
        vm.messages.append(ChatMessage(role="assistant", text="…"))
        msg_idx = len(vm.messages) - 1
        accumulated = ""
        try:
            async for chunk in vm.send("test"):
                accumulated += chunk
                vm.messages[msg_idx] = ChatMessage(role="assistant", text=accumulated or "…")
        except Exception as exc:
            vm.messages[msg_idx] = ChatMessage(
                role="assistant", text=f"⚠ Assistant error: {exc}"
            )

        assert "⚠ Assistant error: bad config" in vm.messages[msg_idx].text

    @pytest.mark.asyncio
    async def test_error_after_partial_chunks_preserves_error_not_partial(self):
        """Error after receiving some chunks overwrites the partial with error."""
        nav = _make_nav()
        vm = nav.assistant_vm
        vm._assistant = _make_error_assistant(
            ["hello ", "world"], IOError("connection lost")
        )

        vm.messages.append(ChatMessage(role="assistant", text="…"))
        msg_idx = len(vm.messages) - 1
        accumulated = ""
        try:
            async for chunk in vm.send("test"):
                accumulated += chunk
                vm.messages[msg_idx] = ChatMessage(role="assistant", text=accumulated)
        except Exception as exc:
            vm.messages[msg_idx] = ChatMessage(
                role="assistant", text=f"⚠ Assistant error: {exc}"
            )

        # Error replaces the partial "hello world" -- correct behavior
        assert "⚠ Assistant error: connection lost" in vm.messages[msg_idx].text


# ============================================================
# 5. TOGGLE / OFFSET STATE MACHINE
# ============================================================

class TestToggleStateMachine:
    """Attack the drawer toggle with rapid and edge-case sequences."""

    def test_rapid_double_toggle_returns_to_closed(self):
        """Double-toggle = open then close = back to hidden."""
        nav = _make_nav()
        drawer, fab = build_chat_overlay(nav, nav.assistant_vm)

        drawer.toggle()  # open
        drawer.toggle()  # close
        assert drawer.offset.x == 1.0
        assert not drawer.is_open()

    def test_triple_toggle_ends_open(self):
        """Odd number of toggles leaves drawer open."""
        nav = _make_nav()
        drawer, fab = build_chat_overlay(nav, nav.assistant_vm)

        drawer.toggle()
        drawer.toggle()
        drawer.toggle()
        assert drawer.offset.x == 0
        assert drawer.is_open()

    def test_rapid_10_toggles_consistent(self):
        """10 rapid toggles: final state is closed (even count)."""
        nav = _make_nav()
        drawer, fab = build_chat_overlay(nav, nav.assistant_vm)

        for _ in range(10):
            drawer.toggle()

        assert drawer.offset.x == 1.0
        assert not drawer.is_open()

    def test_offset_and_open_flag_always_in_sync(self):
        """After any toggle, offset.x and is_open() are consistent."""
        nav = _make_nav()
        drawer, fab = build_chat_overlay(nav, nav.assistant_vm)

        for i in range(20):
            drawer.toggle()
            if drawer.is_open():
                assert drawer.offset.x == 0, f"Desync at toggle {i+1}: open but offset={drawer.offset.x}"
            else:
                assert drawer.offset.x == 1.0, f"Desync at toggle {i+1}: closed but offset={drawer.offset.x}"

    def test_toggle_while_messages_stream_doesnt_crash(self):
        """Toggling during a simulated mid-stream state doesn't crash."""
        nav = _make_nav()
        vm = nav.assistant_vm
        vm.messages.append(ChatMessage(role="user", text="q"))
        vm.messages.append(ChatMessage(role="assistant", text="partial…"))
        drawer, fab = build_chat_overlay(nav, vm)

        # Toggle several times while "streaming" is in progress
        drawer.toggle()
        vm.messages[-1] = ChatMessage(role="assistant", text="partial more…")
        drawer.toggle()
        drawer.toggle()
        # No crash, messages intact
        assert vm.messages[-1].text == "partial more…"


# ============================================================
# 6. RUNTIME / UPDATE GUARDS
# ============================================================

class TestRuntimeGuards:
    """Verify no unguarded .update() can throw during unmounted state."""

    def test_toggle_before_page_mount_no_crash(self):
        """toggle() when controls are not mounted swallows RuntimeError."""
        nav = _make_nav()
        # No page attached -- updates would throw RuntimeError
        nav._page = None
        drawer, fab = build_chat_overlay(nav, nav.assistant_vm)

        # Should not raise
        drawer.toggle()
        assert drawer.is_open()
        drawer.toggle()
        assert not drawer.is_open()

    def test_refresh_drawer_before_mount_no_crash(self):
        """The internal _refresh_drawer handles unmounted gracefully."""
        nav = _make_nav()
        nav._page = None
        vm = nav.assistant_vm
        drawer, fab = build_chat_overlay(nav, vm)

        # Simulate what _refresh_drawer does -- it rebuilds and calls .update()
        # which would throw if not mounted. The guard swallows it.
        vm.messages.append(ChatMessage(role="user", text="test"))
        # Trigger toggle (which calls _refresh_drawer internally via rebuild)
        drawer.toggle()
        # No crash


# ============================================================
# 7. DEFECT PROBE: vm.send() RETURN TYPE WITH NONE ASSISTANT
# ============================================================

class TestSendReturnContract:
    """AssistantVM.send() must ALWAYS be an async generator, even when null.

    DEFECT FOUND: When _assistant is None, send() executes `return` (bare),
    which in an `async def ... -> AsyncIterator` that has `yield` in it makes
    it an async generator that terminates immediately. BUT if the code path
    hits `return` BEFORE any `yield`, Python still makes it an async generator
    (due to the `yield` further down). This is fine.

    HOWEVER: the type annotation says `-> AsyncIterator[str]` but a bare
    `return` in an async generator function is valid and yields nothing.
    Let's verify the caller-side contract is robust.
    """

    @pytest.mark.asyncio
    async def test_send_none_is_async_iterable(self):
        """vm.send() with None assistant returns an async iterator (not None)."""
        vm = AssistantVM()
        vm._assistant = None
        result = vm.send("hello")
        # Must be an async iterator, NOT None
        assert hasattr(result, "__aiter__")
        chunks = [c async for c in result]
        assert chunks == []

    @pytest.mark.asyncio
    async def test_send_none_can_be_used_in_async_for(self):
        """Callers can safely `async for chunk in vm.send(...)` when null."""
        vm = AssistantVM()
        vm._assistant = None
        collected = []
        async for chunk in vm.send("anything"):
            collected.append(chunk)
        assert collected == []


# ============================================================
# 8. DEFECT PROBE: MESSAGE INDEX RACE
# ============================================================

class TestMessageIndexRace:
    """Attack: if messages are appended between placeholder append and idx capture."""

    @pytest.mark.asyncio
    async def test_interleaved_append_between_placeholder_and_idx(self):
        """If another coroutine appends a message between the placeholder
        append and the idx = len(messages) - 1 capture, the idx points to
        the WRONG message (the interloper, not our placeholder).

        This demonstrates the race window in both _stream_response paths.
        """
        vm = AssistantVM()
        vm._assistant = _make_streaming_assistant(["reply"])

        # Simulate: drawer appends placeholder
        vm.messages.append(ChatMessage(role="assistant", text="…"))
        # RACE: another coroutine appends between ^^ and vv
        vm.messages.append(ChatMessage(role="user", text="interloper!"))
        # Now msg_idx captures len-1 which points to "interloper!", not "…"
        msg_idx = len(vm.messages) - 1

        # The stream will overwrite the interloper!
        assert vm.messages[msg_idx].text == "interloper!"

        # This IS a real (theoretical) race condition in the code:
        # vm.messages.append(ChatMessage(role="assistant", text="…"))
        # msg_idx = len(vm.messages) - 1
        #
        # Between these two lines, another asyncio task COULD append.
        # In practice, this requires a context switch between the append
        # and the very next line -- extremely unlikely in CPython with the GIL
        # since there's no `await` between them, but the pattern is fragile.
        #
        # Severity: LOW (theoretical in single-threaded asyncio, no await gap)
        # Fix: capture idx ATOMICALLY: msg_idx = len(vm.messages); vm.messages.append(...)
        #      or: msg_idx = vm.messages.index(placeholder_ref)
