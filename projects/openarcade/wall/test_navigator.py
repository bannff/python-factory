"""Tests for wall.navigator — persistent rail, routing, search, systems, focus, keyboard."""

from unittest.mock import MagicMock

import flet as ft

from wall.navigator import Navigator, WallState, LibraryState
from wall.filters import filter_tiles
from wall.models import GameTile, WallViewModel
from wall import chrome as CH


def _tile(title="Test", system="SNES", rom_path="", core=None, playable=True):
    return GameTile(
        id=f"{system}-{title}", title=title, system=system,
        art_url="", rom_path=rom_path, core=core, playable=playable,
    )


def _vm_mixed():
    return WallViewModel(tiles=[
        _tile("Street Fighter II", "SNES"),
        _tile("Mortal Kombat", "SNES"),
        _tile("Killer Instinct", "N64"),
        _tile("Donkey Kong Country", "SNES"),
    ], columns=2)


def _key_event(key: str) -> ft.KeyboardEvent:
    """Minimal KeyboardEvent stub."""
    e = MagicMock(spec=ft.KeyboardEvent)
    e.key = key
    return e


# --- Persistent Rail ---

def test_control_returns_row_with_rail_and_switcher():
    """Root control is a Row containing the rail and the body switcher."""
    nav = Navigator(_vm_mixed())
    root = nav.control
    assert isinstance(root, ft.Row)
    assert len(root.controls) == 2
    assert isinstance(root.controls[0], ft.NavigationRail)


def test_rail_persists_on_detail_view():
    """After selecting a game, the root still contains the rail."""
    nav = Navigator(_vm_mixed())
    game = nav._vm.tiles[0]
    nav.select(game)
    root = nav.control
    assert isinstance(root.controls[0], ft.NavigationRail)
    assert nav.state.selected is game


def test_rail_persists_on_settings():
    """After navigating to settings, rail persists."""
    nav = Navigator(_vm_mixed())
    nav._on_nav_select("settings")
    root = nav.control
    assert isinstance(root.controls[0], ft.NavigationRail)


def test_rail_persists_on_systems():
    """After navigating to systems, rail persists."""
    nav = Navigator(_vm_mixed())
    nav._on_nav_select("systems")
    root = nav.control
    assert isinstance(root.controls[0], ft.NavigationRail)


# --- Nav select changes screen ---

def test_nav_select_changes_current_screen():
    nav = Navigator(_vm_mixed())
    nav._on_nav_select("settings")
    assert nav.state.current_screen == "settings"
    nav._on_nav_select("systems")
    assert nav.state.current_screen == "systems"
    nav._on_nav_select("library")
    assert nav.state.current_screen == "library"


def test_nav_select_clears_selected_game():
    """Navigating away from detail clears the selected game."""
    nav = Navigator(_vm_mixed())
    nav.select(nav._vm.tiles[0])
    assert nav.state.selected is not None
    nav._on_nav_select("settings")
    assert nav.state.selected is None


# --- Systems select ---

def test_systems_select_filters_grid_to_system():
    """Selecting a system from Systems screen sets the filter and goes to library."""
    nav = Navigator(_vm_mixed())
    nav._on_nav_select("systems")
    assert nav.state.current_screen == "systems"
    nav._on_system_selected("N64")
    assert nav.state.current_screen == "library"
    assert nav.library.active_system == "N64"
    # Only N64 tiles should be in the filtered list
    assert all(t.system == "N64" for t in nav._filtered)


# --- Search ---

def test_search_filters_tiles_live():
    """Typing a search query filters the tiles."""
    nav = Navigator(_vm_mixed())
    nav.set_search_query("killer")
    assert len(nav._filtered) == 1
    assert nav._filtered[0].title == "Killer Instinct"


def test_search_clearing_restores_all():
    """Clearing search restores the full tile set."""
    nav = Navigator(_vm_mixed())
    nav.set_search_query("killer")
    assert len(nav._filtered) == 1
    nav.set_search_query("")
    assert len(nav._filtered) == 4


# --- State ---

def test_initial_state_is_wall():
    nav = Navigator(_vm_mixed())
    assert nav.state.selected is None


def test_initial_focus_index_is_zero():
    nav = Navigator(_vm_mixed())
    assert nav.state.focus_index == 0


def test_initial_library_state_no_filters():
    nav = Navigator(_vm_mixed())
    assert nav.library.active_system is None
    assert nav.library.active_letter is None
    assert nav.library.search_query == ""


# --- Select/back ---

def test_select_transitions_to_detail():
    nav = Navigator(_vm_mixed())
    game = nav._vm.tiles[0]
    nav.select(game)
    assert nav.state.selected is game


def test_back_transitions_to_wall():
    nav = Navigator(_vm_mixed())
    nav.select(nav._vm.tiles[1])
    nav.back()
    assert nav.state.selected is None


# --- Filter resets focus ---

def test_set_system_filter_resets_focus():
    nav = Navigator(_vm_mixed())
    nav._state.focus_index = 2
    nav.set_system_filter("SNES")
    assert nav.state.focus_index == 0


# --- Keyboard focus (wall view) ---

def test_key_right_moves_focus():
    nav = Navigator(_vm_mixed())
    nav._on_key(_key_event("Arrow Right"))
    assert nav.state.focus_index == 1


def test_key_down_moves_focus():
    nav = Navigator(_vm_mixed())
    nav._on_key(_key_event("Arrow Down"))
    assert nav.state.focus_index == 2


def test_key_left_at_zero_is_noop():
    nav = Navigator(_vm_mixed())
    nav._on_key(_key_event("Arrow Left"))
    assert nav.state.focus_index == 0


def test_enter_on_wall_selects_focused_tile():
    nav = Navigator(_vm_mixed())
    nav._state.focus_index = 1
    nav._on_key(_key_event("Enter"))
    assert nav.state.selected == nav._vm.tiles[1]


# --- Keyboard detail view ---

def test_escape_on_detail_returns_to_wall():
    nav = Navigator(_vm_mixed())
    nav.select(nav._vm.tiles[0])
    nav._on_key(_key_event("Escape"))
    assert nav.state.selected is None


def test_enter_on_detail_non_playable_is_noop():
    vm = WallViewModel(tiles=[_tile("Locked", playable=False)], columns=2)
    nav = Navigator(vm)
    nav.select(vm.tiles[0])
    nav._on_key(_key_event("Enter"))
    assert nav.state.selected is vm.tiles[0]


# --- Search: must filter in place, never recreate the search field ---

def test_search_updates_grid_in_place_without_rebuilding_body():
    """Typing must NOT swap the switcher content (which would recreate the
    TextField and drop the keystroke). It filters and updates the grid in place."""
    nav = Navigator(_vm_mixed())
    nav._switcher.content = nav._build_library_body()  # establishes nav._grid
    body_before = nav._switcher.content
    grid_before = nav._grid

    nav.set_search_query("street")

    # The body (and thus the live search field) is NOT replaced.
    assert nav._switcher.content is body_before
    assert nav._grid is grid_before
    # Filter actually applied.
    assert nav._filtered and all("street" in t.title.lower() for t in nav._filtered)
    # Grid children reflect the filtered set, updated in place.
    assert len(nav._grid.controls) == len(nav._filtered)
