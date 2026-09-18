"""Library chrome components: nav rail, filter bar, A-Z index, layout.

Pure view-builders. Tokens from theme. Icons carry tooltips.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

import flet as ft

from . import theme as T

if TYPE_CHECKING:
    from .global_settings_vm import GlobalSettingsVM


@dataclass(frozen=True)
class NavItem:
    route_id: str
    icon: ft.Icons
    label: str
    tooltip: str


# Default nav items -- data-driven, single source of truth.
NAV_ITEMS = [
    NavItem(route_id="library", icon=ft.Icons.GRID_VIEW_ROUNDED, label="Library", tooltip="Game library"),
    NavItem(route_id="systems", icon=ft.Icons.MEMORY, label="Systems", tooltip="Browse by console"),
    NavItem(route_id="import", icon=ft.Icons.DOWNLOAD_ROUNDED, label="Import", tooltip="Import games"),
    NavItem(route_id="controllers", icon=ft.Icons.SPORTS_ESPORTS, label="Controllers", tooltip="Controller mapping"),
    NavItem(route_id="cores", icon=ft.Icons.EXTENSION, label="Cores", tooltip="Cores & updates"),
    NavItem(route_id="settings", icon=ft.Icons.TUNE, label="Settings", tooltip="Settings"),
    NavItem(route_id="information", icon=ft.Icons.INFO_OUTLINE, label="Info", tooltip="System information"),
    NavItem(route_id="assistant", icon=ft.Icons.AUTO_AWESOME, label="Assistant", tooltip="AI assistant"),
]


def nav_rail(
    items: list[NavItem],
    *,
    selected: str,
    on_select: Callable[[str], None],
) -> ft.NavigationRail:
    """Vertical navigation rail with tooltip on each destination.

    Labels show ONLY on the selected item (Polycade-style: icons dominate,
    active gets a label). No decorative leading icon: every visible rail icon
    is a real destination.
    """
    selected_idx = next((i for i, it in enumerate(items) if it.route_id == selected), 0)

    destinations = [
        ft.NavigationRailDestination(
            icon=it.icon,
            selected_icon=it.icon,
            label=it.label,
            tooltip=it.tooltip,
        )
        for it in items
    ]

    def _on_change(e: ft.ControlEvent) -> None:
        idx = int(e.data)
        on_select(items[idx].route_id)

    return ft.NavigationRail(
        selected_index=selected_idx,
        label_type=ft.NavigationRailLabelType.SELECTED,
        min_width=T.NAV_WIDTH,
        bgcolor=T.BG_SURFACE,
        # Vibrant active pill behind the selected destination's icon.
        indicator_color=ft.Colors.with_opacity(0.28, T.ACCENT),
        destinations=destinations,
        on_change=_on_change,
    )


def filter_bar(
    systems: list[str],
    *,
    active: str | None = None,
    on_select: Callable[[str | None], None],
) -> ft.Row:
    """Horizontal chip row: 'All' + one per system. Active chip highlighted."""

    def _chip(label: str, is_active: bool, value: str | None) -> ft.Container:
        return ft.Container(
            padding=ft.Padding(T.SP_8, T.SP_12, T.SP_8, T.SP_12),
            border_radius=T.SP_16,
            bgcolor=T.ACCENT if is_active else T.BG_SURFACE,
            on_click=lambda _: on_select(value),
            content=ft.Text(
                label,
                size=T.SYSTEM_SIZE,
                color=T.TEXT_PRIMARY if is_active else T.TEXT_MUTED,
                weight=ft.FontWeight("w600" if is_active else "w400"),
            ),
        )

    chips = [_chip("All", active is None, None)]
    chips.extend(_chip(s, active == s, s) for s in systems)
    return ft.Row(controls=chips, spacing=T.SP_8, height=T.FILTER_HEIGHT)


def search_field(*, on_change: Callable[[str], None]) -> ft.TextField:
    """Inline search field for live-filtering the library grid."""
    return ft.TextField(
        hint_text="Search games...",
        prefix_icon=ft.Icons.SEARCH,
        border_radius=T.SP_8,
        bgcolor=T.BG_SURFACE,
        color=T.TEXT_PRIMARY,
        hint_style=ft.TextStyle(color=T.TEXT_MUTED),
        height=40,
        text_size=14,
        content_padding=ft.Padding(T.SP_8, 0, T.SP_8, 0),
        on_change=lambda e: on_change(e.control.value),
    )


def az_index(
    letters: list[str],
    *,
    on_jump: Callable[[str], None],
) -> ft.Column:
    """Vertical A-Z strip. Only present letters clickable."""
    controls = [
        ft.Container(
            width=T.AZ_WIDTH,
            alignment=ft.Alignment.CENTER,
            on_click=lambda _, ltr=ltr: on_jump(ltr),
            content=ft.Text(
                ltr, size=10, color=T.TEXT_MUTED, text_align=ft.TextAlign.CENTER
            ),
        )
        for ltr in letters
    ]
    return ft.Column(
        controls=controls,
        spacing=2,
        width=T.AZ_WIDTH,
        alignment=ft.MainAxisAlignment.START,
    )


@dataclass(frozen=True)
class HintAction:
    icon: ft.Icons
    label: str


def hint_bar(actions: list[HintAction]) -> ft.Row:
    """Bottom controller hint bar. AA contrast, icon + text label (never icon-only)."""
    chips = [
        ft.Row(
            spacing=T.SP_4,
            controls=[
                ft.Icon(a.icon, size=16, color=T.TEXT_MUTED),
                ft.Text(a.label, size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
            ],
        )
        for a in actions
    ]
    return ft.Row(
        controls=chips,
        spacing=T.SP_16,
        height=36,
        alignment=ft.MainAxisAlignment.CENTER,
    )


# --- Context-sensitive hint presets ---

HINTS_WALL = [
    HintAction(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, label="Select"),
    HintAction(icon=ft.Icons.FILTER_LIST, label="Filter"),
]

HINTS_DETAIL = [
    HintAction(icon=ft.Icons.PLAY_ARROW, label="Play"),
    HintAction(icon=ft.Icons.ARROW_BACK, label="Back"),
]


def library_view(
    filter_bar: ft.Row,
    search: ft.TextField,
    az_index: ft.Column,
    grid: ft.Control,
    *,
    hints: list[HintAction] | None = None,
    accent: str | None = None,
    hero_art: str | None = None,
) -> ft.Container:
    """Compose: [search(top) + filter_bar + grid(expand) + hints(bottom)] | az(right).

    Cinematic backdrop (layered, bottom to top):
      1. the focused game's art, full-bleed (when hero_art given);
      2. a blur + dark scrim so it reads as an out-of-focus ambient wash;
      3. a system-tinted radial glow (top-center);
      4. the interactive body (search / filter / grid / a-z).
    Rail is NOT composed here -- it lives at Navigator level.
    """
    children: list[ft.Control] = [search, filter_bar, ft.Container(content=grid, expand=True)]
    if hints:
        children.append(hint_bar(hints))
    center = ft.Column(expand=True, spacing=T.SP_8, controls=children)
    body = ft.Row(
        expand=True,
        spacing=0,
        controls=[center, az_index],
    )
    tint = accent or T.ACCENT
    tint_glow = ft.Container(
        expand=True,
        gradient=ft.RadialGradient(
            center=ft.Alignment.TOP_CENTER,
            radius=1.5,
            colors=[ft.Colors.with_opacity(0.22, tint), "transparent"],
            stops=[0.0, 0.72],
        ),
    )
    layers: list[ft.Control] = []
    if hero_art:
        layers.append(ft.Image(src=hero_art, fit="cover", expand=True))
        # Blur the art behind + dim it so foreground tiles stay legible.
        layers.append(
            ft.Container(
                expand=True,
                blur=ft.Blur(24, 24),
                bgcolor=ft.Colors.with_opacity(0.45, T.BG_BASE),
            )
        )
    layers.append(tint_glow)
    layers.append(body)
    return ft.Container(
        expand=True,
        bgcolor=T.BG_BASE,
        content=ft.Stack(expand=True, controls=layers),
    )


# --- Shared helpers ---


def runahead_toggle_row(
    *,
    enabled: bool,
    on_change: Callable[[bool], None] | None = None,
) -> ft.Row:
    """Global or per-game Run-Ahead toggle. Shared to avoid drift."""
    return ft.Row(
        spacing=T.SP_12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Column(
                spacing=2,
                expand=True,
                controls=[
                    ft.Text("Run-Ahead", size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
                    ft.Text("Reduces input latency", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
                ],
            ),
            ft.Switch(
                value=enabled,
                active_color=T.ACCENT,
                on_change=(lambda e: on_change(e.control.value)) if on_change else None,
            ),
        ],
    )


# --- Settings Screen ---


def _settings_section(
    title: str,
    rows: "tuple",
    *,
    on_change: "Callable[[str, str], None] | None" = None,
) -> ft.Column:
    """Render a settings section (Video / Audio / Latency) from VM rows."""
    from .components import editable_dropdown_row, editable_toggle_row

    controls: list[ft.Control] = [
        ft.Text(title, size=16, weight=ft.FontWeight("w700"), color=T.TEXT_PRIMARY),
    ]
    for row in rows:
        if row.is_toggle:
            controls.append(editable_toggle_row(
                row.label,
                row.current == "true",
                on_change=lambda val, k=row.key: on_change(k, "true" if val else "false") if on_change else None,
                tooltip=f"{row.label} ({row.key})",
            ))
        else:
            controls.append(editable_dropdown_row(
                row.label,
                row.current,
                row.choices,
                on_change=lambda val, k=row.key: on_change(k, val) if on_change else None,
                tooltip=f"{row.label} ({row.key})",
            ))
    return ft.Column(spacing=T.SP_12, controls=controls)


def settings_view(
    *,
    global_settings_vm: "GlobalSettingsVM | None" = None,
    on_setting_change: "Callable[[str, str], None] | None" = None,
    config_dir_text: str,
    version: str = "0.1.0",
    assistant_section: "ft.Control | None" = None,
) -> ft.Container:
    """Settings screen content (body only -- rail lives at Navigator level).

    Renders Video / Audio / Latency sections from GlobalSettingsVM.
    Falls back to placeholder if VM is None (no config dir).
    """
    if TYPE_CHECKING:
        from .global_settings_vm import GlobalSettingsVM  # noqa: F811

    sections: list[ft.Control] = [
        ft.Text("Settings", size=22, weight=ft.FontWeight("w700"), color=T.TEXT_PRIMARY),
    ]

    if global_settings_vm is not None:
        sections.append(_settings_section(
            global_settings_vm.video.title,
            global_settings_vm.video.rows,
            on_change=on_setting_change,
        ))
        sections.append(ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
        sections.append(_settings_section(
            global_settings_vm.audio.title,
            global_settings_vm.audio.rows,
            on_change=on_setting_change,
        ))
        sections.append(ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
        sections.append(_settings_section(
            global_settings_vm.latency.title,
            global_settings_vm.latency.rows,
            on_change=on_setting_change,
        ))
    else:
        sections.append(ft.Text("No config directory configured", size=14, color=T.TEXT_MUTED))

    sections.append(ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)))
    if assistant_section is not None:
        sections.append(assistant_section)
        sections.append(ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)))
    sections.append(ft.Column(spacing=T.SP_4, controls=[
        ft.Text("About", size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
        ft.Text(f"Config: {config_dir_text}", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
        ft.Text(f"Version: {version}", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
    ]))

    content = ft.Column(
        expand=True,
        spacing=T.SP_16,
        scroll=ft.ScrollMode.AUTO,
        controls=sections,
    )

    return ft.Container(content=content, expand=True, padding=T.SP_16 * 2)


def systems_view(
    systems: list[str],
    *,
    on_select: Callable[[str], None],
) -> ft.Container:
    """Systems browse screen: list of consoles. Selecting one navigates to filtered library."""
    chips = [
        ft.Container(
            padding=ft.Padding(T.SP_16, T.SP_12, T.SP_16, T.SP_12),
            border_radius=T.SP_8,
            bgcolor=T.BG_SURFACE,
            on_click=lambda _, s=s: on_select(s),
            content=ft.Row(
                spacing=T.SP_8,
                controls=[
                    ft.Icon(ft.Icons.VIDEOGAME_ASSET, color=T.ACCENT, size=20),
                    ft.Text(s, size=16, color=T.TEXT_PRIMARY, weight=ft.FontWeight("w500")),
                ],
            ),
        )
        for s in systems
    ]
    return ft.Container(
        expand=True,
        padding=T.SP_16 * 2,
        content=ft.Column(
            spacing=T.SP_8,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("Systems", size=22, weight=ft.FontWeight("w700"), color=T.TEXT_PRIMARY),
                ft.Column(spacing=T.SP_8, controls=chips),
            ],
        ),
    )


# --- Cores & Updates Screen ---

@dataclass(frozen=True)
class CoreRow:
    """View-model row for the cores list."""
    display_name: str
    system_name: str
    filename: str
    size_label: str


def cores_view(
    cores: list[CoreRow],
    *,
    on_install: Callable[[str], None] | None = None,
    install_disabled: bool = False,
    status_message: str = "",
) -> ft.Container:
    """Cores & Updates screen: list installed cores + optional install action.

    Minimalist design: core list with name/system/size, install-by-name field.
    Honest empty state when no cores found.
    """
    sections: list[ft.Control] = [
        ft.Text("Cores & Updates", size=22, weight=ft.FontWeight("w700"), color=T.TEXT_PRIMARY),
    ]

    if status_message:
        sections.append(ft.Text(status_message, size=T.SYSTEM_SIZE, color=T.ACCENT_TEXT))

    if cores:
        rows: list[ft.Control] = []
        for c in cores:
            rows.append(ft.Container(
                padding=ft.Padding(T.SP_12, T.SP_8, T.SP_12, T.SP_8),
                border_radius=T.SP_8,
                bgcolor=T.BG_SURFACE,
                content=ft.Row(
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    controls=[
                        ft.Column(
                            spacing=2,
                            controls=[
                                ft.Text(c.display_name, size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
                                ft.Text(
                                    c.system_name or c.filename,
                                    size=T.SYSTEM_SIZE, color=T.TEXT_MUTED,
                                ),
                            ],
                        ),
                        ft.Text(c.size_label, size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
                    ],
                ),
            ))
        sections.append(ft.Column(spacing=T.SP_8, controls=rows))
    else:
        sections.append(ft.Text("No cores installed", size=14, color=T.TEXT_MUTED))

    # Install section (hidden when disabled)
    if not install_disabled and on_install is not None:
        install_field = ft.TextField(
            hint_text="Core name (e.g. snes9x)",
            prefix_icon=ft.Icons.DOWNLOAD,
            border_radius=T.SP_8,
            bgcolor=T.BG_SURFACE,
            color=T.TEXT_PRIMARY,
            hint_style=ft.TextStyle(color=T.TEXT_MUTED),
            height=40,
            text_size=14,
            content_padding=ft.Padding(T.SP_8, 0, T.SP_8, 0),
            on_submit=lambda e: on_install(e.control.value) if e.control.value else None,
        )
        sections.append(ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
        sections.append(ft.Column(spacing=T.SP_8, controls=[
            ft.Text("Install Core", size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
            install_field,
            ft.Text(
                "Enter a core name and press Enter to download from buildbot.",
                size=T.SYSTEM_SIZE, color=T.TEXT_MUTED,
            ),
        ]))

    content = ft.Column(
        expand=True,
        spacing=T.SP_16,
        scroll=ft.ScrollMode.AUTO,
        controls=sections,
    )

    return ft.Container(content=content, expand=True, padding=T.SP_16 * 2)
