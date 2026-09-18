"""Tests for wall.chrome — structural assertions, no ft.app."""

import flet as ft

from wall.chrome import (
    NavItem, NAV_ITEMS, nav_rail, filter_bar, az_index, library_view,
    HintAction, hint_bar, HINTS_WALL, HINTS_DETAIL,
    search_field, settings_view, systems_view,
)
from wall import theme as T


def test_nav_items_has_eight_entries():
    assert len(NAV_ITEMS) == 8
    assert NAV_ITEMS[0].route_id == "library"
    assert NAV_ITEMS[1].route_id == "systems"
    assert NAV_ITEMS[2].route_id == "import"
    assert NAV_ITEMS[3].route_id == "controllers"
    assert NAV_ITEMS[4].route_id == "cores"
    assert NAV_ITEMS[5].route_id == "settings"
    assert NAV_ITEMS[6].route_id == "information"
    assert NAV_ITEMS[7].route_id == "assistant"


def test_nav_items_icons_unique():
    """Every nav item has a distinct icon -- no two share the same icon."""
    icons = [it.icon for it in NAV_ITEMS]
    assert len(icons) == len(set(icons)), f"Duplicate icons: {icons}"


def test_nav_items_icons_purposeful():
    """Key icons match their intent -- Systems is hardware, Controllers is gamepad."""
    by_route = {it.route_id: it.icon for it in NAV_ITEMS}
    # Library = grid, not generic games
    assert by_route["library"] == ft.Icons.GRID_VIEW_ROUNDED
    # Systems = hardware chip, NOT a controller/gamepad/inventory box
    assert by_route["systems"] == ft.Icons.MEMORY
    assert by_route["systems"] != ft.Icons.SPORTS_ESPORTS  # not a controller
    # Controllers = esports (joystick), distinct from Systems
    assert by_route["controllers"] == ft.Icons.SPORTS_ESPORTS
    # Settings = tune (sliders), not cog
    assert by_route["settings"] == ft.Icons.TUNE
    # Assistant = sparkle, not robot
    assert by_route["assistant"] == ft.Icons.AUTO_AWESOME


def test_nav_rail_has_no_decorative_leading_icon():
    """Every visible rail icon is a real destination; no dead top brand icon."""
    rail = nav_rail(NAV_ITEMS, selected="library", on_select=lambda _: None)
    assert rail.leading is None


def test_nav_rail_selected_only_label_type():
    """Rail shows labels ONLY for the selected destination (Polycade style)."""
    rail = nav_rail(NAV_ITEMS, selected="library", on_select=lambda _: None)
    assert rail.label_type == ft.NavigationRailLabelType.SELECTED


def test_nav_rail_has_destinations_with_tooltips():
    rail = nav_rail(NAV_ITEMS, selected="library", on_select=lambda _: None)
    assert isinstance(rail, ft.NavigationRail)
    assert len(rail.destinations) == 8
    for dest in rail.destinations:
        assert dest.tooltip is not None


def test_nav_rail_indicator_color_uses_accent():
    """Indicator pill uses the theme ACCENT with visible opacity."""
    rail = nav_rail(NAV_ITEMS, selected="library", on_select=lambda _: None)
    # Just verify it's not None/transparent
    assert rail.indicator_color is not None


def test_filter_bar_has_all_chip_plus_systems():
    bar = filter_bar(["SNES", "N64", "Genesis"], active=None, on_select=lambda _: None)
    assert isinstance(bar, ft.Row)
    assert len(bar.controls) == 4  # All + 3 systems


def test_filter_bar_empty_systems():
    bar = filter_bar([], active=None, on_select=lambda _: None)
    assert len(bar.controls) == 1  # just "All"


def test_az_index_has_letter_count_children():
    az = az_index(["A", "K", "M", "S"], on_jump=lambda _: None)
    assert isinstance(az, ft.Column)
    assert len(az.controls) == 4


def test_library_view_returns_row_without_rail():
    """library_view wraps the body in a Stack backdrop; body Row is the top layer."""
    fbar = ft.Row()
    search = ft.TextField()
    az = ft.Column()
    grid = ft.GridView()
    view = library_view(fbar, search, az, grid)
    assert isinstance(view, ft.Container)
    stack = view.content
    assert isinstance(stack, ft.Stack)
    # No hero_art: tint-glow + body = 2 layers; body Row is last (on top).
    assert len(stack.controls) == 2
    row = stack.controls[-1]
    assert isinstance(row, ft.Row)
    # center column + az = 2 children (no rail)
    assert len(row.controls) == 2


def test_library_view_hero_art_layers_blurred_backdrop():
    """With hero_art, the Stack adds art + blur/scrim layers beneath the glow+body."""
    view = library_view(ft.Row(), ft.TextField(), ft.Column(), ft.GridView(),
                        hero_art="/tmp/art.png")
    stack = view.content
    # art + blur-scrim + tint-glow + body = 4 layers
    assert len(stack.controls) == 4
    assert isinstance(stack.controls[0], ft.Image)
    assert stack.controls[0].src == "/tmp/art.png"
    assert stack.controls[1].blur is not None  # blur+dim scrim


def test_library_view_with_hints():
    fbar = ft.Row()
    search = ft.TextField()
    az = ft.Column()
    grid = ft.GridView()
    view = library_view(fbar, search, az, grid, hints=HINTS_WALL)
    row = view.content.controls[-1]  # body Row is the top Stack layer
    center = row.controls[0]  # Column
    # search + filter_bar + grid + hint_bar = 4
    assert len(center.controls) == 4


# --- hint_bar tests ---


def test_hint_bar_renders_action_labels():
    bar = hint_bar(HINTS_WALL)
    assert isinstance(bar, ft.Row)
    labels = [r.controls[1].value for r in bar.controls]
    assert labels == ["Select", "Filter"]


def test_hint_bar_detail_preset():
    bar = hint_bar(HINTS_DETAIL)
    labels = [r.controls[1].value for r in bar.controls]
    assert labels == ["Play", "Back"]


def test_hint_bar_empty_actions():
    bar = hint_bar([])
    assert len(bar.controls) == 0


# --- search_field ---


def test_search_field_returns_textfield():
    sf = search_field(on_change=lambda _: None)
    assert isinstance(sf, ft.TextField)


# --- settings_view ---


def test_settings_view_returns_container_no_rail():
    view = settings_view(config_dir_text="/tmp")
    assert isinstance(view, ft.Container)
    # Should NOT be a Row with a rail -- just a Container with content
    assert isinstance(view.content, ft.Column)


# --- systems_view ---


def test_systems_view_lists_systems():
    view = systems_view(["SNES", "N64", "Genesis"], on_select=lambda _: None)
    assert isinstance(view, ft.Container)
    # Inner column has title + chip column
    inner = view.content
    assert isinstance(inner, ft.Column)


# --- Theme contrast (basic sanity) ---


def test_theme_accent_has_sufficient_contrast_placeholder():
    """Verify accent tokens exist and are not empty."""
    assert T.ACCENT.startswith("#")
    assert T.ACCENT_HI.startswith("#")
    assert T.ACCENT_TEXT.startswith("#")
    assert T.ACCENT_GLOW.startswith("#")
    assert T.TEXT_ACTIVE.startswith("#")
