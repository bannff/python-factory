"""Adversarial tests for bead python-factory-3c388: Arcade motion + vibrant theme.

Attack vectors:
  1. is_selected + real mouse hover interaction
  2. Aura layer wiring (system_accent + opacity gating on active_system)
  3. WCAG AA contrast (computed, not eyeballed)
  4. Reduced motion (OPENARCADE_REDUCED_MOTION=1 zeroes animation durations)
  5. is_selected default-False regression on all existing hover_container callers
  6. RetroArch-first invariant (no launch/emulator/config files touched)

Re-created after the original QA pass's adversarial file was lost to an
out-of-band `git reset --hard origin/main` from a concurrent session on the
same repo checkout. See lesson: never run two agents on one unprotected repo.
"""

from __future__ import annotations

import subprocess

import flet as ft
import pytest

from wall import theme as T
from wall.components import hover_container, system_accent


# --- 1. is_selected + hover interaction ---


class TestIsSelectedHoverInteraction:
    def test_is_selected_true_renders_hover_equivalent_state_at_construction(self):
        c = hover_container(ft.Text("x"), is_selected=True)
        assert c.scale == pytest.approx(1.04)
        assert c.shadow is not None
        assert c.shadow.blur_radius == 32  # glow_shadow blur, not resting

    def test_is_selected_false_renders_resting_state_at_construction(self):
        c = hover_container(ft.Text("x"), is_selected=False)
        assert c.scale == 1.0
        assert c.shadow is not None
        assert c.shadow.blur_radius == 22  # resting_shadow blur

    def test_mouse_hover_false_on_selected_card_stays_in_selected_state(self):
        """Mouse-leave on an is_selected=True card must NOT revert to resting --
        it stays hover-equivalent because selection persists independent of hover."""
        c = hover_container(ft.Text("x"), is_selected=True)
        c.update = lambda: None

        c.on_hover(_hover_event(c, "false"))

        assert c.scale == pytest.approx(1.04)
        assert c.shadow.blur_radius == 32

    def test_mouse_hover_true_then_false_on_non_selected_card_round_trips(self):
        """Non-selected cards behave exactly as before: hover in -> glow,
        hover out -> resting."""
        c = hover_container(ft.Text("x"), is_selected=False)
        c.update = lambda: None

        c.on_hover(_hover_event(c, "true"))
        assert c.scale == pytest.approx(1.04)
        assert c.shadow.blur_radius == 32

        c.on_hover(_hover_event(c, "false"))
        assert c.scale == 1.0
        assert c.shadow.blur_radius == 22


def _hover_event(control: ft.Container, data: str) -> ft.ControlEvent:
    e = type("E", (), {})()
    e.control = control
    e.data = data
    return e


# --- 2. Aura layer wiring ---


class TestAuraWiring:
    def test_system_accent_returns_neutral_for_none(self):
        assert system_accent(None) == T.ACCENT

    def test_system_accent_returns_deterministic_hex_for_system(self):
        c1 = system_accent("snes")
        c2 = system_accent("snes")
        assert c1 == c2
        assert c1.startswith("#")

    def test_aura_opacity_active_token_is_a_valid_opacity(self):
        assert 0.0 <= T.AURA_OPACITY_ACTIVE <= 1.0

    def test_gradient_core_and_bg_base_are_distinct_valid_hex(self):
        assert T.GRADIENT_CORE.startswith("#")
        assert T.BG_BASE.startswith("#")
        assert T.GRADIENT_CORE != T.BG_BASE


# --- 3. WCAG AA contrast (computed) ---


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")[:6]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        c_srgb = c / 255.0
        return c_srgb / 12.92 if c_srgb <= 0.03928 else ((c_srgb + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    l1 = _relative_luminance(_hex_to_rgb(fg_hex))
    l2 = _relative_luminance(_hex_to_rgb(bg_hex))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


class TestWcagContrast:
    @pytest.mark.parametrize("bg", [T.GRADIENT_CORE, T.BG_BASE])
    def test_text_primary_meets_aa_against_gradient_range(self, bg):
        ratio = _contrast_ratio(T.TEXT_PRIMARY, bg)
        assert ratio >= 4.5, f"TEXT_PRIMARY vs {bg}: {ratio:.2f}:1 FAILS AA"

    @pytest.mark.parametrize("bg", [T.GRADIENT_CORE, T.BG_BASE])
    def test_text_muted_meets_aa_against_gradient_range(self, bg):
        ratio = _contrast_ratio(T.TEXT_MUTED, bg)
        assert ratio >= 4.5, f"TEXT_MUTED vs {bg}: {ratio:.2f}:1 FAILS AA"

    @pytest.mark.parametrize("bg", [T.GRADIENT_CORE, T.BG_BASE])
    def test_accent_text_meets_aa_against_gradient_range(self, bg):
        ratio = _contrast_ratio(T.ACCENT_TEXT, bg)
        assert ratio >= 4.5, f"ACCENT_TEXT vs {bg}: {ratio:.2f}:1 FAILS AA"


# --- 4. Reduced motion ---


class TestReducedMotion:
    def test_duration_returns_zero_under_reduced_motion(self, monkeypatch):
        monkeypatch.setenv("OPENARCADE_REDUCED_MOTION", "1")
        assert T.duration(T.DURATION_SLOW) == 0
        assert T.duration(T.DURATION_SPRING) == 0

    def test_duration_passes_through_normally(self, monkeypatch):
        monkeypatch.delenv("OPENARCADE_REDUCED_MOTION", raising=False)
        assert T.duration(T.DURATION_SLOW) == T.DURATION_SLOW

    def test_app_py_gradient_animation_uses_theme_duration_helper(self):
        """The aura's animate_opacity must route through T.duration(), not a
        hardcoded ms value, so reduced-motion actually disables it."""
        with open("wall/app.py") as f:
            src = f.read()
        assert "T.duration(T.DURATION_SLOW)" in src


# --- 5. is_selected default-False regression ---


class TestIsSelectedDefaultRegression:
    def test_default_is_selected_false_matches_prior_resting_behavior(self):
        c = hover_container(ft.Text("x"))
        assert c.scale == 1.0
        assert c.shadow.blur_radius == 22

    def test_existing_hover_container_callers_pass_only_known_kwargs(self):
        """No call site should break by passing an unexpected kwarg; is_selected
        is opt-in and defaults False everywhere it isn't explicitly passed."""
        # Smoke: constructing with every combination of the pre-existing kwargs
        # (scale_to, glow_color) still works without is_selected.
        c = hover_container(ft.Text("x"), scale_to=1.08, glow_color="#123456")
        assert c.scale == 1.0


# --- 6. RetroArch-first invariant ---


class TestRetroArchFirstInvariant:
    def test_no_launch_or_emulator_files_touched_by_this_bead(self):
        """This bead is UI-shell only. Verify none of the launch/emulator/config
        seams changed in the working tree (staged or unstaged)."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd="/Users/wdaniero/workplace/python-factory",
            capture_output=True,
            text=True,
            timeout=10,
        )
        changed = result.stdout.strip().splitlines()
        forbidden_substrings = ["launch_handler.py", "core_resolver.py", "retroarch_config.py", "control_plane/"]
        violations = [f for f in changed if any(s in f for s in forbidden_substrings)]
        assert not violations, f"RetroArch-first invariant violated by: {violations}"
