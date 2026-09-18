"""Shared server context — frozen dataclass carrying deps for all tool modules."""

from __future__ import annotations

import platform as _platform_mod
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from factory.launch.interface import NciTransport, ProcessLauncher

from wall.models import GameTile

if TYPE_CHECKING:
    from .downloader import CoreDownloader


def _detect_platform() -> str:
    """Auto-detect platform for buildbot URL (sys.platform)."""
    return sys.platform


def _detect_arch() -> str:
    """Auto-detect arch for buildbot URL (platform.machine())."""
    m = _platform_mod.machine()
    # Normalize arm64 -> arm64 (macOS reports arm64)
    # x86_64/AMD64 -> x86_64
    if m.lower() in ("amd64", "x86_64"):
        return "x86_64"
    return m.lower()


@dataclass(frozen=True)
class ServerContext:
    """Immutable context shared by all per-capability tool modules.

    Constructed once in build_server() and passed to each module's register().
    """

    tiles: list[GameTile]
    system: str
    media_root: Path
    roms_root: Path
    launcher: "ProcessLauncher | None"
    transport_factory: "Callable[[int], NciTransport] | None"

    # Cores & Updates
    cores_dir: Path | None = None
    platform: str = field(default_factory=_detect_platform)
    arch: str = field(default_factory=_detect_arch)
    core_downloader: "CoreDownloader | None" = None
