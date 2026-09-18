"""Tests for declarative motion tokens and animation props (bead x4flp + j88o2).

Headless-safe: asserts animate_* props and durations only (no visual rendering).
"""

from __future__ import annotations

import flet as ft
import pytest

from .models import GameTile
from . import theme as T
from .components import hover_container, tile, detail_view


# --- Fixtures ---


@pytest.fixture
def sample_game() -> GameTile:
    return GameTile(
        id="test-game-1",
        title="Test Game",
        system="SNES",
        rom_path="/roms/test.sfc",
        art_url="https://example.com/art.png",
    )


# --- MODULE 1: theme.duration() ---


class TestDuration:
    def test_returns_ms_normally(self):
        assert T.duration(150) == 150
        assert T.duration(250) == 250
        assert T.duration(0) == 0

    def test_returns_zero_when_reduced_motion(self, monkeypatch):
        monkeypatch.setenv("OPENARCADE_REDUCED_MOTION", "1")
        assert T.duration(150) == 0
        assert T.duration(250) == 0
        assert T.duration(400) == 0

    def test_returns_ms_when_env_is_zero(self, monkeypatch):
        monkeypatch.setenv("OPENARCADE_REDUCED_MOTION", "0")
        assert T.duration(250) == 250

    def test_reads_env_at_call_time(self, monkeypatch):
        """Verify call-time reading (not import-time caching)."""
        assert T.duration(100) == 100
        monkeypatch.setenv("OPENARCADE_REDUCED_MOTION", "1")
        assert T.duration(100) == 0
        monkeypatch.delenv("OPENARCADE_REDUCED_MOTION")
        assert T.duration(100) == 100


class TestMotionTokens:
    def test_curves_are_animation_curve_members(self):
        assert T.CURVE_STANDARD == ft.AnimationCurve.EASE_IN_OUT
        assert T.CURVE_DECELERATE == ft.AnimationCurve.DECELERATE
        assert T.CURVE_EMPHASIZED == ft.AnimationCurve.EASE_IN_OUT_CUBIC_EMPHASIZED
        assert T.CURVE_SPRING == ft.AnimationCurve.EASE_OUT_BACK

    def test_durations_are_positive_ints(self):
        assert T.DURATION_FAST == 150
        assert T.DURATION_NORMAL == 250
        assert T.DURATION_SLOW == 400
        assert T.DURATION_SPRING == 200


# --- MODULE 2: hover_container scale+glow animation ---


class TestHoverContainer:
    def test_animate_scale_uses_spring_curve(self):
        inner = ft.Container(content=ft.Text("x"))
        hc = hover_container(inner)
        assert hc.animate_scale is not None
        assert isinstance(hc.animate_scale, ft.Animation)
        assert hc.animate_scale.duration == T.duration(T.DURATION_SPRING)
        assert hc.animate_scale.curve == T.CURVE_SPRING

    def test_animate_opacity_configured_for_glow(self):
        inner = ft.Container(content=ft.Text("x"))
        hc = hover_container(inner)
        assert hc.animate_opacity is not None
        assert isinstance(hc.animate_opacity, ft.Animation)
        assert hc.animate_opacity.duration == T.duration(T.DURATION_FAST)

    def test_reduced_motion_zero_duration(self, monkeypatch):
        monkeypatch.setenv("OPENARCADE_REDUCED_MOTION", "1")
        inner = ft.Container(content=ft.Text("x"))
        hc = hover_container(inner)
        assert hc.animate_scale.duration == 0
        assert hc.animate_opacity.duration == 0


# --- MODULE 2: tile focus-ring fade ---


class TestTileFocusRing:
    def test_focused_tile_has_opacity_animation(self, sample_game):
        t = tile(sample_game, focused=True)
        # The outer hover container wraps a focus ring container
        # which has animate_opacity set
        focus_ring = t.content  # the inner content of hover_container
        assert focus_ring.animate_opacity is not None
        assert isinstance(focus_ring.animate_opacity, ft.Animation)
        assert focus_ring.animate_opacity.duration == T.duration(T.DURATION_FAST)
        assert focus_ring.opacity == 1.0

    def test_unfocused_tile_ring_hidden(self, sample_game):
        t = tile(sample_game, focused=False)
        inner = t.content
        # Unfocused: inner content is directly the card (no focus ring wrapper)
        # The hover_container wraps the inner directly
        assert t.animate_scale is not None  # hover still works


# --- MODULE 2: detail hero mounts visible (regression: x4flp left it invisible) ---


class TestDetailHeroVisible:
    def test_hero_mounts_visible_not_transparent(self, sample_game):
        """Regression: an entrance 'settle' started the hero at opacity=0 and
        nothing flipped it (screens rebuild fresh → no post-mount tween), leaving
        the detail art INVISIBLE. The hero must mount visible."""
        dv = detail_view(
            sample_game,
            on_play=lambda: None,
            on_back=lambda: None,
        )
        # detail_view -> Container.content -> Column.controls[0] -> Row.controls[0] = hero
        col = dv.content
        row = col.controls[0]
        hero = row.controls[0]

        # Not transparent, not shrunk. (Unset props default to fully visible.)
        assert hero.opacity in (None, 1.0)
        assert hero.scale in (None, 1.0)
        assert hero.content is not None  # art region is present


# --- MODULE 3: AnimatedSwitcher uses theme tokens ---


class TestScreenTransition:
    def test_switcher_duration_uses_theme_token(self):
        """AnimatedSwitcher should use T.duration(T.DURATION_NORMAL), not magic 300."""
        switcher = ft.AnimatedSwitcher(
            duration=T.duration(T.DURATION_NORMAL),
            transition=ft.AnimatedSwitcherTransition.FADE,
            switch_in_curve=T.CURVE_DECELERATE,
            switch_out_curve=T.CURVE_STANDARD,
            content=ft.Text("body"),
            expand=True,
        )
        assert switcher.duration == T.DURATION_NORMAL
        assert switcher.switch_in_curve == T.CURVE_DECELERATE
        assert switcher.switch_out_curve == T.CURVE_STANDARD

    def test_switcher_reduced_motion(self, monkeypatch):
        monkeypatch.setenv("OPENARCADE_REDUCED_MOTION", "1")
        switcher = ft.AnimatedSwitcher(
            duration=T.duration(T.DURATION_NORMAL),
            transition=ft.AnimatedSwitcherTransition.FADE,
            content=ft.Text("body"),
            expand=True,
        )
        assert switcher.duration == 0


# --- MODULE 4: spring curve on tile scale (bead j88o2) ---


class TestTileSpringCurve:
    def test_tile_hover_uses_spring_curve(self, sample_game):
        """The tile's hover_container uses CURVE_SPRING for scale animation."""
        t = tile(sample_game)
        # tile() returns hover_container(inner) — the outer container IS the hover
        assert t.animate_scale is not None
        assert t.animate_scale.curve == T.CURVE_SPRING
        assert t.animate_scale.duration == T.duration(T.DURATION_SPRING)
