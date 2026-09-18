"""Wall <-> Detail navigation controller with persistent rail + keyboard focus."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import flet as ft

from .models import GameTile, WallViewModel
from .focus import Direction, focus_move
from .filters import filter_tiles, derive_systems, derive_letters
from .config_service import save_global_overrides
from .controls_vm import ControlsVM
from .core_options_vm import CoreOptionsVM
from .input_remap_vm import InputRemapVM
from .library_query import search_games
from .retroarch_config import RetroArchConfig
from .launch_handler import LaunchHandler
from .snap_fetcher import SnapFetcher
from .assistant_panel import assistant_panel, ChatMessage
from .assistant_vm import AssistantVM
from . import chrome as CH
from . import components as C
from . import theme as T


# Flet 0.85 key strings
_KEY_MAP: dict[str, Direction] = {
    "Arrow Up": Direction.UP,
    "Arrow Down": Direction.DOWN,
    "Arrow Left": Direction.LEFT,
    "Arrow Right": Direction.RIGHT,
}


def _find_tile_by_id(tiles: list[GameTile], game_id: str) -> GameTile | None:
    """Look up a tile by its id."""
    return next((t for t in tiles if t.id == game_id), None)


@dataclass
class WallState:
    """Navigation state: None = grid, GameTile = detail view."""
    selected: GameTile | None = None
    focus_index: int = 0
    _detail_tab: str = "description"
    current_screen: str = "library"


@dataclass
class LibraryState:
    """Active filter state for the library grid."""
    active_system: str | None = None
    active_letter: str | None = None
    search_query: str = ""


class Navigator:
    """Persistent rail + AnimatedSwitcher body driven by WallState + LibraryState."""

    def __init__(
        self,
        vm: WallViewModel,
        page: ft.Page | None = None,
        *,
        config_dir: Path | None = None,
        snap_fetcher: SnapFetcher | None = None,
        media_root: Path | None = None,
        retroarch_config: RetroArchConfig | None = None,
        launch_handler: LaunchHandler | None = None,
    ) -> None:
        self._vm = vm
        self._page = page
        self._config_dir = config_dir
        self._snap_fetcher = snap_fetcher
        self._media_root = media_root
        self._ra_config = retroarch_config
        self._launch_handler = launch_handler
        self._state = WallState()
        self._library = LibraryState()
        self._filtered: list[GameTile] = list(vm.tiles)
        self._grid: ft.GridView | None = None  # stable ref for in-place search updates

        # --- Assistant state (shared VM — single source of truth) ---
        self._assistant_vm = AssistantVM()
        self._reload_assistant()

        # Body switcher -- content swaps on nav; rail persists outside.
        self._switcher = ft.AnimatedSwitcher(
            duration=T.duration(T.DURATION_NORMAL),
            transition=ft.AnimatedSwitcherTransition.FADE,
            switch_in_curve=T.CURVE_DECELERATE,
            switch_out_curve=T.CURVE_STANDARD,
            content=self._build_library_body(),
            expand=True,
        )

        # Persistent rail -- built ONCE, lives at root level.
        self._rail = CH.nav_rail(CH.NAV_ITEMS, selected="library", on_select=self._on_nav_select)

        # Root composition: rail(left, flush to edge) | body(expand, padded).
        self._root = ft.Row(
            expand=True,
            spacing=0,
            controls=[
                self._rail,
                ft.Container(content=self._switcher, expand=True, padding=T.SP_16),
            ],
        )

        if page:
            page.on_keyboard_event = self._on_key

    @property
    def state(self) -> WallState:
        return self._state

    @property
    def library(self) -> LibraryState:
        return self._library

    @property
    def assistant_vm(self) -> AssistantVM:
        """The shared AssistantVM instance (used by chat_overlay + landing page)."""
        return self._assistant_vm

    # Backward-compat accessors (tests may reference these)
    @property
    def _assistant_messages(self) -> list[ChatMessage]:
        return self._assistant_vm.messages

    @property
    def _is_null_assistant(self) -> bool:
        return self._assistant_vm.is_null

    @_is_null_assistant.setter
    def _is_null_assistant(self, value: bool) -> None:
        self._assistant_vm.is_null = value

    @property
    def _assistant(self):
        return self._assistant_vm._assistant

    @_assistant.setter
    def _assistant(self, value) -> None:
        # Write-through to the shared VM so tests (and any legacy callers)
        # that set nav._assistant keep working after the VM extraction.
        self._assistant_vm._assistant = value

    @property
    def control(self) -> ft.Row:
        """The root control to add to the page. Contains the persistent rail + body."""
        return self._root

    # --- Body transition helper ---

    def _set_body(self, content: ft.Control) -> None:
        """Assign a new screen body to the switcher.

        The AnimatedSwitcher's FADE crossfade animates the swap. A wrapper
        scale-in was tried but is a no-op here: screens are rebuilt fresh on nav,
        so content mounts at its final value (setting 0.97 then 1.0 synchronously
        never tweens). Plain assignment keeps the honest, working crossfade.
        """
        self._switcher.content = content

    # --- Public API ---

    def select(self, game: GameTile) -> None:
        self._state.selected = game
        self._state._detail_tab = "description"
        self._set_body(self._build_detail(game))
        self._try_update()

    def back(self) -> None:
        self._state.selected = None
        self._set_body(self._build_library_body())
        self._try_update()

    def set_system_filter(self, system: str | None) -> None:
        self._library.active_system = None if system == self._library.active_system else system
        self._state.focus_index = 0
        self._state.current_screen = "library"
        self._update_rail_selection("library")
        self._set_body(self._build_library_body())
        self._try_update()

    def set_letter_filter(self, letter: str | None) -> None:
        self._library.active_letter = None if letter == self._library.active_letter else letter
        self._state.focus_index = 0
        self._set_body(self._build_library_body())
        self._try_update()

    def set_search_query(self, query: str) -> None:
        """Live search: filter in place WITHOUT rebuilding the library body.

        Rebuilding _build_library_body() recreates the search TextField, and the
        AnimatedSwitcher swaps it out mid-keystroke — destroying focus and the
        typed text (the 'letters disappear' bug). Instead we recompute the filter
        and update ONLY the grid's children, leaving the live search field mounted.
        """
        self._library.search_query = query
        self._state.focus_index = 0
        self._filtered = filter_tiles(
            self._vm.tiles,
            system=self._library.active_system,
            letter=self._library.active_letter,
            query=self._library.search_query or None,
        )
        if self._grid is not None:
            self._grid.controls = self._grid_tiles()
            try:
                self._grid.update()
            except RuntimeError:
                pass

    # --- Internal ---

    def _try_update(self) -> None:
        """Update controls if attached to a page; no-op in tests."""
        try:
            self._switcher.update()
        except RuntimeError:
            pass
        try:
            self._rail.update()
        except RuntimeError:
            pass

    def _update_rail_selection(self, route_id: str) -> None:
        """Sync rail selected index to route."""
        idx = next((i for i, it in enumerate(CH.NAV_ITEMS) if it.route_id == route_id), 0)
        self._rail.selected_index = idx

    def _on_nav_select(self, route_id: str) -> None:
        self._state.current_screen = route_id
        self._state.selected = None
        self._update_rail_selection(route_id)
        if route_id == "settings":
            self._set_body(self._build_settings())
        elif route_id == "systems":
            self._set_body(self._build_systems())
        elif route_id == "controllers":
            self._set_body(self._build_controllers())
        elif route_id == "import":
            self._set_body(self._build_import())
        elif route_id == "information":
            self._set_body(self._build_information())
        elif route_id == "cores":
            self._set_body(self._build_cores())
        elif route_id == "assistant":
            self._set_body(self._build_assistant())
        else:
            self._set_body(self._build_library_body())
        self._try_update()

    # --- Keyboard handler ---

    def _on_key(self, e: ft.KeyboardEvent) -> None:
        key = e.key

        if self._state.selected is None and self._state.current_screen == "library":
            direction = _KEY_MAP.get(key)
            if direction:
                new_idx = focus_move(
                    self._state.focus_index,
                    direction,
                    count=len(self._filtered),
                    columns=self._vm.columns,
                )
                if new_idx != self._state.focus_index:
                    self._state.focus_index = new_idx
                    self._set_body(self._build_library_body())
                    self._try_update()
            elif key == "Enter":
                if self._filtered:
                    self.select(self._filtered[self._state.focus_index])
        elif self._state.selected is not None:
            if key == "Escape":
                self.back()
            elif key == "Enter":
                game = self._state.selected
                if game and game.playable and game.rom_path and self._page:
                    if self._launch_handler:
                        self._page.run_task(self._launch_handler.launch, game)
            elif key in ("Arrow Left", "Arrow Right", "Tab"):
                tabs = ("description", "controls", "core_options")
                cur = tabs.index(self._state._detail_tab) if self._state._detail_tab in tabs else 0
                if key == "Arrow Left":
                    cur = (cur - 1) % len(tabs)
                else:
                    cur = (cur + 1) % len(tabs)
                self._state._detail_tab = tabs[cur]
                self._set_body(self._build_detail(self._state.selected))
                self._try_update()

    # --- Body builders ---

    def _grid_tiles(self) -> list[ft.Control]:
        """Build the tile controls for the current filtered set."""
        return [
            C.tile(t, on_click=self.select, focused=(i == self._state.focus_index))
            for i, t in enumerate(self._filtered)
        ]

    def _build_grid(self) -> ft.GridView:
        return ft.GridView(
            runs_count=self._vm.columns,
            spacing=T.SP_12,
            run_spacing=T.SP_12,
            child_aspect_ratio=T.TILE_ASPECT,
            expand=True,
            controls=self._grid_tiles(),
        )

    def _build_library_body(self) -> ft.Row:
        """Library body: search + filter_bar + grid + az. No rail."""
        self._filtered = filter_tiles(
            self._vm.tiles,
            system=self._library.active_system,
            letter=self._library.active_letter,
            query=self._library.search_query or None,
        )
        self._grid = self._build_grid()
        grid = self._grid
        fbar = CH.filter_bar(
            derive_systems(self._vm.tiles),
            active=self._library.active_system,
            on_select=self.set_system_filter,
        )
        search = CH.search_field(on_change=self.set_search_query)
        letters = derive_letters(self._vm.tiles)
        az = CH.az_index(letters, on_jump=self.set_letter_filter) if len(letters) >= 8 else ft.Container(width=0)
        accent = C.system_accent(self._library.active_system)
        fi = self._state.focus_index
        focused = self._filtered[fi] if self._filtered and 0 <= fi < len(self._filtered) else None
        hero_art = focused.art_url if focused else None
        return CH.library_view(
            fbar, search, az, grid, hints=CH.HINTS_WALL, accent=accent, hero_art=hero_art
        )

    def _build_detail(self, game: GameTile) -> ft.Container:
        if self._page and game.playable and game.rom_path:
            if self._launch_handler:
                on_play = lambda: self._page.run_task(self._launch_handler.launch, game)
            else:
                on_play = lambda: None
        else:
            on_play = lambda: None

        # --- On-demand snap fetch: trigger background SCP if eligible ---
        if (
            self._page
            and self._snap_fetcher
            and self._media_root
            and not game.video_url
            and game.expected_snap_path
        ):
            self._page.run_task(self._do_snap_fetch, game)

        def _on_tab(tab_id: str) -> None:
            self._state._detail_tab = tab_id
            self._set_body(self._build_detail(game))
            self._try_update()

        # Delegate to RetroArchConfig for all config resolution
        controls_vm: ControlsVM | None = None
        core_options_vm: CoreOptionsVM | None = None
        input_remap_vm: InputRemapVM | None = None
        if self._ra_config:
            controls_vm = self._ra_config.resolve_controls_vm(game)
            core_options_vm = self._ra_config.resolve_core_options_vm(game)
            input_remap_vm = self._ra_config.resolve_input_remap_vm(game)

        # --- Editable toggle callbacks (imperative shell) ---
        def _on_runahead_toggle(enabled: bool) -> None:
            if self._ra_config:
                self._ra_config.write_game_override(game, "run_ahead_enabled", "true" if enabled else "false")
                self._ra_config.write_game_override(game, "run_ahead_frames", "1")
            self._set_body(self._build_detail(game))
            self._try_update()

        def _on_video_smooth_toggle(enabled: bool) -> None:
            if self._ra_config:
                self._ra_config.write_game_override(game, "video_smooth", "true" if enabled else "false")
            self._set_body(self._build_detail(game))
            self._try_update()

        def _on_core_option_change(key: str, value: str) -> None:
            if self._ra_config:
                self._ra_config.write_core_option(game, key, value)
            self._set_body(self._build_detail(game))
            self._try_update()

        def _on_remap_change(button: str, target: str) -> None:
            if self._ra_config:
                self._ra_config.write_input_remap(game, button, target)
            self._set_body(self._build_detail(game))
            self._try_update()

        def _on_shader_change(preset: str) -> None:
            if self._ra_config:
                if preset == "None":
                    self._ra_config.write_game_override(game, "video_shader_enable", "false")
                    self._ra_config.write_game_override(game, "video_shader", "")
                else:
                    self._ra_config.write_game_override(game, "video_shader_enable", "true")
                    self._ra_config.write_game_override(game, "video_shader", preset)
            self._set_body(self._build_detail(game))
            self._try_update()

        return C.detail_view(
            game,
            active_tab=self._state._detail_tab,
            controls_vm=controls_vm,
            core_options_vm=core_options_vm,
            input_remap_vm=input_remap_vm,
            on_play=on_play,
            on_back=self.back,
            on_select_tab=_on_tab,
            on_runahead_toggle=_on_runahead_toggle if self._ra_config else None,
            on_video_smooth_toggle=_on_video_smooth_toggle if self._ra_config else None,
            on_shader_change=_on_shader_change if self._ra_config else None,
            on_core_option_change=_on_core_option_change if self._ra_config else None,
            on_remap_change=_on_remap_change if self._ra_config else None,
        )

    # --- Information screen ---

    def _build_cores(self) -> ft.Container:
        """Cores & Updates screen — list installed cores.

        Calls cores_query PURE core directly (no MCP server import).
        """
        from control_plane.cores_query import list_installed_cores

        cores_dir = self._media_root / "cores" if self._media_root else None
        cores: list = []
        if cores_dir and cores_dir.is_dir():
            cores = list_installed_cores(cores_dir)

        core_rows = [
            CH.CoreRow(
                display_name=c.display_name,
                system_name=c.system_name,
                filename=c.filename,
                size_label=f"{c.size_bytes / 1024 / 1024:.1f} MB" if c.size_bytes >= 1024 * 1024
                else f"{c.size_bytes / 1024:.0f} KB",
            )
            for c in cores
        ]

        return CH.cores_view(
            core_rows,
            install_disabled=True,  # Install action is MCP-only for now; UI = read-only
        )

    def _build_information(self) -> ft.Container:
        """Information screen — read-only system info card.

        Calls information_query PURE core directly (no MCP server import).
        """
        from control_plane.information_query import get_system_info

        # Derive system: active filter > first tile > empty
        default_sys = ""
        if self._library.active_system:
            default_sys = self._library.active_system
        elif self._vm.tiles:
            default_sys = self._vm.tiles[0].system

        info = get_system_info(
            tiles=self._vm.tiles,
            media_root=self._media_root or Path("."),
            system=None,
            default_system=default_sys,
        )

        heading = ft.Text(
            f"{info.get('system', '').upper()} — {info.get('core', 'unknown')}",
            size=22,
            weight=ft.FontWeight("w700"),
            color=T.TEXT_PRIMARY,
            tooltip="Active system and resolved emulator core",
        )

        def _row(label: str, value: str, *, tooltip: str = "") -> ft.Row:
            return ft.Row(
                spacing=T.SP_12,
                controls=[
                    ft.Text(label, size=14, weight=ft.FontWeight("w600"), color=T.TEXT_MUTED, width=180),
                    ft.Text(value, size=14, color=T.TEXT_PRIMARY, tooltip=tooltip or label),
                ],
            )

        rows: list[ft.Control] = [
            _row("Games", str(info["game_count"]), tooltip="Total games for this system"),
            _row("Supported extensions", ", ".join(info["supported_extensions"]) or "—", tooltip="ROM file types recognized"),
            _row("Art coverage", info["art_coverage"], tooltip="Games with local cover art / total"),
            _row("Config layers", ", ".join(info["config_layers_present"]) or "none", tooltip="Override layers present on disk"),
            _row("Override directory", info["override_dir"], tooltip="Path to per-game override configs"),
        ]

        if "retroarch_version" in info:
            rows.insert(0, _row("RetroArch version", info["retroarch_version"], tooltip="Parsed from config header"))

        systems_text = ", ".join(info.get("systems", []))
        if systems_text:
            rows.append(_row("All systems", systems_text, tooltip="Systems present in library"))

        card = ft.Container(
            padding=T.SP_16 * 2,
            border_radius=T.SP_12,
            bgcolor=T.BG_SURFACE,
            content=ft.Column(
                spacing=T.SP_16,
                controls=[heading, ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE))] + rows,
            ),
        )

        content = ft.Column(
            expand=True,
            spacing=T.SP_12,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("System Information", size=18, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY),
                card,
            ],
        )
        return ft.Container(content=content, expand=True, padding=T.SP_16 * 2)

    # --- Assistant screen ---

    def _build_assistant(self) -> ft.Container:
        """Assistant panel: chat surface, or the settings form (when unconfigured
        OR the user opened settings via the gear). Streaming runs off-thread.
        """
        vm = self._assistant_vm
        show_config = vm.is_null or vm.config_open
        if show_config:
            from .assistant_settings_vm import build_assistant_settings_vm

            a_vm = build_assistant_settings_vm()
            on_provider, on_model, on_save_key, on_clear_key = (
                self._assistant_config_handlers(self._build_assistant)
            )
            section = C.assistant_settings_section(
                a_vm,
                on_provider_change=on_provider,
                on_model_change=on_model,
                on_save_key=on_save_key,
                on_clear_key=on_clear_key,
            )
            # Once configured, offer a way back to the chat.
            on_close = (
                None if vm.is_null
                else (lambda: self._toggle_assistant_config(False))
            )
            return C.assistant_setup_view(section, on_close=on_close)

        def _on_send(text: str) -> None:
            vm.messages.append(ChatMessage(role="user", text=text))
            self._set_body(self._build_assistant())
            self._try_update()
            # Kick off streaming in background (non-blocking)
            if self._page:
                self._page.run_task(self._stream_assistant_response, text)

        chat = assistant_panel(
            vm.messages,
            on_send=_on_send,
            enabled=True,
        )
        # Settings gear so the user can change provider/model anytime.
        gear = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            icon_color=T.TEXT_MUTED,
            tooltip="Assistant settings",
            on_click=lambda _: self._toggle_assistant_config(True),
        )
        header = ft.Row(controls=[ft.Container(expand=True), gear])
        return ft.Container(
            expand=True,
            content=ft.Column(expand=True, spacing=0, controls=[header, chat]),
        )

    def _toggle_assistant_config(self, open_: bool) -> None:
        """Show/hide the inline assistant settings form on the Assistant page."""
        self._assistant_vm.config_open = open_
        self._set_body(self._build_assistant())
        self._try_update()

    async def _stream_assistant_response(self, text: str) -> None:
        """Consume the AssistantLoop async iterator and append chunks to messages.

        Each chunk is appended to a growing assistant message. The panel is
        rebuilt after each chunk to show incremental streaming.
        """
        vm = self._assistant_vm
        msg_idx = len(vm.messages)
        vm.messages.append(ChatMessage(role="assistant", text="…"))
        accumulated = ""

        try:
            async for chunk in vm.send(text):
                accumulated += chunk
                vm.messages[msg_idx] = ChatMessage(
                    role="assistant", text=accumulated or "…"
                )
                self._set_body(self._build_assistant())
                self._try_update()
            if not accumulated:
                vm.messages[msg_idx] = ChatMessage(
                    role="assistant",
                    text=(
                        "(No response — the model returned nothing. Check the "
                        "model and provider access in Settings → Assistant.)"
                    ),
                )
                self._set_body(self._build_assistant())
                self._try_update()
        except Exception as exc:  # surface the real error instead of a silent empty bubble
            vm.messages[msg_idx] = ChatMessage(
                role="assistant", text=f"⚠ Assistant error: {exc}"
            )
            self._set_body(self._build_assistant())
            self._try_update()

    # --- Settings screen ---

    def _build_settings(self) -> ft.Container:
        """Settings body. Builds GlobalSettingsVM from parsed global override."""
        from .global_settings_vm import build_global_settings_vm

        global_cfg: dict[str, str] = {}
        if self._config_dir:
            from factory.arcade_config.runtime.serializers import parse_cfg as _parse
            global_override_path = self._config_dir / "global.cfg"
            if global_override_path.exists():
                global_cfg = _parse(global_override_path.read_text(errors="replace"))

        vm = build_global_settings_vm(global_cfg) if self._config_dir else None
        config_dir_text = str(self._config_dir) if self._config_dir else "--"

        from .assistant_settings_vm import build_assistant_settings_vm
        a_vm = build_assistant_settings_vm()
        on_provider, on_model, on_save_key, on_clear_key = (
            self._assistant_config_handlers(self._build_settings)
        )
        assistant_section = C.assistant_settings_section(
            a_vm,
            on_provider_change=on_provider,
            on_model_change=on_model,
            on_save_key=on_save_key,
            on_clear_key=on_clear_key,
        )
        return CH.settings_view(
            global_settings_vm=vm,
            on_setting_change=self._on_global_setting_change if self._config_dir else None,
            config_dir_text=config_dir_text,
            assistant_section=assistant_section,
        )

    # --- Assistant config persistence (Settings -> Assistant) ---

    def _reload_assistant(self) -> None:
        """(Re)build the assistant from the saved Settings config (env fallback).

        Called at startup and after any Settings->Assistant change so the chosen
        provider/model/key takes effect live without an app restart.
        """
        from control_plane.assistant import resolve_assistant, AssistantConfig, NullAssistant
        from control_plane.assistant_config_service import resolve_keychain
        self._assistant_config = AssistantConfig.from_stored(keychain=resolve_keychain())
        assistant = resolve_assistant(self._assistant_config)
        self._assistant_vm._assistant = assistant
        self._assistant_vm.is_null = isinstance(assistant, NullAssistant)
        self._assistant_vm._reload_fn = self._reload_assistant

    def _assistant_stored(self) -> tuple[str, str]:
        """Return (provider, model_id) from the persisted assistant config."""
        from control_plane.assistant_config_service import load_assistant_config
        cfg = load_assistant_config()
        return cfg.get("provider", "bedrock"), cfg.get("model_id", "")

    def _assistant_config_handlers(self, rebuild):
        """Build (on_provider, on_model, on_save_key, on_clear_key) callbacks.

        Each persists a Settings->Assistant change, hot-reloads the assistant so
        it takes effect without a restart, then rebuilds the given screen. Shared
        by the Settings section AND the inline setup panel on the Assistant page,
        so configuring from either place works and swaps to live chat on success.
        """
        from control_plane.assistant_config_service import (
            save_assistant_config,
            resolve_keychain,
            store_api_key,
            clear_api_key,
            KeychainUnavailable,
        )

        def _refresh() -> None:
            self._reload_assistant()
            self._set_body(rebuild())
            self._try_update()

        def on_provider(provider: str) -> None:
            _, model_id = self._assistant_stored()
            save_assistant_config(provider, model_id)
            _refresh()

        def on_model(model_id: str) -> None:
            provider, _ = self._assistant_stored()
            save_assistant_config(provider, model_id)
            _refresh()

        def on_save_key(key: str) -> None:
            # CONTROL #5: store only via keychain; fail closed (no plaintext).
            if not key:
                return
            provider, _ = self._assistant_stored()
            try:
                store_api_key(provider, key, keychain=resolve_keychain())
            except KeychainUnavailable:
                pass  # honest disabled state already rendered; never persist plaintext
            _refresh()

        def on_clear_key() -> None:
            provider, _ = self._assistant_stored()
            try:
                clear_api_key(provider, keychain=resolve_keychain())
            except KeychainUnavailable:
                pass
            _refresh()

        return on_provider, on_model, on_save_key, on_clear_key

    def _on_global_setting_change(self, key: str, value: str) -> None:
        """Persist any global setting change via save_global_overrides (merge)."""
        if self._config_dir is None:
            return
        cfg_value = value
        if key == "video_aspect_ratio" and value == "Auto":
            cfg_value = ""
        save_global_overrides({key: cfg_value}, base_dir=self._config_dir)
        self._set_body(self._build_settings())
        self._try_update()

    def _build_systems(self) -> ft.Container:
        """Systems browse body: list consoles, selecting one filters library."""
        systems = derive_systems(self._vm.tiles)
        return CH.systems_view(systems, on_select=self._on_system_selected)

    def _on_system_selected(self, system: str) -> None:
        """From Systems screen: set filter and navigate to library."""
        self._library.active_system = system
        self._state.focus_index = 0
        self._state.current_screen = "library"
        self._update_rail_selection("library")
        self._set_body(self._build_library_body())
        self._try_update()

    # --- Controllers screen ---

    def _build_controllers(self) -> ft.Container:
        """Controllers screen: game picker + editable RetroPad remap rows.

        If a game is contextually selected (from detail view), shows its remaps.
        Otherwise shows a game-picker (honest state — no fake rows).
        """
        game = self._state.selected

        sections: list[ft.Control] = [
            ft.Text("Controllers", size=22, weight=ft.FontWeight("w700"), color=T.TEXT_PRIMARY),
            ft.Text(
                "Remap RetroPad buttons per game",
                size=T.SYSTEM_SIZE,
                color=T.TEXT_MUTED,
            ),
        ]

        # Game picker dropdown
        game_options = [
            C.dropdown_option(t.id, t.title)
            for t in self._vm.tiles
        ]

        def _on_game_pick(e: ft.ControlEvent) -> None:
            picked = _find_tile_by_id(self._vm.tiles, e.control.value)
            if picked:
                self._state.selected = picked
                self._set_body(self._build_controllers())
                self._try_update()

        picker = ft.Dropdown(
            label="Game",
            hint_text="Select a game to remap",
            options=game_options,
            value=game.id if game else None,
            on_select=_on_game_pick,
            text_size=14,
            width=320,
            border_color=ft.Colors.with_opacity(0.2, ft.Colors.WHITE),
            focused_border_color=T.ACCENT,
            color=T.TEXT_PRIMARY,
            bgcolor=T.BG_SURFACE,
            tooltip="Choose a game to configure controller mapping",
        )
        sections.append(ft.Container(content=picker, padding=ft.Padding(0, T.SP_8, 0, T.SP_16)))

        if game is None:
            sections.append(
                ft.Text(
                    "Select a game above to view and edit controller mappings.",
                    size=14,
                    color=T.TEXT_MUTED,
                    italic=True,
                )
            )
        else:
            # Resolve remaps via pure core
            input_remap_vm: InputRemapVM | None = None
            if self._ra_config:
                input_remap_vm = self._ra_config.resolve_input_remap_vm(game)

            if input_remap_vm is None:
                sections.append(
                    ft.Text(
                        f"No core configured for {game.title} — cannot resolve remaps.",
                        size=14,
                        color=T.TEXT_MUTED,
                    )
                )
            else:
                sections.append(ft.Text(
                    f"Mapping for: {game.title}",
                    size=16,
                    weight=ft.FontWeight("w600"),
                    color=T.TEXT_PRIMARY,
                ))

                # Editable remap rows — reuse editable_dropdown_row
                for row in input_remap_vm.rows:
                    def _make_change_handler(btn: str):
                        def _handler(val: str) -> None:
                            if self._ra_config and game:
                                self._ra_config.write_input_remap(game, btn, val)
                                self._set_body(self._build_controllers())
                                self._try_update()
                        return _handler

                    sections.append(C.editable_dropdown_row(
                        row.label,
                        row.current_target,
                        row.choices,
                        on_change=_make_change_handler(row.button),
                        tooltip=f"RetroPad {row.label} → target",
                    ))

        content = ft.Column(
            expand=True,
            spacing=T.SP_12,
            scroll=ft.ScrollMode.AUTO,
            controls=sections,
        )
        return ft.Container(content=content, expand=True, padding=T.SP_16 * 2)

    # --- Import screen ---

    def _build_import(self) -> ft.Container:
        """Import / Library Manager screen.

        States: path-entry -> scanning -> preview -> importing -> done.
        Calls pure library_scan/library_import directly (NO MCP server import).
        """
        from .library_scan import scan_directory, ScanResult
        from .library_import import write_gamelist

        sections: list[ft.Control] = [
            ft.Text("Import Games", size=22, weight=ft.FontWeight("w700"), color=T.TEXT_PRIMARY),
            ft.Text(
                "Scan a ROM directory and import new games into your library",
                size=T.SYSTEM_SIZE,
                color=T.TEXT_MUTED,
            ),
        ]

        # State lives in closure — rebuild on each interaction
        if not hasattr(self, "_import_state"):
            self._import_state: dict = {"path": "", "result": None, "done_count": None, "system": ""}

        state = self._import_state

        # System dropdown
        from .library_scan import SYSTEM_EXTENSIONS
        system_options = sorted(SYSTEM_EXTENSIONS.keys())

        def _on_system_pick(e: ft.ControlEvent) -> None:
            state["system"] = e.control.value
            state["result"] = None
            state["done_count"] = None
            self._set_body(self._build_import())
            self._try_update()

        sections.append(ft.Dropdown(
            label="System",
            hint_text="Select target system",
            options=[C.dropdown_option(s, s.upper()) for s in system_options],
            value=state["system"] or None,
            on_select=_on_system_pick,
            text_size=14,
            width=240,
            border_color=ft.Colors.with_opacity(0.2, ft.Colors.WHITE),
            focused_border_color=T.ACCENT,
            color=T.TEXT_PRIMARY,
            bgcolor=T.BG_SURFACE,
            tooltip="System to scan for",
        ))

        # Path entry
        def _on_path_change(e: ft.ControlEvent) -> None:
            state["path"] = e.control.value

        sections.append(ft.TextField(
            label="ROM directory",
            hint_text="/path/to/roms",
            value=state["path"],
            on_change=_on_path_change,
            prefix_icon=ft.Icons.FOLDER_OPEN,
            border_radius=T.SP_8,
            bgcolor=T.BG_SURFACE,
            color=T.TEXT_PRIMARY,
            hint_style=ft.TextStyle(color=T.TEXT_MUTED),
            text_size=14,
            width=480,
            tooltip="Path to directory containing ROM files",
        ))

        # Scan button
        def _on_scan_click(_) -> None:
            if not state["path"] or not state["system"]:
                return
            _existing_ids = frozenset(t.id for t in self._vm.tiles)
            _existing_art_ids = frozenset(t.id for t in self._vm.tiles if t.art_url)
            result = scan_directory(
                Path(state["path"]),
                system=state["system"],
                existing_ids=_existing_ids,
                existing_art_ids=_existing_art_ids,
            )
            state["result"] = result
            state["done_count"] = None
            self._set_body(self._build_import())
            self._try_update()

        sections.append(ft.Container(
            padding=ft.Padding(0, T.SP_8, 0, 0),
            content=ft.ElevatedButton(
                "Scan",
                icon=ft.Icons.SEARCH,
                on_click=_on_scan_click,
                tooltip="Scan directory for ROMs",
                disabled=not (state["path"] and state["system"]),
            ),
        ))

        # Preview results
        result: ScanResult | None = state.get("result")
        if result is not None:
            sections.append(ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
            sections.append(ft.Text(
                f"Found {len(result.candidates)} ROMs",
                size=16, weight=ft.FontWeight("w600"), color=T.TEXT_PRIMARY,
            ))
            sections.append(ft.Row(spacing=T.SP_16, controls=[
                ft.Text(f"Matched: {result.matched}", size=14, color=T.ACCENT),
                ft.Text(f"Metadata only: {result.metadata_only}", size=14, color=T.TEXT_MUTED),
                ft.Text(f"New (unmatched): {result.unmatched}", size=14, color=T.TEXT_PRIMARY),
            ]))

            # Candidate table (compact, max 20 shown)
            display = result.candidates[:20]
            if display:
                rows = [
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(c.title, size=12, color=T.TEXT_PRIMARY)),
                        ft.DataCell(ft.Text(c.status, size=12, color=T.TEXT_MUTED)),
                    ])
                    for c in display
                ]
                sections.append(ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Title", size=12, color=T.TEXT_MUTED)),
                        ft.DataColumn(ft.Text("Status", size=12, color=T.TEXT_MUTED)),
                    ],
                    rows=rows,
                    border_radius=T.SP_8,
                    data_row_max_height=36,
                ))
                if len(result.candidates) > 20:
                    sections.append(ft.Text(
                        f"... and {len(result.candidates) - 20} more",
                        size=12, color=T.TEXT_MUTED, italic=True,
                    ))

            # Import button (only if there are unmatched)
            if result.unmatched > 0:
                def _on_import_click(_) -> None:
                    if not self._media_root:
                        return
                    new_candidates = [c for c in result.candidates if c.status == "unmatched"]
                    gamelist_path = self._media_root / "gamelists" / result.system / "gamelist.xml"
                    count = write_gamelist(new_candidates, gamelist_path, merge=True)
                    state["done_count"] = count
                    self._set_body(self._build_import())
                    self._try_update()

                sections.append(ft.Container(
                    padding=ft.Padding(0, T.SP_12, 0, 0),
                    content=ft.ElevatedButton(
                        f"Import {result.unmatched} new games",
                        icon=ft.Icons.DOWNLOAD,
                        on_click=_on_import_click,
                        bgcolor=T.ACCENT,
                        color=T.TEXT_PRIMARY,
                        tooltip="Import unmatched ROMs into gamelist",
                    ),
                ))

        # Done state
        done_count = state.get("done_count")
        if done_count is not None:
            sections.append(ft.Divider(color=ft.Colors.with_opacity(0.08, ft.Colors.WHITE)))
            gamelist_loc = ""
            if self._media_root and state.get("system"):
                gamelist_loc = str(self._media_root / "gamelists" / state["system"] / "gamelist.xml")
            sections.append(ft.Text(
                f"✓ Imported {done_count} games",
                size=16, weight=ft.FontWeight("w600"), color=T.ACCENT,
            ))
            if gamelist_loc:
                sections.append(ft.Text(
                    f"Written to: {gamelist_loc}",
                    size=T.SYSTEM_SIZE, color=T.TEXT_MUTED,
                ))

        content = ft.Column(
            expand=True,
            spacing=T.SP_12,
            scroll=ft.ScrollMode.AUTO,
            controls=sections,
        )
        return ft.Container(content=content, expand=True, padding=T.SP_16 * 2)

    # --- Snap fetch (UI-state mutation gated on IO result — stays here) ---

    async def _do_snap_fetch(self, game: GameTile) -> None:
        """Background fetch ONE snap from Pi. Race-guarded by game id."""
        if not self._snap_fetcher or not self._media_root:
            return
        target_id = game.id
        dest = self._media_root / game.expected_snap_path
        ok = await self._snap_fetcher.fetch(game.expected_snap_path, dest)
        if not ok:
            return
        # RACE GUARD: only apply if this game is still the selected detail
        if self._state.selected is None or self._state.selected.id != target_id:
            return
        # Mutate the tile in the VM tiles list so future visits see it
        from dataclasses import replace
        updated = replace(game, video_url=game.expected_snap_path)
        idx = next((i for i, t in enumerate(self._vm.tiles) if t.id == target_id), None)
        if idx is not None:
            self._vm.tiles[idx] = updated
        self._state.selected = updated
        self._set_body(self._build_detail(updated))
        self._try_update()
