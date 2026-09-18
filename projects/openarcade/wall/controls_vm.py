"""Pure view-model mapper for the Controls tab. Zero Flet imports."""

from __future__ import annotations

from dataclasses import dataclass

from factory.arcade_config.runtime.settings import RetroArchRuntimeSettings


@dataclass(frozen=True)
class ControlsVM:
    """Presentation-ready state for the Controls tab.

    Fields reflect REAL RetroArch runtime state. None remap_rows = default layout.
    """

    runahead_enabled: bool
    runahead_frames: int
    shader_enabled: bool
    shader_name: str
    video_smooth: bool
    core: str
    remap_rows: tuple[tuple[str, str], ...] | None  # None = default layout


def controls_from_settings(
    settings: RetroArchRuntimeSettings,
    *,
    remaps: tuple[tuple[str, str], ...] | None = None,
) -> ControlsVM:
    """Build a ControlsVM from resolved runtime settings.

    Parameters
    ----------
    settings : RetroArchRuntimeSettings
        Resolved from layered configs.
    remaps : tuple of (button, target) pairs, or None
        If None, renders "Default RetroPad layout". If provided, renders remap grid.
    """
    return ControlsVM(
        runahead_enabled=settings.run_ahead_enabled,
        runahead_frames=settings.run_ahead_frames,
        shader_enabled=settings.shader_enabled,
        shader_name=settings.shader_name,
        video_smooth=settings.video_smooth,
        core=settings.core,
        remap_rows=remaps,
    )
