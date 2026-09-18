"""Design tokens for the OpenArcade wall. Single source of truth for visuals."""

from __future__ import annotations

import os

import flet as ft

# --- Colors ---
BG_BASE = "#08080D"  # deeper black for cinema feel
BG_SURFACE = "#14141F"  # slightly cooler/darker surface
BG_SURFACE_HI = "#1E1E30"  # cooler purple-tinted highlight
HAIRLINE = "#FFFFFF14"  # ~0.08 white top-edge highlight so cards catch light
ACCENT = "#7C3AED"  # violet-600, vibrant arcade purple for large UI surfaces/rings
ACCENT_HI = "#A78BFA"  # violet-400, for gradient brand header + active labels
ACCENT_TEXT = "#C4B5FD"  # violet-300, AA-safe accent for small text on dark surfaces
ACCENT_GLOW = "#5B21B6"  # violet-800, subtle glow/ring tint
GRADIENT_CORE = "#1A0A2E"  # deep violet glow core -- dark enough to preserve text contrast
AURA_OPACITY_ACTIVE = 0.14  # system-tint aura opacity when a system filter is active
TEXT_PRIMARY = "#F5F5FA"
TEXT_MUTED = "#94A3B8"  # slate-400 for readable secondary
TEXT_ACTIVE = "#E9D5FF"  # purple-200 for active nav labels
SCRIM_TOP = "transparent"
SCRIM_BOTTOM = "#000000D9"
LOCK_BADGE_BG = "#00000099"
LOCK_BADGE_COLOR = "#F59E0B"  # amber

# --- Spacing ---
SP_4 = 4
SP_8 = 8
SP_12 = 12
SP_16 = 16

# --- Radius ---
RADIUS = 14

# --- Typography ---
TITLE_SIZE = 19
TITLE_WEIGHT = "w700"
SYSTEM_SIZE = 12
SYSTEM_WEIGHT = "w500"
WATERMARK_SIZE = 64
WATERMARK_WEIGHT = "w800"

# --- Chrome ---
NAV_WIDTH = 96
AZ_WIDTH = 24
FILTER_HEIGHT = 48

# --- Tile ---
NOT_PLAYABLE_OPACITY = 0.45
LOCK_BADGE_SIZE = 28
LOCK_ICON_SIZE = 16
TITLE_BAND_HEIGHT = 52

# --- Tile + Detail Hero (LANDSCAPE to match art renders 1.91:1 AND video snaps) ---
# Grid cell aspect (width/height). 1.5 yields a ~16:9 art region once the fixed
# TITLE_BAND_HEIGHT is subtracted, so landscape box-art + snaps cover-fill cleanly.
TILE_ASPECT = 1.5
DETAIL_HERO_W = 480
DETAIL_HERO_H = 270

# --- Motion ---
DURATION_FAST = 150
DURATION_NORMAL = 250
DURATION_SLOW = 400

CURVE_STANDARD = ft.AnimationCurve.EASE_IN_OUT
CURVE_DECELERATE = ft.AnimationCurve.DECELERATE
CURVE_EMPHASIZED = ft.AnimationCurve.EASE_IN_OUT_CUBIC_EMPHASIZED
CURVE_SPRING = ft.AnimationCurve.EASE_OUT_BACK

DURATION_SPRING = 200


def duration(ms: int) -> int:
    """Return ms, or 0 when reduced-motion is requested. Read at CALL TIME (testable)."""
    return 0 if os.environ.get("OPENARCADE_REDUCED_MOTION", "0") == "1" else ms
