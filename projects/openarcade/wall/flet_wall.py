"""Bespoke wall renderer -- bypasses generic FletAdapter CARD (cannot express Stack/scrim/badge). See B13."""

import hashlib

import flet as ft

from .models import GameTile, WallViewModel
from . import theme as T


def _hsl_to_hex(h: int, s: int, l: int) -> str:
    """Convert HSL (h:0-360, s:0-100, l:0-100) to #RRGGBB hex."""
    s_f, l_f = s / 100, l / 100
    c = (1 - abs(2 * l_f - 1)) * s_f
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l_f - c / 2
    if h < 60:
        r, g, b = c, x, 0.0
    elif h < 120:
        r, g, b = x, c, 0.0
    elif h < 180:
        r, g, b = 0.0, c, x
    elif h < 240:
        r, g, b = 0.0, x, c
    elif h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    return "#{:02x}{:02x}{:02x}".format(
        int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)
    )


def placeholder_gradient(system: str) -> tuple[str, str]:
    """Deterministic gradient pair for a system. Stable across runs."""
    hue = int(hashlib.sha1(system.encode()).hexdigest(), 16) % 360
    primary = _hsl_to_hex(hue, 55, 25)
    secondary = _hsl_to_hex((hue + 40) % 360, 45, 15)
    return primary, secondary


def _build_placeholder(system: str) -> ft.Container:
    """Procedural placeholder: gradient + centered system-initials watermark."""
    c1, c2 = placeholder_gradient(system)
    initials = system[:3].upper() if system else "?"
    return ft.Container(
        expand=True,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[c1, c2],
        ),
        alignment=ft.Alignment.CENTER,
        content=ft.Text(
            initials,
            size=T.WATERMARK_SIZE,
            weight=ft.FontWeight(T.WATERMARK_WEIGHT),
            color="#FFFFFF14",  # white @ ~8%
        ),
    )


def _build_art(tile: GameTile) -> ft.Control:
    """Box art image or procedural placeholder."""
    if tile.art_url:
        return ft.Image(src=tile.art_url, fit="cover", expand=True)
    return _build_placeholder(tile.system)


def _build_scrim() -> ft.Container:
    """Bottom ~40% gradient scrim for text legibility."""
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.BOTTOM_LEFT,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[T.SCRIM_TOP, T.SCRIM_BOTTOM],
        ),
    )


def _build_system_chip(system: str) -> ft.Container:
    """Top-left system chip."""
    return ft.Container(
        top=T.SP_8,
        left=T.SP_8,
        padding=ft.Padding(left=T.SP_8, right=T.SP_8, top=T.SP_4, bottom=T.SP_4),
        border_radius=T.SP_4,
        bgcolor=T.BG_SURFACE,
        content=ft.Text(system, size=T.SYSTEM_SIZE, weight=ft.FontWeight(T.SYSTEM_WEIGHT), color=T.TEXT_MUTED),
    )


def _build_title_block(tile: GameTile) -> ft.Container:
    """Bottom-left title + system line."""
    return ft.Container(
        bottom=T.SP_12,
        left=T.SP_12,
        right=T.SP_12,
        content=ft.Column(
            spacing=2,
            controls=[
                ft.Text(tile.title, size=T.TITLE_SIZE, weight=ft.FontWeight(T.TITLE_WEIGHT), color=T.TEXT_PRIMARY),
                ft.Text(tile.system, size=T.SYSTEM_SIZE, weight=ft.FontWeight(T.SYSTEM_WEIGHT), color=T.TEXT_MUTED),
            ],
        ),
    )


def _build_lock_badge(tile: GameTile) -> ft.Container:
    """Top-right lock badge for not-playable tiles."""
    return ft.Container(
        top=T.SP_8,
        right=T.SP_8,
        width=T.LOCK_BADGE_SIZE,
        height=T.LOCK_BADGE_SIZE,
        border_radius=T.LOCK_BADGE_SIZE // 2,
        bgcolor=T.LOCK_BADGE_BG,
        alignment=ft.Alignment.CENTER,
        tooltip=tile.status_detail or "Not playable",
        content=ft.Icon(ft.Icons.LOCK_OUTLINE, size=T.LOCK_ICON_SIZE, color=T.LOCK_BADGE_COLOR),
    )


def render_tile(tile: GameTile) -> ft.Container:
    """Build a single tile per the design spec."""
    art = _build_art(tile)
    opacity = T.NOT_PLAYABLE_OPACITY if not tile.playable else 1.0

    stack_controls: list[ft.Control] = [
        ft.Container(content=art, expand=True, opacity=opacity),
        _build_scrim(),
        _build_system_chip(tile.system),
        _build_title_block(tile),
    ]
    if not tile.playable:
        stack_controls.append(_build_lock_badge(tile))

    return ft.Container(
        border_radius=T.RADIUS,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        bgcolor=T.BG_SURFACE,
        content=ft.Stack(controls=stack_controls, expand=True),
    )


def render_wall(vm: WallViewModel) -> ft.GridView:
    """Render the full wall grid from a WallViewModel."""
    return ft.GridView(
        runs_count=vm.columns,
        spacing=T.SP_12,
        run_spacing=T.SP_12,
        child_aspect_ratio=T.TILE_ASPECT,
        controls=[render_tile(t) for t in vm.tiles],
    )
