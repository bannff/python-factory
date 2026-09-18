"""Launch handler — async RetroArch launch sequence.

Extracted from navigator.py (bead pacz8). Owns temp override cfg, transport+probe
assembly, and orchestration. Platform argv logic now lives in the launch brick
(factory.launch.interface.platform_launch_argv).
"""

from __future__ import annotations

import platform
import tempfile

import flet as ft

from .launch_intent import launch_args
from .core_resolver import resolve_core_path
from .models import GameTile
from factory.launch.interface import (
    LaunchConfig,
    build_override_cfg_text,
    platform_launch_argv,
    ProcessLaunchOrchestrator,
    AsyncProcessLauncher,
    VersionProbe,
    UdpNciTransport,
)


class LaunchHandler:
    """Encapsulates the async game-launch sequence.

    Injectable/testable — receives a core-resolver callable and page ref.
    """

    def __init__(
        self,
        *,
        resolve_core: "callable[[GameTile], str]",
        page: ft.Page | None = None,
    ) -> None:
        self._resolve_core = resolve_core
        self._page = page

    async def launch(self, game: GameTile) -> None:
        """Launch game via RetroArch subprocess + NCI VERSION readiness polling."""
        # Transient feedback: launching
        if self._page:
            self._page.snack_bar = ft.SnackBar(
                content=ft.Text(f"Launching {game.title}..."),
                open=True,
                duration=3000,
            )
            self._page.update()

        content_path, core_hint = launch_args(game)
        # Prefer a REAL local core library path (loadable by `-L`) over a
        # RetroPie-style name/hint. On the Linux cabinet resolve_core_path may
        # return "" (different core layout) and we fall back to the hint / the
        # injected emulators.cfg resolver.
        core = (
            resolve_core_path(game.system)
            or core_hint
            or self._resolve_core(game)
        )
        if not core:
            if self._page:
                self._page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"Cannot resolve core for {game.title}"),
                    open=True,
                    duration=4000,
                )
                self._page.update()
            return

        # Platform detection at composition root only
        video_driver: str | None = None
        if platform.system() == "Darwin":
            video_driver = "metal"
            retroarch_bin = "/Applications/RetroArch.app/Contents/MacOS/RetroArch"
        else:
            retroarch_bin = "retroarch"

        cfg = LaunchConfig(
            core=core,
            rom=content_path,
            retroarch_bin=retroarch_bin,
            video_driver=video_driver,
        )

        # Write override cfg to temp file
        cfg_text = build_override_cfg_text(cfg)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".cfg", prefix="oa_launch_", delete=False
        )
        tmp.write(cfg_text)
        tmp.close()

        # Unified platform argv (open -a on macOS, raw retroarch on Linux)
        argv = platform_launch_argv(cfg, tmp.name)

        # Assemble real transport + probe + launcher
        transport = UdpNciTransport(port=cfg.port)
        probe = VersionProbe(transport)
        launcher = AsyncProcessLauncher()
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=10.0)

        try:
            await orch.launch(argv)
        except Exception as exc:
            if self._page:
                self._page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"Launch failed: {exc}"),
                    open=True,
                    duration=5000,
                )
                self._page.update()
