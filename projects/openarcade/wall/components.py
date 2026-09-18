"""Reusable Flet view-builder components. Pure (return ft.Control, no side-effects).

FIX: opacity bug -- uses ft.Colors.with_opacity, NEVER raw "#FFFFFF14" (ARGB trap).
"""

from __future__ import annotations

import hashlib
from typing import Callable, TYPE_CHECKING

import flet as ft
import flet_video as fv

from .models import GameTile
from .controls_vm import ControlsVM, controls_from_settings
from . import theme as T

if TYPE_CHECKING:
    from .assistant_settings_vm import AssistantSettingsVM


# --- Helpers ---


def _system_gradient(system: str) -> tuple[str, str]:
    """Deterministic gradient pair from system name."""
    hue = int(hashlib.sha1(system.encode()).hexdigest(), 16) % 360
    from .flet_wall import _hsl_to_hex

    primary = _hsl_to_hex(hue, 55, 25)
    secondary = _hsl_to_hex((hue + 40) % 360, 45, 15)
    return primary, secondary


def system_accent(system: str | None) -> str:
    """Public accent color for a system (or the neutral ACCENT for None/All).

    Reuses the deterministic per-system palette so the wall's ambient tint
    matches the tile chips.
    """
    if not system:
        return T.ACCENT
    primary, _ = _system_gradient(system)
    return primary


def _or_dash(value: str) -> str:
    """Return value or '--' for empty string."""
    return value if value else "--"


# --- Core Components (B14) ---


def hover_container(
    content: ft.Control,
    *,
    scale_to: float = 1.04,
    glow_color: str = T.ACCENT,
    is_selected: bool = False,
) -> ft.Container:
    """Wrap content with hover lift+scale+glow animation. Token-driven, declarative.

    When is_selected=True the container renders in the SAME visual state as
    hover (scale=scale_to, glow_shadow) persistently -- independent of actual
    mouse hover. Mouse hover still works normally on non-selected cards.
    """

    # Resting depth: soft downward shadow so cards read as raised, not flat.
    resting_shadow = ft.BoxShadow(
        spread_radius=0,
        blur_radius=22,
        offset=ft.Offset(0, 10),
        color=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
    )
    # Hover: accent glow bloom.
    glow_shadow = ft.BoxShadow(
        spread_radius=3,
        blur_radius=32,
        color=ft.Colors.with_opacity(0.55, glow_color),
    )

    # Initial state: selected cards start in "hover-equivalent" state.
    initial_scale = scale_to if is_selected else 1.0
    initial_shadow = glow_shadow if is_selected else resting_shadow

    def _on_hover(e: ft.ControlEvent) -> None:
        c = e.control
        if e.data == "true":
            c.scale = scale_to
            c.shadow = glow_shadow
        else:
            # When selected, fall back to selected (hover-equiv) state, not resting.
            if is_selected:
                c.scale = scale_to
                c.shadow = glow_shadow
            else:
                c.scale = 1.0
                c.shadow = resting_shadow  # keep depth, don't go flat
        c.update()

    return ft.Container(
        content=content,
        scale=initial_scale,
        opacity=1.0,
        animate_scale=ft.Animation(T.duration(T.DURATION_SPRING), T.CURVE_SPRING),
        animate_opacity=ft.Animation(T.duration(T.DURATION_FAST), T.CURVE_STANDARD),
        shadow=initial_shadow,
        on_hover=_on_hover,
    )


def placeholder_card(title: str, system: str) -> ft.Container:
    """Title-forward placeholder (game title prominent, system small chip)."""
    c1, c2 = _system_gradient(system)
    return ft.Container(
        expand=True,
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[c1, c2],
        ),
        alignment=ft.Alignment.CENTER,
        padding=T.SP_16,
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=T.SP_8,
            controls=[
                ft.Text(
                    title,
                    size=T.TITLE_SIZE,
                    weight=ft.FontWeight(T.TITLE_WEIGHT),
                    color=T.TEXT_PRIMARY,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(
                    padding=ft.Padding(T.SP_4, T.SP_8, T.SP_4, T.SP_8),
                    border_radius=T.SP_4,
                    bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.WHITE),
                    content=ft.Text(
                        system,
                        size=T.SYSTEM_SIZE,
                        weight=ft.FontWeight(T.SYSTEM_WEIGHT),
                        color=T.TEXT_MUTED,
                    ),
                ),
            ],
        ),
    )


def _bounded_art_region(game: GameTile, *, allow_video: bool = False) -> ft.Container:
    """Bounded art region: cover-fit + clip. Parent Column gives height; art fills uniformly.

    Reusable primitive -- Detail hero calls with allow_video=True for video-snap attract.
    Wall tiles default allow_video=False (no Video instantiation -> no perf risk).
    """
    if allow_video and game.video_url:
        art_content: ft.Control = fv.Video(
            playlist=[fv.VideoMedia(resource=game.video_url)],
            autoplay=True,
            muted=True,
            playlist_mode=fv.PlaylistMode.LOOP,
            fit="cover",
            show_controls=False,
            expand=True,
        )
    elif game.art_url:
        art_content = ft.Image(
            src=game.art_url, fit="contain", expand=True
        )
    else:
        art_content = placeholder_card(game.title, game.system)

    art_opacity = T.NOT_PLAYABLE_OPACITY if not game.playable else 1.0

    chip = ft.Container(
        top=T.SP_8,
        left=T.SP_8,
        padding=ft.Padding(T.SP_4, T.SP_8, T.SP_4, T.SP_8),
        border_radius=T.SP_4,
        bgcolor=T.BG_SURFACE,
        content=ft.Text(
            game.system,
            size=T.SYSTEM_SIZE,
            weight=ft.FontWeight(T.SYSTEM_WEIGHT),
            color=T.TEXT_MUTED,
        ),
    )

    stack_controls: list[ft.Control] = [
        # Positioned.fill: pin to all 4 sides so the art fills the bounded Stack
        # region. (A non-positioned Stack child gets loose constraints and would
        # render at the image's natural size -> dead space.) cover-fit then fills.
        ft.Container(content=art_content, left=0, top=0, right=0, bottom=0, opacity=art_opacity),
        # Bottom scrim: fade the art into the surface color so it melts into the
        # title band below instead of ending on a hard edge.
        ft.Container(
            left=0,
            right=0,
            bottom=0,
            height=64,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.TOP_CENTER,
                end=ft.Alignment.BOTTOM_CENTER,
                colors=["#00000000", T.BG_SURFACE],
            ),
        ),
        chip,
    ]

    if not game.playable:
        stack_controls.append(
            ft.Container(
                top=T.SP_8,
                right=T.SP_8,
                width=T.LOCK_BADGE_SIZE,
                height=T.LOCK_BADGE_SIZE,
                border_radius=T.LOCK_BADGE_SIZE // 2,
                bgcolor=T.LOCK_BADGE_BG,
                alignment=ft.Alignment.CENTER,
                tooltip=game.status_detail or "Not playable",
                content=ft.Icon(
                    ft.Icons.LOCK_OUTLINE,
                    size=T.LOCK_ICON_SIZE,
                    color=T.LOCK_BADGE_COLOR,
                ),
            )
        )

    return ft.Container(
        expand=True,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=ft.Stack(expand=True, controls=stack_controls),
    )


def _title_band(game: GameTile) -> ft.Container:
    """Fixed-height title band: strong title + a system-colored chip."""
    c1, _ = _system_gradient(game.system)
    return ft.Container(
        height=T.TITLE_BAND_HEIGHT,
        padding=ft.Padding(T.SP_12, T.SP_8, T.SP_12, T.SP_8),
        content=ft.Column(
            spacing=4,
            alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    game.title,
                    size=T.TITLE_SIZE,
                    weight=ft.FontWeight(T.TITLE_WEIGHT),
                    color=T.TEXT_PRIMARY,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                ),
                # System as a colored pill (per-system accent), left-aligned + intrinsic width.
                ft.Row(
                    spacing=0,
                    controls=[
                        ft.Container(
                            padding=ft.Padding(T.SP_8, 2, T.SP_8, 2),
                            border_radius=6,
                            bgcolor=ft.Colors.with_opacity(0.9, c1),
                            content=ft.Text(
                                game.system.upper(),
                                size=10,
                                weight=ft.FontWeight("w700"),
                                color=T.TEXT_PRIMARY,
                            ),
                        ),
                    ],
                ),
            ],
        ),
    )


def tile(
    game: GameTile,
    *,
    focused: bool = False,
    on_click: Callable[[GameTile], None] | None = None,
) -> ft.Container:
    """Build a single game tile -- Column[art_region, title_band].

    Every tile is IDENTICAL size: the GridView cell bounds total height,
    art_region expands to fill remaining space (cover-fit + clip),
    title_band is fixed TITLE_BAND_HEIGHT.

    Focus ring fades in declaratively via animate_opacity (no pop).
    """
    inner = ft.Container(
        expand=True,
        border_radius=T.RADIUS,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        # Top-lit surface gradient so the card catches light and reads as raised.
        gradient=ft.LinearGradient(
            begin=ft.Alignment.TOP_CENTER,
            end=ft.Alignment.BOTTOM_CENTER,
            colors=[T.BG_SURFACE_HI, T.BG_SURFACE],
        ),
        # Hairline top-edge highlight (light catches the top rim).
        border=ft.Border.all(1, T.HAIRLINE),
        on_click=(lambda e, g=game: on_click(g)) if on_click else None,
        content=ft.Column(
            spacing=0,
            expand=True,
            controls=[_bounded_art_region(game), _title_band(game)],
        ),
    )

    # Focus ring: a wrapping container whose border fades in/out via opacity.
    focus_ring = ft.Container(
        content=inner,
        expand=True,
        border_radius=T.RADIUS,
        border=ft.Border.all(2, T.ACCENT) if focused else ft.Border.all(2, "transparent"),
        opacity=1.0 if focused else 0.0,
        animate_opacity=ft.Animation(T.duration(T.DURATION_FAST), T.CURVE_STANDARD),
    )

    # Outer: always-visible wrapper that carries the hover animation.
    # When focused, the ring is opaque; when not, it's hidden (opacity 0).
    # We nest: hover_container > focus_ring > inner.
    # But focus_ring.opacity hides the BORDER only; we need content always visible.
    # So: compose as container with border opacity for the ring + full inner.
    outer = ft.Container(
        expand=True,
        border_radius=T.RADIUS,
        border=ft.Border.all(2, T.ACCENT),
        opacity=1.0 if focused else 0.0,
        animate_opacity=ft.Animation(T.duration(T.DURATION_FAST), T.CURVE_STANDARD),
        content=inner,
    )

    return hover_container(outer if focused else inner, glow_color=T.ACCENT, is_selected=focused)


# --- B17 Detail Builders ---


def metadata_row(game: GameTile) -> ft.Row:
    """Players / Genre / Category as icon+label+value triples."""

    def _triple(icon: str, label: str, value: str | None) -> ft.Row:
        return ft.Row(
            spacing=T.SP_4,
            controls=[
                ft.Icon(icon, size=14, color=T.TEXT_MUTED),
                ft.Text(label, size=T.SYSTEM_SIZE, color=T.TEXT_MUTED, weight=ft.FontWeight("w600")),
                ft.Text(_or_dash(value or ""), size=T.SYSTEM_SIZE, color=T.TEXT_PRIMARY if value else T.TEXT_MUTED),
            ],
        )

    return ft.Row(
        spacing=T.SP_16,
        controls=[
            _triple(ft.Icons.PEOPLE_OUTLINE, "Players", game.players),
            _triple(ft.Icons.CATEGORY_OUTLINED, "Genre", game.genre),
            _triple(ft.Icons.LABEL_OUTLINE, "Category", game.category),
        ],
    )


def screenshot_carousel(screenshots: tuple[str, ...]) -> ft.Control:
    """Pure filmstrip of screenshots. Empty tuple -> placeholder."""
    if not screenshots:
        return ft.Container(
            height=180,
            border_radius=T.RADIUS,
            bgcolor=T.BG_SURFACE,
            alignment=ft.Alignment.CENTER,
            content=ft.Text("No screenshots available", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
        )
    return ft.Row(
        spacing=T.SP_8,
        scroll=ft.ScrollMode.AUTO,
        controls=[
            ft.Container(
                border_radius=T.RADIUS,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                content=ft.Image(src=url, fit="cover", width=320, height=180),
            )
            for url in screenshots
        ],
    )


def readonly_value_row(label: str, value: str, *, muted: bool = False, tooltip: str | None = None) -> ft.Row:
    """Read-only setting row: label left, value right. No callback possible at type level."""
    controls: list[ft.Control] = [
        ft.Text(label, size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY, expand=True),
        ft.Text(value, size=14, color=T.TEXT_MUTED if muted else T.TEXT_PRIMARY),
    ]
    return ft.Row(
        spacing=T.SP_12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=controls,
        tooltip=tooltip,
    )


def assistant_settings_section(
    vm: "AssistantSettingsVM",
    *,
    on_provider_change: Callable[[str], None],
    on_model_change: Callable[[str], None],
    on_save_key: Callable[[str], None],
    on_clear_key: Callable[[], None],
) -> ft.Column:
    """Settings -> Assistant section: provider + model + masked API key.

    Security:
      CONTROL #3: the API-key field is password-masked and store-only; once
        configured we show a '✓ configured / Clear' affordance and NEVER
        re-render the value.
      CONTROL #5: when no secure keychain exists we render an honest, disabled
        message and offer NO plaintext path.
    """
    # Model input: a dropdown of known-good models when the provider has a
    # catalog (maps a friendly label -> the real API id), else free-text
    # (ollama / litellm / custom).
    if vm.model_choices:
        model_control: ft.Control = ft.Dropdown(
            value=vm.model_id or None,
            width=260,
            text_size=14,
            hint_text="Select a model",
            options=[dropdown_option(mid, label) for label, mid in vm.model_choices],
            on_select=lambda e: on_model_change(e.control.value or ""),
            color=T.TEXT_PRIMARY,
            bgcolor=T.BG_SURFACE,
            border_color=ft.Colors.with_opacity(0.2, ft.Colors.WHITE),
            focused_border_color=T.ACCENT,
        )
    else:
        model_control = ft.TextField(
            value=vm.model_id,
            width=260,
            text_size=14,
            hint_text="e.g. llama3.2",
            on_submit=lambda e: on_model_change(e.control.value or ""),
            on_blur=lambda e: on_model_change(e.control.value or ""),
            color=T.TEXT_PRIMARY,
            bgcolor=T.BG_SURFACE,
            border_color=ft.Colors.with_opacity(0.2, ft.Colors.WHITE),
            focused_border_color=T.ACCENT,
        )

    rows: list[ft.Control] = [
        ft.Text("Assistant", size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
        editable_dropdown_row(
            "Provider",
            vm.provider,
            vm.provider_choices,
            on_change=on_provider_change,
            tooltip="LLM provider that powers the in-app AI assistant",
        ),
        ft.Row(
            spacing=T.SP_12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("Model ID", size=14, weight=ft.FontWeight("w600"),
                        color=T.TEXT_PRIMARY, expand=True, tooltip="Model identifier"),
                model_control,
            ],
        ),
    ]

    if not vm.requires_api_key:
        rows.append(readonly_value_row("API Key", "Not required for this provider", muted=True))
    elif not vm.keychain_available:
        # CONTROL #5: honest disabled state, no plaintext path offered.
        rows.append(ft.Text(vm.keychain_message, size=T.SYSTEM_SIZE, color=T.TEXT_MUTED))
    elif vm.api_key_status == "configured":
        # CONTROL #3: never re-display the value; offer Clear only.
        rows.append(ft.Row(
            spacing=T.SP_12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("API Key", size=14, weight=ft.FontWeight("w600"),
                        color=T.TEXT_PRIMARY, expand=True),
                ft.Text("\u2713 configured", size=14, color=T.ACCENT_TEXT),
                ft.TextButton("Clear", on_click=lambda _: on_clear_key(),
                              tooltip="Remove the stored API key from the OS keychain"),
            ],
        ))
    else:
        # CONTROL #3: masked, store-only entry field.
        key_field = ft.TextField(
            password=True,
            can_reveal_password=False,
            width=260,
            text_size=14,
            hint_text="Paste API key",
            color=T.TEXT_PRIMARY,
            bgcolor=T.BG_SURFACE,
            border_color=ft.Colors.with_opacity(0.2, ft.Colors.WHITE),
            focused_border_color=T.ACCENT,
        )
        rows.append(ft.Row(
            spacing=T.SP_12,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text("API Key", size=14, weight=ft.FontWeight("w600"),
                        color=T.TEXT_PRIMARY, expand=True),
                key_field,
                ft.TextButton("Save", on_click=lambda _: on_save_key(key_field.value or ""),
                              tooltip="Store the API key securely in the OS keychain"),
            ],
        ))

    return ft.Column(spacing=T.SP_8, controls=rows)


def assistant_setup_view(config_section: ft.Control, *, on_close=None) -> ft.Container:
    """Assistant page shown when no model is configured, or when the user opens
    settings via the gear.

    Instead of a dead 'go to Settings' pointer, this embeds the SAME
    provider/model/API-key controls inline, so the user sets it up right here.
    On save the caller hot-reloads the assistant and this view swaps to the
    live chat. When on_close is given (already configured), a 'Back to chat'
    button returns to the conversation.
    """
    controls: list[ft.Control] = [
        ft.Icon(ft.Icons.SMART_TOY, size=48, color=T.ACCENT),
        ft.Text(
            "Set up the AI assistant",
            size=T.TITLE_SIZE,
            weight=ft.FontWeight(T.TITLE_WEIGHT),
            color=T.TEXT_PRIMARY,
        ),
        ft.Text(
            "Pick a provider and enter a model ID. OpenAI, Anthropic, "
            "Gemini and LiteLLM need an API key (stored in your OS "
            "keychain); Bedrock and Ollama use local credentials.",
            size=14,
            color=T.TEXT_MUTED,
            text_align=ft.TextAlign.CENTER,
            width=520,
        ),
        ft.Container(
            width=520,
            padding=T.SP_16,
            border_radius=T.SP_12,
            bgcolor=T.BG_SURFACE,
            border=ft.Border.all(
                1, ft.Colors.with_opacity(0.08, ft.Colors.WHITE)
            ),
            content=config_section,
        ),
    ]
    if on_close is not None:
        controls.append(
            ft.TextButton(
                "← Back to chat",
                on_click=lambda _: on_close(),
                tooltip="Return to the conversation",
            )
        )
    return ft.Container(
        expand=True,
        alignment=ft.Alignment.TOP_CENTER,
        padding=T.SP_16 * 2,
        content=ft.Column(
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=T.SP_16,
            scroll=ft.ScrollMode.AUTO,
            controls=controls,
        ),
    )


def editable_toggle_row(
    label: str,
    value: bool,
    *,
    on_change: Callable[[bool], None],
    tooltip: str = "",
) -> ft.Row:
    """Editable toggle row: label left, Switch right. Callback fires on toggle.

    Type-level guarantee: this row HAS a callback. A read-only row CANNOT have one.
    """
    switch = ft.Switch(
        value=value,
        active_color=T.ACCENT,
        on_change=lambda e: on_change(e.control.value),
        tooltip=tooltip or label,
    )
    return ft.Row(
        spacing=T.SP_12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(label, size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY, expand=True),
            switch,
        ],
    )


def controls_panel(
    vm: ControlsVM,
    *,
    on_runahead_toggle: Callable[[bool], None] | None = None,
    on_video_smooth_toggle: Callable[[bool], None] | None = None,
    on_shader_change: Callable[[str], None] | None = None,
    input_remap_vm: "InputRemapVM | None" = None,
    on_remap_change: Callable[[str, str], None] | None = None,
) -> ft.Column:
    """Build the Controls tab body from a ControlsVM.

    Editable rows (Run-Ahead, Video Smoothing, Shader) get interactive controls.
    Read-only rows (Core) use readonly_value_row — no callback possible.
    Input remaps: editable dropdown per button when on_remap_change provided.
    """
    # Run-Ahead — EDITABLE
    if on_runahead_toggle:
        runahead_row: ft.Control = editable_toggle_row(
            "Run-Ahead",
            vm.runahead_enabled,
            on_change=on_runahead_toggle,
            tooltip="Toggle run-ahead latency reduction (per-game override)",
        )
    else:
        ra_value = f"On \u2013 {vm.runahead_frames} frame{'s' if vm.runahead_frames != 1 else ''}" if vm.runahead_enabled else "Off"
        runahead_row = readonly_value_row("Run-Ahead", ra_value)

    # Shader — EDITABLE dropdown (1a8wx)
    if on_shader_change:
        from .shader_picker_vm import build_shader_picker_vm
        shader_vm = build_shader_picker_vm(vm.shader_enabled, vm.shader_name)
        shader_row: ft.Control = editable_dropdown_row(
            "Shader",
            shader_vm.current,
            shader_vm.choices,
            on_change=on_shader_change,
            tooltip="CRT shader preset (per-game override)",
        )
    else:
        shader_value = vm.shader_name if vm.shader_enabled else "Off"
        shader_row = readonly_value_row("Shader", shader_value, tooltip="Change via RetroArch Menu")

    # Video Smoothing — EDITABLE
    if on_video_smooth_toggle:
        smooth_row: ft.Control = editable_toggle_row(
            "Video Smoothing",
            vm.video_smooth,
            on_change=on_video_smooth_toggle,
            tooltip="Toggle bilinear filtering (per-game override)",
        )
    else:
        smooth_row = readonly_value_row("Video Smoothing", "On" if vm.video_smooth else "Off")

    # Core — READ-ONLY
    rows: list[ft.Control] = [runahead_row, shader_row, smooth_row]
    if vm.core:
        rows.append(readonly_value_row("Core", vm.core, muted=True))

    # Controller Mapping — editable dropdowns when on_remap_change provided
    if input_remap_vm is not None and on_remap_change:
        from .input_remap_vm import InputRemapVM  # noqa: F811

        mapping_rows: list[ft.Control] = [
            ft.Text("Controller Mapping", size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
        ]
        for row in input_remap_vm.rows:
            mapping_rows.append(editable_dropdown_row(
                row.label,
                row.current_target,
                row.choices,
                on_change=lambda v, btn=row.button: on_remap_change(btn, v),
                tooltip=f"Remap {row.label} button",
            ))
        rows.append(ft.Column(spacing=T.SP_4, controls=mapping_rows))
    elif input_remap_vm is not None:
        # Read-only display (no callback)
        mapping_rows = [
            ft.Text("Controller Mapping", size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
        ]
        for row in input_remap_vm.rows:
            mapping_rows.append(
                ft.Row(
                    spacing=T.SP_8,
                    controls=[
                        ft.Text(row.label, size=T.SYSTEM_SIZE, weight=ft.FontWeight("w600"), color=T.TEXT_MUTED, width=60),
                        ft.Text("\u2192", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
                        ft.Text(row.current_target.upper(), size=T.SYSTEM_SIZE, color=T.TEXT_PRIMARY),
                    ],
                )
            )
        rows.append(ft.Column(spacing=T.SP_4, controls=mapping_rows))
    else:
        rows.append(ft.Column(spacing=T.SP_4, controls=[
            ft.Text("Controller", size=14, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
            ft.Text("Default RetroPad layout", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
        ]))

    # Handoff row — advanced settings live in RGUI, never reimplemented
    handoff_row = ft.Container(
        padding=ft.Padding(T.SP_12, T.SP_12, T.SP_12, T.SP_12),
        border_radius=T.SP_8,
        bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.WHITE),
        content=ft.Row(
            spacing=T.SP_8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(ft.Icons.OPEN_IN_NEW, size=16, color=T.ACCENT),
                ft.Text(
                    "Advanced \u2013 Open RetroArch Menu",
                    size=14,
                    weight=ft.FontWeight("w600"),
                    color=T.ACCENT,
                ),
            ],
        ),
    )
    rows.append(handoff_row)

    return ft.Column(spacing=T.SP_16, controls=rows)

def detail_tabs(
    game: GameTile,
    *,
    active_tab: str = "description",
    controls_vm: ControlsVM | None = None,
    core_options_vm: "CoreOptionsVM | None" = None,
    input_remap_vm: "InputRemapVM | None" = None,
    on_select_tab: Callable[[str], None] | None = None,
    on_runahead_toggle: Callable[[bool], None] | None = None,
    on_video_smooth_toggle: Callable[[bool], None] | None = None,
    on_shader_change: Callable[[str], None] | None = None,
    on_core_option_change: Callable[[str, str], None] | None = None,
    on_remap_change: Callable[[str, str], None] | None = None,
) -> ft.Column:
    """Description | Controls | Core Options tab headers + body.

    Returns expand=True Column so it fills remaining vertical space below
    the hero band. Tab body Column also expand=True + scroll=AUTO so content
    is genuinely scrollable within the bounded area.
    """

    def _tab_header(label: str, tab_id: str) -> ft.Container:
        is_active = tab_id == active_tab
        return ft.Container(
            padding=ft.Padding(T.SP_4, T.SP_12, T.SP_4, T.SP_12),
            border=ft.Border(bottom=ft.BorderSide(2, T.ACCENT if is_active else "transparent")),
            on_click=(lambda _, t=tab_id: on_select_tab(t)) if on_select_tab else None,
            content=ft.Text(
                label,
                size=14,
                weight=ft.FontWeight("w700" if is_active else "w500"),
                color=T.TEXT_PRIMARY if is_active else T.TEXT_MUTED,
            ),
        )

    headers = ft.Row(
        spacing=T.SP_16,
        controls=[
            _tab_header("Description", "description"),
            _tab_header("Controls", "controls"),
            _tab_header("Core Options", "core_options"),
        ],
    )

    if active_tab == "description":
        body: ft.Control = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text(
                    _or_dash(game.description or ""),
                    size=14,
                    color=T.TEXT_PRIMARY if game.description else T.TEXT_MUTED,
                    style=ft.TextStyle(height=1.5),
                )
            ],
        )
    elif active_tab == "core_options":
        from .core_options_vm import CoreOptionsVM as _CoreOptionsVM

        if core_options_vm is not None:
            body = ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[core_options_panel(core_options_vm, on_change=on_core_option_change)],
            )
        else:
            body = ft.Container(
                expand=True,
                padding=T.SP_16,
                content=ft.Text("No core options loaded", size=14, color=T.TEXT_MUTED),
            )
    else:
        from factory.arcade_config.runtime.settings import RetroArchRuntimeSettings

        fallback_vm = controls_from_settings(RetroArchRuntimeSettings(
            core="", run_ahead_enabled=False, run_ahead_frames=1,
            shader_enabled=False, shader_name="", video_smooth=False,
        ))
        body = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                controls_panel(
                    controls_vm or fallback_vm,
                    on_runahead_toggle=on_runahead_toggle,
                    on_video_smooth_toggle=on_video_smooth_toggle,
                    on_shader_change=on_shader_change,
                    input_remap_vm=input_remap_vm,
                    on_remap_change=on_remap_change,
                ),
            ],
        )

    return ft.Column(expand=True, spacing=T.SP_12, controls=[headers, body])


def metadata_sidebar(game: GameTile) -> ft.Column:
    """Platform / Developer / Publisher / Release Date / Rating sidebar."""

    def _row(label: str, value: str | None) -> ft.Column:
        return ft.Column(
            spacing=2,
            controls=[
                ft.Text(label, size=T.SYSTEM_SIZE, color=T.TEXT_MUTED, weight=ft.FontWeight("w600")),
                ft.Text(_or_dash(value or ""), size=14, color=T.TEXT_PRIMARY if value else T.TEXT_MUTED),
            ],
        )

    return ft.Column(
        spacing=T.SP_12,
        controls=[
            _row("Platform", game.system),
            _row("Developer", game.developer),
            _row("Publisher", game.publisher or None),
            _row("Release Date", game.release_date),
            _row("Rating", game.rating),
        ],
    )


def _detail_footer(game: GameTile) -> ft.Row | None:
    """Last Played / Play Count stats. Returns None when no play data exists.

    Play-tracking is unbuilt, so both fields are absent today and the footer
    simply does not render -- no fake 'Coming soon' placeholder. When only one
    field has data (future state), only that field is shown.
    """
    if game.last_played is None and game.play_count is None:
        return None

    stats: list[ft.Control] = []
    if game.last_played is not None:
        stats.append(ft.Row(spacing=T.SP_4, controls=[
            ft.Icon(ft.Icons.ACCESS_TIME, size=14, color=T.TEXT_MUTED),
            ft.Text("Last Played", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
            ft.Text(game.last_played, size=T.SYSTEM_SIZE, color=T.TEXT_PRIMARY),
        ]))
    if game.play_count is not None:
        stats.append(ft.Row(spacing=T.SP_4, controls=[
            ft.Icon(ft.Icons.PLAY_CIRCLE_OUTLINE, size=14, color=T.TEXT_MUTED),
            ft.Text("Play Count", size=T.SYSTEM_SIZE, color=T.TEXT_MUTED),
            ft.Text(str(game.play_count), size=T.SYSTEM_SIZE, color=T.TEXT_PRIMARY),
        ]))
    return ft.Row(spacing=T.SP_16, controls=stats)


def detail_view(
    game: GameTile,
    *,
    active_tab: str = "description",
    controls_vm: ControlsVM | None = None,
    core_options_vm: "CoreOptionsVM | None" = None,
    input_remap_vm: "InputRemapVM | None" = None,
    on_play: Callable[[], None],
    on_back: Callable[[], None],
    on_select_tab: Callable[[str], None] | None = None,
    on_runahead_toggle: Callable[[bool], None] | None = None,
    on_video_smooth_toggle: Callable[[bool], None] | None = None,
    on_shader_change: Callable[[str], None] | None = None,
    on_core_option_change: Callable[[str, str], None] | None = None,
    on_remap_change: Callable[[str, str], None] | None = None,
) -> ft.Container:
    """Cinematic game detail page.

    Layout:
      Container(expand=True, padding=32)
        Column(expand=True)
          Row(height=320)  -- hero band: art | title+actions | metadata sidebar
          Divider
          Column(expand=True) -- tabs fill remaining space (scroll=AUTO per body)
    """
    # --- Hero Art (fixed 320px band) ---
    hero = ft.Container(
        width=T.DETAIL_HERO_W,
        height=320,
        border_radius=T.RADIUS,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        content=_bounded_art_region(game, allow_video=True),
    )

    # --- Actions: Play = primary filled, Back = secondary ghost ---
    actions = ft.Row(
        spacing=T.SP_12,
        controls=[
            ft.Button(
                "Play",
                icon=ft.Icons.PLAY_ARROW,
                on_click=lambda _: on_play(),
                style=ft.ButtonStyle(bgcolor=T.ACCENT, color=T.TEXT_PRIMARY),
            ),
            ft.TextButton(
                "Back",
                icon=ft.Icons.ARROW_BACK,
                on_click=lambda _: on_back(),
            ),
        ],
    )

    # --- Title / metadata / actions column (center of hero band) ---
    title_meta = ft.Column(
        expand=True,
        spacing=T.SP_16,
        alignment=ft.MainAxisAlignment.CENTER,
        controls=[
            ft.Text(game.title, size=28, weight=ft.FontWeight("w800"), color=T.TEXT_PRIMARY),
            metadata_row(game),
            actions,
        ],
    )

    # --- Sidebar (right of hero band) ---
    sidebar = metadata_sidebar(game)

    # --- Hero band Row (fixed height ~320) ---
    hero_band = ft.Row(
        height=320,
        spacing=T.SP_16 * 2,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[hero, title_meta, sidebar],
    )

    # --- Tabs section (fills remaining vertical space) ---
    tabs = detail_tabs(
        game,
        active_tab=active_tab,
        controls_vm=controls_vm,
        core_options_vm=core_options_vm,
        input_remap_vm=input_remap_vm,
        on_select_tab=on_select_tab,
        on_runahead_toggle=on_runahead_toggle,
        on_video_smooth_toggle=on_video_smooth_toggle,
        on_shader_change=on_shader_change,
        on_core_option_change=on_core_option_change,
        on_remap_change=on_remap_change,
    )

    # --- Footer (only when play-tracking data exists) ---
    footer = _detail_footer(game)
    footer_block: list[ft.Control] = (
        [ft.Divider(color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)), footer]
        if footer is not None
        else []
    )

    return ft.Container(
        expand=True,
        padding=T.SP_16 * 2,
        bgcolor=T.BG_BASE,
        content=ft.Column(
            expand=True,
            spacing=T.SP_16,
            controls=[
                hero_band,
                ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)),
                tabs,
                *footer_block,
            ],
        ),
    )


# --- dge52: Core Options editable UI ---


def dropdown_option(key: str, label: str) -> ft.dropdown.Option:
    """Build a dropdown option whose MENU text is visible on the dark theme.

    Flet renders an Option's `text` in the popup menu with a default (dark) color
    that is invisible on our dark surface — the recurring 'empty dropdown' bug.
    Setting `content` to an explicitly-colored Text guarantees the menu item is
    readable. `text` is kept as the fallback the closed control displays.
    """
    return ft.dropdown.Option(
        key=key,
        text=label,
        content=ft.Text(label, color=T.TEXT_PRIMARY, size=14),
    )


def editable_dropdown_row(
    label: str,
    value: str,
    choices: tuple[str, ...] | list[str],
    *,
    on_change: Callable[[str], None],
    tooltip: str = "",
) -> ft.Row:
    """Editable core-option row: label left, Dropdown right. Skinned, minimalist, a11y.

    Type-level: this row HAS a callback. A read-only row CANNOT have one.
    WCAG AA: label + tooltip, visible focus indicator via Flet Dropdown defaults.
    """
    dropdown = ft.Dropdown(
        value=value,
        options=[dropdown_option(c, c) for c in choices],
        on_select=lambda e: on_change(e.control.value),
        tooltip=tooltip or label,
        text_size=14,
        width=180,
        content_padding=ft.Padding(T.SP_8, T.SP_4, T.SP_8, T.SP_4),
        border_color=ft.Colors.with_opacity(0.2, ft.Colors.WHITE),
        focused_border_color=T.ACCENT,
        color=T.TEXT_PRIMARY,
        bgcolor=T.BG_SURFACE,
    )
    return ft.Row(
        spacing=T.SP_12,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        controls=[
            ft.Text(
                label,
                size=14,
                weight=ft.FontWeight("w600"),
                color=T.TEXT_PRIMARY,
                expand=True,
                tooltip=tooltip or label,
            ),
            dropdown,
        ],
    )


def core_options_panel(
    vm: "CoreOptionsVM",
    *,
    on_change: Callable[[str, str], None] | None = None,
) -> ft.Column:
    """Build the Core Options panel from a CoreOptionsVM.

    Curated options get editable_dropdown_row; uncurated get readonly_value_row.
    on_change receives (option_key, new_value).
    """
    from .core_options_vm import CoreOptionsVM  # noqa: F811 (type import above is string)

    rows: list[ft.Control] = []

    if vm.curated:
        rows.append(ft.Text(
            "Core Options",
            size=16,
            weight=ft.FontWeight("w700"),
            color=T.TEXT_PRIMARY,
        ))
        for opt in vm.curated:
            if on_change:
                rows.append(editable_dropdown_row(
                    opt.label,
                    opt.value,
                    opt.choices,
                    on_change=lambda v, k=opt.key: on_change(k, v),
                    tooltip=f"{opt.label} ({opt.key})",
                ))
            else:
                rows.append(readonly_value_row(opt.label, opt.value, tooltip=opt.key))

    if vm.uncurated:
        rows.append(ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
        rows.append(ft.Text(
            "Other Options (read-only)",
            size=14,
            weight=ft.FontWeight("w600"),
            color=T.TEXT_MUTED,
        ))
        for opt in vm.uncurated:
            rows.append(readonly_value_row(opt.label, opt.value, muted=True, tooltip=opt.key))

    return ft.Column(spacing=T.SP_12, controls=rows)
