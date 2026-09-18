"""OpenArcade MCP Control Plane server — thin orchestrator.

Entry point: build_server() returns a FastMCP instance.
Each capability lives in its own module (library_tools, launch_tools,
settings_tools, systems_tools) — all sharing a frozen ServerContext.

Run standalone via `python -m control_plane.server` (reads env vars).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from factory.mcp_utils.runtime.tool_catalog import ToolCatalog

from wall.gamelist_source import load_gamelist
from factory.launch.interface import NciTransport, ProcessLauncher

from .context import ServerContext
from . import library_tools, launch_tools, settings_tools, systems_tools, controllers_tools, library_manager_tools, information_tools, cores_tools, assistant_tools, curation_tools, knowledge_tools


def build_server(
    *,
    gamelist_path: Path,
    system: str,
    media_root: Path,
    roms_root: Path | None = None,
    launcher: ProcessLauncher | None = None,
    transport_factory: "Callable[[int], NciTransport] | None" = None,
) -> ToolCatalog:
    """Build the OpenArcade MCP server.

    Loads the game library once at startup (cheap, ~786 tiles for SNES).

    Injectable overrides (default to real implementations):
      launcher: ProcessLauncher for subprocess exec (default: AsyncProcessLauncher)
      transport_factory: (port) -> NciTransport for NCI readiness (default: UdpNciTransport)
    """
    effective_roms_root = roms_root if roms_root else media_root / system.lower()
    tiles = load_gamelist(
        gamelist_path, system=system, media_root=media_root,
        roms_root=effective_roms_root, require_media=False,
    )

    ctx = ServerContext(
        tiles=tiles,
        system=system,
        media_root=media_root,
        roms_root=effective_roms_root,
        launcher=launcher,
        transport_factory=transport_factory,
    )

    mcp = ToolCatalog("openarcade")

    # Register per-capability modules
    library_tools.register(mcp, context=ctx)
    launch_tools.register(mcp, context=ctx)
    settings_tools.register(mcp, context=ctx)
    systems_tools.register(mcp, context=ctx)
    controllers_tools.register(mcp, context=ctx)
    library_manager_tools.register(mcp, context=ctx)
    information_tools.register(mcp, context=ctx)
    cores_tools.register(mcp, context=ctx)
    assistant_tools.register(mcp, context=ctx)
    curation_tools.register(mcp, context=ctx)
    knowledge_tools.register(mcp, context=ctx)

    return mcp


# --- Standalone stdio entry ---

if __name__ == "__main__":
    import os

    gamelist = Path(os.environ.get("OPENARCADE_GAMELIST", ""))
    media = Path(os.environ.get("OPENARCADE_MEDIA_ROOT", ""))
    sys_name = os.environ.get("OPENARCADE_SYSTEM", "snes")

    if not gamelist.exists():
        raise SystemExit(f"OPENARCADE_GAMELIST not found: {gamelist}")
    if not media.exists():
        raise SystemExit(f"OPENARCADE_MEDIA_ROOT not found: {media}")

    server = build_server(gamelist_path=gamelist, system=sys_name, media_root=media)
    server.run()
