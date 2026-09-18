"""Launch tools — start a game via RetroArch subprocess + NCI readiness.

register() wires launch_game onto the passed FastMCP instance.

Uses the unified launch brick (factory.launch.interface) for:
  - resolve_core_path: real dylib/.so resolution (not RetroPie names)
  - platform_launch_argv: macOS `open -a` wrapper (not inner binary exec)
  - ProcessLaunchOrchestrator: Darwin readiness-over-liveness
"""

from __future__ import annotations

import platform
import tempfile
import time
from typing import Any

from wall.library_query import get_game as _get_game
from wall.launch_intent import launch_args
from factory.launch.interface import (
    LaunchConfig,
    build_override_cfg_text,
    platform_launch_argv,
    resolve_core_path,
    ProcessLaunchOrchestrator,
    AsyncProcessLauncher,
    VersionProbe,
    LaunchState,
    UdpNciTransport,
)

from .context import ServerContext
from .settings_query import resolve_core as resolve_core_from_cfg


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register launch_game tool."""
    tiles = context.tiles
    system = context.system
    media_root = context.media_root
    launcher = context.launcher
    transport_factory = context.transport_factory

    @mcp.tool()
    async def launch_game(game_id: str) -> dict[str, Any]:
        """Launch a game by id via RetroArch subprocess + NCI VERSION readiness.

        Resolves core+rom from library, builds LaunchConfig with platform-appropriate
        video_driver, execs RetroArch via unified platform_launch_argv, polls VERSION
        until ready or timeout. Returns launch state + elapsed seconds.
        """
        tile = _get_game(tiles, game_id)
        if tile is None:
            return {"state": "FAILED", "reason": f"Game not found: {game_id}"}

        content_path, core_hint = launch_args(tile)

        # Unified core resolution: prefer real dylib path, fall back to
        # emulators.cfg (Linux cabinet with RetroPie-style layout).
        core = (
            resolve_core_path(tile.system)
            or core_hint
            or resolve_core_from_cfg(system, media_root)
        )
        if not core:
            return {"state": "FAILED", "reason": "Cannot resolve core for game"}

        # Platform-appropriate video driver
        video_driver: str | None = None
        if platform.system() == "Darwin":
            video_driver = "metal"

        # RetroArch binary path
        if platform.system() == "Darwin":
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

        # Assemble orchestrator — real impls unless overridden for testing
        _transport_factory = transport_factory or (lambda port: UdpNciTransport(port=port))
        _launcher = launcher or AsyncProcessLauncher()

        transport = _transport_factory(cfg.port)
        probe = VersionProbe(transport)
        orch = ProcessLaunchOrchestrator(_launcher, probe, timeout=10.0)

        t0 = time.monotonic()
        state = await orch.launch(argv)
        elapsed = round(time.monotonic() - t0, 2)

        result: dict[str, Any] = {
            "state": state.name,
            "elapsed_seconds": elapsed,
            "game_id": game_id,
            "core": core,
        }
        if state == LaunchState.FAILED:
            result["reason"] = orch.failure_reason
        return result
