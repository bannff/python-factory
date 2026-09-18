"""Pure view-model for the Global Settings screen (Video / Audio / Latency).

Zero Flet imports. Maps resolved global cfg values + hardcoded defaults
to presentation-ready rows. Same pattern as core_options_vm.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingsRow:
    """A single settings row -- dropdown or toggle."""

    key: str
    label: str
    current: str
    choices: tuple[str, ...]
    is_toggle: bool  # True = render as toggle, False = dropdown


@dataclass(frozen=True)
class SettingsSection:
    """A labeled group of settings rows."""

    title: str
    rows: tuple[SettingsRow, ...]


@dataclass(frozen=True)
class GlobalSettingsVM:
    """Complete view-model for the Global Settings screen."""

    video: SettingsSection
    audio: SettingsSection
    latency: SettingsSection


# --- Defaults (meta-architect approved) ---

VIDEO_ASPECT_RATIO_CHOICES = ("Auto", "4:3", "16:9", "Core Provided", "1:1 PAR")
VIDEO_ASPECT_RATIO_KEY = "aspect_ratio_index"
# RetroArch stores aspect_ratio_index as an integer index:
#   0=4:3, 1=16:9, 2=Auto, ... but also accepts named string since RA 1.9+.
# We use the *string* form via video_aspect_ratio cfg key for clarity.
# Mapping: "Auto" -> "", "4:3" -> "4:3", etc.  RA accepts these as video_aspect_ratio values.
VIDEO_ASPECT_RATIO_CFG_KEY = "video_aspect_ratio"

AUDIO_VOLUME_CHOICES = ("-10", "-5", "-3", "0", "3", "5", "10")
AUDIO_LATENCY_CHOICES = ("32", "64", "128", "256")
RUN_AHEAD_FRAMES_CHOICES = ("0", "1", "2", "3", "4", "5", "6")
VIDEO_FRAME_DELAY_CHOICES = tuple(str(i) for i in range(16))  # "0".."15"


def _bool_str(raw: str, default: bool = False) -> str:
    """Normalize a raw cfg bool string to "true"/"false"."""
    if not raw:
        return "true" if default else "false"
    return "true" if raw.strip().lower() == "true" else "false"


def _clamp_choice(raw: str, choices: tuple[str, ...], default: str) -> str:
    """Return raw if it's in choices, else default."""
    return raw if raw in choices else default


def build_global_settings_vm(global_cfg: dict[str, str]) -> GlobalSettingsVM:
    """Build the VM from a parsed global override cfg dict.

    All rows render even with no override (render-all-at-default pattern).
    """
    # --- VIDEO ---
    aspect_raw = global_cfg.get(VIDEO_ASPECT_RATIO_CFG_KEY, "")
    # Map empty / missing -> "Auto"
    if not aspect_raw or aspect_raw.strip() == "":
        aspect_current = "Auto"
    else:
        aspect_current = _clamp_choice(aspect_raw.strip(), VIDEO_ASPECT_RATIO_CHOICES, "Auto")

    video_rows = (
        SettingsRow(
            key=VIDEO_ASPECT_RATIO_CFG_KEY,
            label="Aspect Ratio",
            current=aspect_current,
            choices=VIDEO_ASPECT_RATIO_CHOICES,
            is_toggle=False,
        ),
        SettingsRow(
            key="video_scale_integer",
            label="Integer Scaling",
            current=_bool_str(global_cfg.get("video_scale_integer", ""), default=False),
            choices=("true", "false"),
            is_toggle=True,
        ),
        SettingsRow(
            key="video_vsync",
            label="VSync",
            current=_bool_str(global_cfg.get("video_vsync", ""), default=True),
            choices=("true", "false"),
            is_toggle=True,
        ),
        SettingsRow(
            key="video_smooth",
            label="Bilinear Filtering",
            current=_bool_str(global_cfg.get("video_smooth", ""), default=False),
            choices=("true", "false"),
            is_toggle=True,
        ),
    )

    # --- AUDIO ---
    audio_rows = (
        SettingsRow(
            key="audio_mute_enable",
            label="Mute Audio",
            current=_bool_str(global_cfg.get("audio_mute_enable", ""), default=False),
            choices=("true", "false"),
            is_toggle=True,
        ),
        SettingsRow(
            key="audio_volume",
            label="Volume (dB)",
            current=_clamp_choice(
                global_cfg.get("audio_volume", "").replace(".000000", "").replace(".0", ""),
                AUDIO_VOLUME_CHOICES,
                "0",
            ),
            choices=AUDIO_VOLUME_CHOICES,
            is_toggle=False,
        ),
        SettingsRow(
            key="audio_latency",
            label="Audio Latency (ms)",
            current=_clamp_choice(global_cfg.get("audio_latency", ""), AUDIO_LATENCY_CHOICES, "64"),
            choices=AUDIO_LATENCY_CHOICES,
            is_toggle=False,
        ),
    )

    # --- LATENCY ---
    latency_rows = (
        SettingsRow(
            key="run_ahead_frames",
            label="Run-Ahead Frames",
            current=_clamp_choice(global_cfg.get("run_ahead_frames", ""), RUN_AHEAD_FRAMES_CHOICES, "0"),
            choices=RUN_AHEAD_FRAMES_CHOICES,
            is_toggle=False,
        ),
        SettingsRow(
            key="video_frame_delay",
            label="Frame Delay",
            current=_clamp_choice(global_cfg.get("video_frame_delay", ""), VIDEO_FRAME_DELAY_CHOICES, "0"),
            choices=VIDEO_FRAME_DELAY_CHOICES,
            is_toggle=False,
        ),
    )

    return GlobalSettingsVM(
        video=SettingsSection(title="Video", rows=video_rows),
        audio=SettingsSection(title="Audio", rows=audio_rows),
        latency=SettingsSection(title="Latency", rows=latency_rows),
    )
