"""Chat overlay builder — floating action button + slide-in drawer.

Produces the two controls (drawer Container + FAB) that mount in the root
Stack. The drawer is a PERSISTENT mounted Container that toggles via
animate_offset (slide right to hide, to 0 to show). The FAB toggles it.

Depends on: Navigator (for page update), AssistantVM (shared state).
Navigator does NOT import this module — app.py composes both.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import flet as ft

from .assistant_panel import assistant_panel, ChatMessage
from .assistant_vm import AssistantVM
from . import theme as T

if TYPE_CHECKING:
    from .navigator import Navigator

_DRAWER_WIDTH = 400
_DRAWER_WIDE = 640
_FAB_SIZE = 56
_FAB_MARGIN = 24


def build_chat_overlay(
    nav: "Navigator",
    assistant_vm: AssistantVM,
) -> tuple[ft.Container, ft.Container]:
    """Build (drawer_container, fab_container).

    Both are added to the root Stack. The drawer slides in from the right;
    the FAB sits bottom-right and toggles the drawer.

    Returns:
        (drawer, fab) — two Controls for the Stack.
    """
    # --- Drawer state (local to this overlay instance) ---
    drawer_open = [False]  # mutable cell for closure
    drawer_wide = [False]  # wide-mode toggle

    # --- Drawer body rebuilder ---
    def _build_drawer_body() -> ft.Control:
        """Build the inner content of the drawer from shared AssistantVM."""

        def _on_send(text: str) -> None:
            assistant_vm.messages.append(ChatMessage(role="user", text=text))
            _refresh_drawer()
            # Stream in background
            page = nav._page
            if page:
                page.run_task(_stream_response, text)

        chat = assistant_panel(
            assistant_vm.messages,
            on_send=_on_send,
            enabled=not assistant_vm.is_null,
            empty_reason="Configure the assistant in Settings → Assistant.",
            show_header=False,
        )
        # Close button + wide-mode toggle at top
        close_btn = ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_color=T.TEXT_MUTED,
            tooltip="Close assistant drawer",
            on_click=lambda _: _toggle_drawer(),
        )
        wide_btn = ft.IconButton(
            icon=ft.Icons.WIDTH_WIDE if not drawer_wide[0] else ft.Icons.WIDTH_NORMAL,
            icon_color=T.TEXT_MUTED,
            tooltip="Wide mode" if not drawer_wide[0] else "Narrow mode",
            on_click=lambda _: _toggle_wide(),
        )
        header = ft.Row(
            controls=[
                ft.Text("Assistant", size=16, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
                ft.Container(expand=True),
                wide_btn,
                close_btn,
            ],
        )
        return ft.Column(
            expand=True,
            spacing=0,
            controls=[
                ft.Container(content=header, padding=ft.Padding(T.SP_16, T.SP_12, T.SP_8, 0)),
                ft.Container(content=chat, expand=True, padding=ft.Padding(T.SP_12, 0, T.SP_12, T.SP_12)),
            ],
        )

    async def _stream_response(text: str) -> None:
        """Stream assistant response, updating shared VM + drawer."""
        msg_idx = len(assistant_vm.messages)
        assistant_vm.messages.append(ChatMessage(role="assistant", text="…"))
        accumulated = ""
        try:
            async for chunk in assistant_vm.send(text):
                accumulated += chunk
                assistant_vm.messages[msg_idx] = ChatMessage(
                    role="assistant", text=accumulated or "…"
                )
                _refresh_drawer()
                # Also refresh the landing page if it's active
                nav._try_update()
        except Exception as exc:
            assistant_vm.messages[msg_idx] = ChatMessage(
                role="assistant", text=f"⚠ Assistant error: {exc}"
            )
            _refresh_drawer()
            nav._try_update()
        if not accumulated and msg_idx < len(assistant_vm.messages):
            assistant_vm.messages[msg_idx] = ChatMessage(
                role="assistant",
                text="(No response — check model and provider in Settings.)",
            )
            _refresh_drawer()
            nav._try_update()

    # --- Drawer container (persistent, toggles offset) ---
    drawer_content = ft.Container(
        content=_build_drawer_body(),
        expand=True,
    )

    drawer = ft.Container(
        width=_DRAWER_WIDTH,
        height=None,  # full height via Stack alignment
        bgcolor=T.BG_SURFACE,
        border=ft.Border(left=ft.BorderSide(1, ft.Colors.with_opacity(0.1, ft.Colors.WHITE))),
        border_radius=ft.BorderRadius(T.SP_12, 0, 0, T.SP_12),
        content=drawer_content,
        # Start hidden (offset right, off-screen)
        offset=ft.Offset(1.0, 0),
        animate_offset=ft.Animation(250, ft.AnimationCurve.EASE_OUT),
        animate=ft.Animation(200, ft.AnimationCurve.EASE_OUT),
        right=0,
        top=0,
        bottom=0,
    )

    # --- FAB ---
    fab_button = ft.FloatingActionButton(
        icon=ft.Icons.SMART_TOY,
        bgcolor=T.ACCENT,
        tooltip="Assistant",
        mini=False,
        on_click=lambda _: _toggle_drawer(),
    )

    fab = ft.Container(
        content=fab_button,
        right=_FAB_MARGIN,
        bottom=_FAB_MARGIN,
    )

    # --- Toggle logic ---
    def _toggle_drawer() -> None:
        drawer_open[0] = not drawer_open[0]
        if drawer_open[0]:
            drawer.offset = ft.Offset(0, 0)
            # Refresh body content to reflect latest messages
            drawer_content.content = _build_drawer_body()
        else:
            drawer.offset = ft.Offset(1.0, 0)
        try:
            drawer.update()
            drawer_content.update()
        except RuntimeError:
            pass

    def _toggle_wide() -> None:
        """Switch between narrow (400px) and wide (640px) drawer."""
        drawer_wide[0] = not drawer_wide[0]
        drawer.width = _DRAWER_WIDE if drawer_wide[0] else _DRAWER_WIDTH
        # Rebuild body to update the toggle icon state
        drawer_content.content = _build_drawer_body()
        try:
            drawer.update()
            drawer_content.update()
        except RuntimeError:
            pass

    def _refresh_drawer() -> None:
        """Rebuild drawer body with latest messages."""
        drawer_content.content = _build_drawer_body()
        try:
            drawer_content.update()
        except RuntimeError:
            pass

    # Expose toggle for testing
    drawer.toggle = _toggle_drawer  # type: ignore[attr-defined]
    drawer.is_open = lambda: drawer_open[0]  # type: ignore[attr-defined]
    drawer.toggle_wide = _toggle_wide  # type: ignore[attr-defined]
    drawer.is_wide = lambda: drawer_wide[0]  # type: ignore[attr-defined]

    return drawer, fab
