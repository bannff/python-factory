"""AI Assistant chat panel — minimalist Flet surface.

Pure view assembly: scrollable message list (user vs assistant bubbles) + text
input with a send affordance. No business logic, no IO. The caller (navigator)
drives the AssistantLoop protocol and feeds messages + on_send into this builder.

Design: one accent color, clear hierarchy, WCAG AA, keyboard accessible,
respects prefers-reduced-motion via Flet's built-in system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from . import theme as T


@dataclass(frozen=True)
class ChatMessage:
    """Single chat message bubble data."""

    role: str  # "user" | "assistant"
    text: str


def _message_bubble(msg: ChatMessage) -> ft.Container:
    """Render a single message as a styled bubble with role-based alignment."""
    is_user = msg.role == "user"
    return ft.Container(
        padding=ft.Padding(T.SP_12, T.SP_8, T.SP_12, T.SP_8),
        border_radius=T.SP_12,
        bgcolor=T.ACCENT if is_user else T.BG_SURFACE,
        alignment=ft.Alignment.CENTER_RIGHT if is_user else ft.Alignment.CENTER_LEFT,
        margin=ft.Margin(
            left=64 if is_user else 0,
            top=T.SP_4,
            right=0 if is_user else 64,
            bottom=T.SP_4,
        ),
        content=ft.Text(
            msg.text,
            size=14,
            color=T.TEXT_PRIMARY,
            selectable=True,
        ),
    )


def _empty_state(reason: str) -> ft.Container:
    """Honest empty state — calm, informative, no dead controls."""
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=T.SP_12,
            controls=[
                ft.Icon(ft.Icons.SMART_TOY, size=48, color=T.TEXT_MUTED),
                ft.Text(
                    reason,
                    size=14,
                    color=T.TEXT_MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
        ),
    )


def assistant_panel(
    messages: list[ChatMessage],
    *,
    on_send: Callable[[str], None],
    enabled: bool = True,
    empty_reason: str = "",
    show_header: bool = True,
) -> ft.Container:
    """Build the assistant chat panel.

    Args:
        messages: Ordered chat history to display.
        on_send: Callback when user submits a message.
        enabled: If False, shows the empty_reason state instead of the chat.
        empty_reason: Message to display when disabled (e.g. model not configured).
        show_header: If False, omit the built-in "Assistant" title (the drawer
            overlay supplies its own header, so we avoid a duplicate label).

    Returns:
        A Container with the full panel (expand=True).
    """
    if not enabled:
        return _empty_state(empty_reason)

    # Message list — scrollable, newest at bottom
    bubbles = [_message_bubble(m) for m in messages]
    message_list = ft.ListView(
        controls=bubbles,
        expand=True,
        spacing=T.SP_4,
        auto_scroll=True,
    )

    # Input row: text field + send button
    input_field = ft.TextField(
        hint_text="Ask the assistant...",
        border_radius=T.SP_8,
        bgcolor=T.BG_SURFACE,
        color=T.TEXT_PRIMARY,
        hint_style=ft.TextStyle(color=T.TEXT_MUTED),
        text_size=14,
        expand=True,
        content_padding=ft.Padding(T.SP_12, 0, T.SP_12, 0),
        on_submit=lambda e: _handle_send(e.control),
        autofocus=True,
    )

    def _handle_send(field: ft.TextField) -> None:
        text = (field.value or "").strip()
        if text:
            on_send(text)
            field.value = ""
            try:
                field.update()
            except RuntimeError:
                pass

    send_button = ft.IconButton(
        icon=ft.Icons.SEND,
        icon_color=T.ACCENT,
        tooltip="Send message",
        on_click=lambda _: _handle_send(input_field),
    )

    input_row = ft.Row(
        spacing=T.SP_8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[input_field, send_button],
    )

    # Compose: (optional header) + messages (expand) + input
    header = ft.Text(
        "Assistant",
        size=18,
        weight=ft.FontWeight("w700"),
        color=T.TEXT_PRIMARY,
    )

    column_controls = [message_list, input_row]
    if show_header:
        column_controls.insert(0, header)

    return ft.Container(
        expand=True,
        padding=T.SP_16 * 2,
        content=ft.Column(
            expand=True,
            spacing=T.SP_12,
            controls=column_controls,
        ),
    )
