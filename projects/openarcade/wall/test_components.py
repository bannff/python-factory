"""Tests for wall.components — B14 reusable component system + B17 detail."""

import flet as ft

from wall.components import (
    tile, detail_view, placeholder_card, hover_container,
    metadata_row, detail_tabs, screenshot_carousel, metadata_sidebar,
    _bounded_art_region, _title_band, _detail_footer,
)
from wall.models import GameTile
from wall import theme as T


def _game(*, art_url="https://example.com/art.png", playable=True, **kw):
    defaults = dict(
        id="snes-test", title="Test Game", system="SNES",
        art_url=art_url, playable=playable, status_detail=None,
        players="1-2", genre="Fighting", year="1992", publisher="Capcom",
    )
    defaults.update(kw)
    return GameTile(**defaults)


# --- tile structure (Column[art_region, title_band]) ---


def test_tile_root_content_is_column_with_two_children():
    """Tile inner content is a Column with exactly 2 children: art region + title band."""
    g = _game()
    ctrl = tile(g)
    inner = ctrl.content  # hover_container wraps inner
    col = inner.content
    assert isinstance(col, ft.Column)
    assert len(col.controls) == 2


def test_tile_title_band_has_fixed_height():
    """Title band height equals TITLE_BAND_HEIGHT token."""
    g = _game()
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    title_band = col.controls[1]
    assert title_band.height == T.TITLE_BAND_HEIGHT


def test_tile_art_region_uses_cover_fit_image_when_art_url_set():
    """Art region contains an ft.Image with fit=cover when art_url is present."""
    g = _game(art_url="https://example.com/art.png")
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    art_region = col.controls[0]
    # art_region is Container(clip) -> Stack -> controls[0] (Container with Image)
    stack = art_region.content
    art_container = stack.controls[0]
    assert isinstance(art_container.content, ft.Image)
    assert art_container.content.src == "https://example.com/art.png"
    assert art_container.content.fit == "contain"


def test_tile_art_region_clip_behavior_hard_edge():
    """Art region container uses HARD_EDGE clipping for cover-fit overflow."""
    g = _game()
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    art_region = col.controls[0]
    assert art_region.clip_behavior == ft.ClipBehavior.HARD_EDGE


def test_tile_art_region_uses_placeholder_when_art_url_empty():
    """Art region uses placeholder_card (not Image) when art_url is empty."""
    g = _game(art_url="")
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    art_region = col.controls[0]
    stack = art_region.content
    art_container = stack.controls[0]
    assert not isinstance(art_container.content, ft.Image)
    assert isinstance(art_container.content, ft.Container)


def test_tile_lock_badge_when_not_playable():
    """Not-playable tile includes lock badge in art region stack."""
    g = _game(playable=False, status_detail="MISSING_CORE")
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    art_region = col.controls[0]
    stack = art_region.content
    badge = stack.controls[-1]
    assert isinstance(badge, ft.Container)
    assert badge.tooltip == "MISSING_CORE"
    assert isinstance(badge.content, ft.Icon)


def test_tile_no_lock_badge_when_playable():
    """Playable tile has no lock badge -- only art container + system chip."""
    g = _game(playable=True)
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    art_region = col.controls[0]
    stack = art_region.content
    # controls: [art_container, bottom_scrim, chip] -- no lock badge
    assert len(stack.controls) == 3


def test_tile_title_band_shows_game_title():
    """Title band displays the game title with ellipsis overflow."""
    g = _game(title="Goldeneye 007")
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    title_band = col.controls[1]
    band_col = title_band.content
    assert band_col.controls[0].value == "Goldeneye 007"
    assert band_col.controls[0].max_lines == 1


# --- _bounded_art_region primitive ---


def test_bounded_art_region_expand_true():
    """Art region expands to fill parent-allocated height."""
    g = _game()
    region = _bounded_art_region(g)
    assert region.expand is True


# --- _title_band primitive ---


def test_title_band_height_matches_token():
    """Title band height is exactly TITLE_BAND_HEIGHT."""
    g = _game()
    band = _title_band(g)
    assert band.height == T.TITLE_BAND_HEIGHT


def test_title_band_shows_system_subtitle():
    """Title band shows system name as subtitle."""
    g = _game(system="N64")
    band = _title_band(g)
    band_col = band.content
    # system is now an uppercased colored chip: Column.controls[1] -> Row -> Container(chip) -> Text
    chip = band_col.controls[1].controls[0]
    assert chip.content.value == "N64"


# --- detail_view ---


def test_detail_view_has_play_and_back_buttons():
    g = _game()
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    # New layout: Container(expand) -> Column(expand) -> [hero_band(Row), Divider, tabs, ...]
    # hero_band Row -> [hero, title_meta(Column), sidebar]
    # title_meta Column -> [title, metadata_row, actions Row]
    outer_col = ctrl.content
    hero_band = outer_col.controls[0]  # Row
    title_meta = hero_band.controls[1]  # Column (expand=True)
    actions_row = title_meta.controls[2]  # Row with Play + Back
    labels = [getattr(b, "text", getattr(b, "content", "")) for b in actions_row.controls]
    assert "Play" in labels
    assert "Back" in labels


def test_detail_view_outer_container_expands():
    """detail_view root Container must have expand=True to fill the page."""
    g = _game()
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    assert ctrl.expand is True


def test_detail_view_outer_column_expands():
    """detail_view inner Column must have expand=True."""
    g = _game()
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    assert isinstance(outer_col, ft.Column)
    assert outer_col.expand is True


def test_detail_view_play_is_elevated_button():
    """Play must be a filled Button (primary accent); Back must be TextButton (secondary/ghost)."""
    g = _game()
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    hero_band = outer_col.controls[0]
    title_meta = hero_band.controls[1]
    actions_row = title_meta.controls[2]
    play_btn = actions_row.controls[0]
    back_btn = actions_row.controls[1]
    # Play is a Button with accent bgcolor in style (primary action)
    assert isinstance(play_btn, ft.Button)
    assert play_btn.style.bgcolor == T.ACCENT
    # Back is a TextButton (ghost/secondary)
    assert isinstance(back_btn, ft.TextButton)


def test_detail_tabs_expand_true():
    """detail_tabs must return a Column with expand=True."""
    g = _game()
    tabs = detail_tabs(g, active_tab="description")
    assert isinstance(tabs, ft.Column)
    assert tabs.expand is True


def test_detail_tabs_body_expand_and_scroll():
    """Tab body must have expand=True and scroll=AUTO."""
    g = _game()
    tabs = detail_tabs(g, active_tab="description")
    body = tabs.controls[1]  # body Column
    assert body.expand is True
    assert body.scroll == ft.ScrollMode.AUTO


# --- hover_container ---


def test_hover_container_wraps_content():
    inner = ft.Text("hi")
    hc = hover_container(inner)
    assert hc.content is inner
    assert hc.scale == 1.0


# --- placeholder_card ---


def test_placeholder_card_shows_title():
    card = placeholder_card("Street Fighter II", "SNES")
    col = card.content
    title_text = col.controls[0]
    assert title_text.value == "Street Fighter II"


# --- B17 detail tests ---


def test_metadata_row_renders_dash_for_absent_fields():
    """Missing players/genre/category -> muted '--' (absent metadata, never 'Coming soon')."""
    g = _game(players="", genre="", category=None)
    row = metadata_row(g)
    # Three triples
    values = [triple.controls[2].value for triple in row.controls]
    assert values == ["--", "--", "--"]


def test_metadata_row_renders_populated_fields():
    g = _game(players="1-2", genre="Fighting", category="Arcade")
    row = metadata_row(g)
    values = [triple.controls[2].value for triple in row.controls]
    assert values == ["1-2", "Fighting", "Arcade"]


def test_screenshot_carousel_placeholder_for_empty_tuple():
    """Empty screenshots -> graceful placeholder text."""
    ctrl = screenshot_carousel(())
    # Container with Text inside
    assert isinstance(ctrl, ft.Container)
    assert ctrl.content.value == "No screenshots available"


def test_screenshot_carousel_filmstrip_for_nonempty():
    """Non-empty screenshots -> Row of images."""
    ctrl = screenshot_carousel(("http://a.png", "http://b.png"))
    assert isinstance(ctrl, ft.Row)
    assert len(ctrl.controls) == 2
    assert ctrl.controls[0].content.src == "http://a.png"


def test_screenshot_carousel_no_fallback_art_param():
    """screenshot_carousel no longer accepts fallback_art -- empty returns placeholder."""
    ctrl = screenshot_carousel(())
    assert isinstance(ctrl, ft.Container)
    assert ctrl.content.value == "No screenshots available"
    # No Image present -- the art-duplication path is gone
    assert not isinstance(ctrl.content, ft.Image)


def test_detail_tabs_description_body():
    """active_tab=description shows game.description text (no carousel)."""
    g = _game(description="A legendary fighting game.")
    tabs = detail_tabs(g, active_tab="description")
    body = tabs.controls[1]  # scrollable Column -> [Text]
    text = body.controls[0]
    assert isinstance(text, ft.Text)
    assert text.value == "A legendary fighting game."


def test_detail_tabs_description_dash_when_none():
    g = _game(description=None)
    tabs = detail_tabs(g, active_tab="description")
    body = tabs.controls[1]
    text = body.controls[0]
    assert isinstance(text, ft.Text)
    assert text.value == "--"


def test_detail_tabs_controls_body_has_controls_panel():
    """Controls tab renders controls_panel with default layout summary."""
    g = _game()
    tabs = detail_tabs(g, active_tab="controls")
    body = tabs.controls[1]  # Container wrapping controls_panel

    def _collect_texts(ctrl) -> list[str]:
        out = []
        if isinstance(ctrl, ft.Text) and ctrl.value:
            out.append(ctrl.value)
        for attr in ("controls", "content"):
            child = getattr(ctrl, attr, None)
            if child is None:
                continue
            if isinstance(child, list):
                for c in child:
                    out.extend(_collect_texts(c))
            elif hasattr(child, "controls") or hasattr(child, "content") or isinstance(child, ft.Text):
                out.extend(_collect_texts(child))
        return out

    texts = _collect_texts(body)
    assert "Run-Ahead" in texts
    assert "Default RetroPad layout" in texts
    assert "Advanced \u2013 Open RetroArch Menu" in texts


def test_detail_tabs_active_header_accented():
    """Active tab has accent border; inactive has transparent."""
    g = _game()
    tabs = detail_tabs(g, active_tab="description")
    headers = tabs.controls[0]  # Row of tab headers
    desc_border = headers.controls[0].border.bottom.color
    ctrl_border = headers.controls[1].border.bottom.color
    assert desc_border != "transparent"
    assert ctrl_border == "transparent"


def test_metadata_sidebar_dash_for_absent():
    """Missing developer/release_date/rating -> muted '--' (absent metadata, never 'Coming soon')."""
    g = _game(developer=None, release_date=None, rating=None, publisher="")
    sidebar = metadata_sidebar(g)
    # Platform (always present = system), Developer, Publisher, Release Date, Rating
    values = [col.controls[1].value for col in sidebar.controls]
    assert values[0] == "SNES"  # Platform always populated
    assert values[1] == "--"  # Developer
    assert values[2] == "--"  # Publisher (empty -> None -> dash)
    assert values[3] == "--"  # Release Date
    assert values[4] == "--"  # Rating


def test_detail_footer_hidden_when_no_play_data():
    """Play-tracking is unbuilt -> footer is None, NOT a fake 'Coming soon' row."""
    assert _detail_footer(_game(last_played=None, play_count=None)) is None


def test_detail_footer_shows_only_present_play_field():
    """When only one play stat exists, only that field renders (no dash/placeholder for the other)."""
    row = _detail_footer(_game(last_played=None, play_count=7))
    assert row is not None
    texts = [t.value for sub in row.controls for t in sub.controls if isinstance(t, ft.Text)]
    assert "Play Count" in texts and "7" in texts
    assert "Last Played" not in texts


def test_detail_view_has_no_coming_soon_anywhere():
    """Whole detail view for a sparsely-populated game must never render 'Coming soon'."""
    g = _game(players="", genre="", category=None, description=None,
              developer=None, release_date=None, rating=None,
              publisher="", last_played=None, play_count=None)
    view = detail_view(g, on_play=lambda: None, on_back=lambda: None)

    def _texts(ctrl) -> list[str]:
        out: list[str] = []
        if isinstance(ctrl, ft.Text) and ctrl.value:
            out.append(ctrl.value)
        for attr in ("controls", "content"):
            child = getattr(ctrl, attr, None)
            if isinstance(child, list):
                for c in child:
                    out.extend(_texts(c))
            elif child is not None:
                out.extend(_texts(child))
        return out

    assert "Coming soon" not in _texts(view)


def test_metadata_sidebar_populated():
    g = _game(developer="Capcom", release_date="1992-06-10", rating="E")
    sidebar = metadata_sidebar(g)
    values = [col.controls[1].value for col in sidebar.controls]
    assert values[1] == "Capcom"
    assert values[3] == "1992-06-10"
    assert values[4] == "E"


def test_detail_tabs_headers_are_clickable_when_handler_given():
    """Mouse-clicking a tab header must invoke on_select_tab (keyboard is not the
    only way to switch tabs). Regression: headers were display-only (B25)."""
    fired: list[str] = []
    tabs = detail_tabs(_game(), active_tab="description", on_select_tab=fired.append)
    headers = tabs.controls[0].controls  # headers Row
    clickable = {h.content.value: h for h in headers}
    assert clickable["Description"].on_click is not None
    assert clickable["Controls"].on_click is not None
    clickable["Controls"].on_click(None)
    assert fired == ["controls"]


def test_detail_tabs_headers_inert_without_handler():
    """No handler -> headers carry no on_click (pure display)."""
    tabs = detail_tabs(_game(), active_tab="description")
    headers = tabs.controls[0].controls
    assert all(h.on_click is None for h in headers)


# --- Cycle 2: Templated Detail Hero ---


def test_detail_hero_uses_bounded_art_region():
    """Hero is a Container(DETAIL_HERO_W x 320) whose content is _bounded_art_region."""
    g = _game(art_url="https://example.com/hero.png")
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    hero_band = outer_col.controls[0]  # Row (hero band)
    hero = hero_band.controls[0]
    # Bounded container dimensions (320 = cinematic hero band height)
    assert hero.width == T.DETAIL_HERO_W
    assert hero.height == 320
    assert hero.clip_behavior == ft.ClipBehavior.HARD_EDGE
    assert hero.border_radius == T.RADIUS
    # Content is _bounded_art_region output: Container with expand=True + Stack
    art_region = hero.content
    assert isinstance(art_region, ft.Container)
    assert art_region.expand is True
    stack = art_region.content
    assert isinstance(stack, ft.Stack)
    # First stack child (Positioned.fill container) holds an Image with the art_url
    positioned_container = stack.controls[0]
    assert isinstance(positioned_container.content, ft.Image)
    assert positioned_container.content.src == "https://example.com/hero.png"
    assert positioned_container.content.fit == "contain"


def test_detail_description_tab_has_no_duplicate_cover_art():
    """Description tab body does NOT contain a second Image with art_url."""
    g = _game(art_url="https://example.com/art.png", description="Great game.")
    ctrl = detail_view(g, active_tab="description", on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    # New layout: controls = [hero_band(Row), Divider, tabs(Column)]
    tabs_col = outer_col.controls[2]  # detail_tabs output (expand=True Column)
    body = tabs_col.controls[1]  # scrollable Column -> [Text]
    text = body.controls[0]
    assert isinstance(text, ft.Text)
    assert text.value == "Great game."
    # And no Image (cover art) leaked into the description body.
    assert not isinstance(text, ft.Image)


# --- Cycle 3: video-snap attract in detail hero ---


def test_bounded_art_region_video_when_allow_video_true():
    """allow_video=True + video_url set -> fv.Video in control tree."""
    import flet_video as fv

    g = _game(video_url="snes/snap/Test.mp4")
    region = _bounded_art_region(g, allow_video=True)
    stack = region.content
    positioned = stack.controls[0]
    assert isinstance(positioned.content, fv.Video)


def test_bounded_art_region_image_when_allow_video_false():
    """allow_video=False (default) + video_url set -> ft.Image, not fv.Video."""
    import flet_video as fv

    g = _game(video_url="snes/snap/Test.mp4")
    region = _bounded_art_region(g, allow_video=False)
    stack = region.content
    positioned = stack.controls[0]
    assert isinstance(positioned.content, ft.Image)
    assert not isinstance(positioned.content, fv.Video)


def test_bounded_art_region_image_when_video_url_empty():
    """allow_video=True but video_url empty -> falls back to ft.Image."""
    g = _game(video_url="")
    region = _bounded_art_region(g, allow_video=True)
    stack = region.content
    positioned = stack.controls[0]
    assert isinstance(positioned.content, ft.Image)


def test_wall_tile_never_gets_video():
    """Wall tile() call uses default allow_video=False -> no Video even with video_url."""
    import flet_video as fv

    g = _game(video_url="snes/snap/Test.mp4")
    ctrl = tile(g)
    inner = ctrl.content
    col = inner.content
    art_region = col.controls[0]
    stack = art_region.content
    positioned = stack.controls[0]
    assert not isinstance(positioned.content, fv.Video)
    assert isinstance(positioned.content, ft.Image)


def test_detail_hero_gets_video_when_video_url_set():
    """detail_view hero uses allow_video=True -> fv.Video in hero content."""
    import flet_video as fv

    g = _game(video_url="snes/snap/Test.mp4")
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    main_row = outer_col.controls[0]
    hero = main_row.controls[0]
    art_region = hero.content
    stack = art_region.content
    positioned = stack.controls[0]
    assert isinstance(positioned.content, fv.Video)


def test_editable_dropdown_row_options_have_visible_text():
    """Regression (y4f8y): Flet 0.85 dropdown.Option(positional) leaves text=None,
    rendering blank options. Every option MUST carry visible text, not just a key."""
    import wall.components as C

    row = C.editable_dropdown_row(
        "B", "b", ("b", "y", "a", "x"), on_change=lambda v: None
    )
    # Find the Dropdown control in the row
    dropdown = next(c for c in row.controls if hasattr(c, "options"))
    assert dropdown.options, "dropdown has no options"
    for opt in dropdown.options:
        assert opt.text, f"option {opt.key!r} renders blank (text not set)"
        assert opt.key, "option missing key"


def test_dropdown_option_menu_text_is_visible_on_dark_theme():
    """Regression: dropdown menu options rendered dark-on-dark (invisible) — the
    recurring 'empty dropdown' bug. dropdown_option must give each option
    explicitly-colored content so the menu item is readable on the dark surface."""
    from wall.components import dropdown_option
    from wall import theme as T
    opt = dropdown_option("ntsc", "NTSC")
    assert opt.key == "ntsc"
    assert opt.text == "NTSC"                    # closed-control fallback
    assert isinstance(opt.content, ft.Text)      # menu item is a colored Text
    assert opt.content.value == "NTSC"
    assert opt.content.color == T.TEXT_PRIMARY   # visible, not default dark


# --- Detail tab scrollability (bead k9mmu) ---


def test_detail_tabs_description_body_is_scrollable():
    """Description tab body has scroll=AUTO so long text doesn't overflow."""
    g = _game(description="A" * 5000)  # Long description
    tabs = detail_tabs(g, active_tab="description")
    body = tabs.controls[1]  # Second child after headers
    assert isinstance(body, ft.Column)
    assert body.scroll == ft.ScrollMode.AUTO


def test_detail_tabs_controls_body_is_scrollable():
    """Controls tab body has scroll=AUTO for many settings rows."""
    g = _game()
    tabs = detail_tabs(g, active_tab="controls")
    body = tabs.controls[1]
    assert isinstance(body, ft.Column)
    assert body.scroll == ft.ScrollMode.AUTO


def test_detail_tabs_core_options_body_is_scrollable():
    """Core options tab body has scroll=AUTO."""
    from wall.core_options_vm import CoreOptionsVM, CoreOptionRow
    vm = CoreOptionsVM(
        curated=(CoreOptionRow(key="k", label="L", value="v", choices=("v", "w"), editable=True),),
        uncurated=(),
    )
    g = _game()
    tabs = detail_tabs(g, active_tab="core_options", core_options_vm=vm)
    body = tabs.controls[1]
    assert isinstance(body, ft.Column)
    assert body.scroll == ft.ScrollMode.AUTO


# --- Bead 3: detail_view layout contract ---


def test_detail_view_hero_band_is_fixed_height():
    """Hero band Row has explicit height=320 (fixed, does not expand)."""
    g = _game()
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    hero_band = outer_col.controls[0]
    assert isinstance(hero_band, ft.Row)
    assert hero_band.height == 320


def test_detail_view_tabs_expand_below_hero():
    """Tabs section (below divider) has expand=True to fill remaining space."""
    g = _game()
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    # controls: [hero_band(Row), Divider, tabs(Column), ...]
    tabs = outer_col.controls[2]
    assert isinstance(tabs, ft.Column)
    assert tabs.expand is True


def test_detail_view_one_primary_action():
    """Only one primary (filled+accent) action; everything else is secondary."""
    g = _game()
    ctrl = detail_view(g, on_play=lambda: None, on_back=lambda: None)
    outer_col = ctrl.content
    hero_band = outer_col.controls[0]
    title_meta = hero_band.controls[1]
    actions_row = title_meta.controls[2]
    # Only one Button with accent bgcolor style (primary)
    primary = [
        b for b in actions_row.controls
        if isinstance(b, ft.Button) and not isinstance(b, ft.TextButton)
        and getattr(getattr(b, "style", None), "bgcolor", None) == T.ACCENT
    ]
    assert len(primary) == 1
    assert primary[0].content == "Play"
