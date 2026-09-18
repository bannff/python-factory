"""Cores & Updates tools — list_cores, install_core.

register() wires onto the passed FastMCP instance (cerv6 pattern).
Pure core shared by UI + assistant; no UI/Flet imports.
"""

from __future__ import annotations

from typing import Any

from .context import ServerContext
from .cores_query import (
    CoreValidationError,
    InstalledCore,
    list_installed_cores,
    validate_core_name,
)
from .downloader import CoreDownloader, DownloadError, install_core


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register cores tools (list_cores, install_core)."""

    @mcp.tool()
    def list_cores() -> list[dict[str, Any]]:
        """List installed RetroArch cores with metadata.

        Scans cores_dir for *_libretro.{dylib,so,dll} files and parses
        matching .info files for display_name, systemname, extensions.
        Falls back to filename when no .info present.
        """
        if context.cores_dir is None:
            return []
        cores = list_installed_cores(context.cores_dir)
        return [
            {
                "filename": c.filename,
                "display_name": c.display_name,
                "system_name": c.system_name,
                "supported_extensions": c.supported_extensions,
                "size_bytes": c.size_bytes,
            }
            for c in cores
        ]

    @mcp.tool()
    def install_core_tool(core_name: str) -> dict[str, Any]:
        """Install a RetroArch core by name from the official buildbot.

        Downloads the core zip for the current platform, validates integrity,
        and installs to the cores directory. Requires cores_dir and
        core_downloader to be configured.

        Args:
            core_name: Core identifier (e.g. 'snes9x', 'mupen64plus_next').
                       Must be in the known cores allowlist.
        """
        if context.cores_dir is None:
            return {"error": "Cores directory not configured"}
        if context.core_downloader is None:
            return {"error": "Core installation is disabled (read-only mode)"}

        try:
            validate_core_name(core_name)
        except CoreValidationError as e:
            return {"error": str(e)}

        try:
            installed_path = install_core(
                core_name,
                platform=context.platform,
                arch=context.arch,
                cores_dir=context.cores_dir,
                downloader=context.core_downloader,
            )
        except CoreValidationError as e:
            return {"error": str(e)}
        except DownloadError as e:
            return {"error": str(e)}

        return {
            "core_name": core_name,
            "installed": True,
            "path": str(installed_path),
        }
