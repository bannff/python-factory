"""Pure query functions for Cores & Updates shell screen.

Shared by BOTH the MCP tools and the UI layer. No fastmcp, no flet imports.

Security controls:
- core_name validated against ^[a-z0-9_]+$ AND static KNOWN_CORES allowlist.
- URL built from HARDCODED base + validated name only (caller never supplies a URL).
- HTTPS only, TLS verification ON (stdlib default).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# --- Security control #1: Static KNOWN_CORES allowlist ---
# Subset of real buildbot cores. Extend as needed; NEVER accept arbitrary names.
KNOWN_CORES: frozenset[str] = frozenset({
    # Arcade
    "mame2003_plus", "mame2010", "mame", "fbneo",
    # Nintendo
    "snes9x", "snes9x2002", "snes9x2005", "snes9x2010",
    "nestopia", "fceumm", "quicknes", "bsnes",
    "gambatte", "mgba", "vbam", "gpsp",
    "mupen64plus_next", "parallel_n64",
    "dolphin", "melonds", "desmume",
    # Sega
    "genesis_plus_gx", "picodrive", "flycast", "beetle_saturn",
    # Sony
    "pcsx_rearmed", "pcsx2", "beetle_psx_hw", "beetle_psx",
    "ppsspp",
    # Atari / Other
    "stella", "prosystem", "hatari",
    "mednafen_pce", "mednafen_pce_fast",
    "mednafen_ngp", "mednafen_wswan",
    # Misc
    "scummvm", "dosbox_pure", "vice_x64",
})

# Valid core name: lowercase alphanumeric + underscore only.
_CORE_NAME_RE = re.compile(r"^[a-z0-9_]+$")

# Buildbot base URL — HARDCODED, HTTPS only.
_BUILDBOT_BASE = "https://buildbot.libretro.com/nightly"

# Platform/arch -> buildbot path segment + library extension
_PLATFORM_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("darwin", "arm64"): ("apple/osx/arm64", "dylib"),
    ("darwin", "x86_64"): ("apple/osx/x86_64", "dylib"),
    ("linux", "x86_64"): ("linux/x86_64", "so"),
    ("linux", "aarch64"): ("linux/aarch64", "so"),
    ("win32", "x86_64"): ("windows/x86_64", "dll"),
}


class CoreValidationError(Exception):
    """Raised when a core name fails validation."""


@dataclass(frozen=True)
class InstalledCore:
    """Metadata for a core installed on disk."""
    filename: str
    display_name: str
    system_name: str
    supported_extensions: list[str]
    size_bytes: int


def validate_core_name(name: str) -> str:
    """Validate core_name against charset + allowlist. Returns cleaned name or raises.

    Security control #1: rejects BEFORE any URL build or IO.
    Rejects: '.', '/', '\\', '..', spaces, encodings, null bytes, unknown cores.
    """
    if not name or not isinstance(name, str):
        raise CoreValidationError("core_name must be a non-empty string")
    if "\x00" in name:
        raise CoreValidationError("core_name contains null byte")
    if not _CORE_NAME_RE.match(name):
        raise CoreValidationError(
            f"core_name '{name}' contains invalid characters; "
            "only lowercase a-z, digits, underscore allowed"
        )
    if name not in KNOWN_CORES:
        raise CoreValidationError(
            f"core_name '{name}' is not in the known cores allowlist"
        )
    return name


def build_download_url(core_name: str, platform: str, arch: str) -> str:
    """Build the download URL for a core from HARDCODED base + validated name.

    Security control #2: URL pinning. Caller NEVER passes a URL.
    HTTPS only. No HTTP fallback.

    Args:
        core_name: Already-validated core name (lowercase, in allowlist).
        platform: sys.platform value (e.g. 'darwin', 'linux', 'win32').
        arch: platform.machine() value (e.g. 'arm64', 'x86_64').

    Raises:
        CoreValidationError: if platform/arch combo is unsupported.
    """
    # Re-validate defensively (belt + suspenders)
    validate_core_name(core_name)

    key = (platform, arch)
    if key not in _PLATFORM_MAP:
        raise CoreValidationError(
            f"Unsupported platform/arch: {platform}/{arch}. "
            f"Supported: {sorted(_PLATFORM_MAP.keys())}"
        )
    path_segment, ext = _PLATFORM_MAP[key]
    # URL: base/platform_path/latest/<core>_libretro.<ext>.zip
    return f"{_BUILDBOT_BASE}/{path_segment}/latest/{core_name}_libretro.{ext}.zip"


def get_library_extension(platform: str, arch: str) -> str:
    """Get the library file extension for this platform (dylib/so/dll)."""
    key = (platform, arch)
    if key not in _PLATFORM_MAP:
        raise CoreValidationError(f"Unsupported platform/arch: {platform}/{arch}")
    return _PLATFORM_MAP[key][1]


def list_installed_cores(cores_dir: Path) -> list[InstalledCore]:
    """Scan cores_dir for installed cores (*_libretro.<ext>).

    Parses matching .info files for display_name/systemname/supported_extensions.
    Falls back to filename-derived metadata when no .info present.
    """
    if not cores_dir.is_dir():
        return []

    results: list[InstalledCore] = []
    # Match *_libretro.{dylib,so,dll}
    for f in sorted(cores_dir.iterdir()):
        if not f.is_file():
            continue
        stem = f.stem  # e.g. snes9x_libretro
        if not stem.endswith("_libretro"):
            continue
        if f.suffix not in (".dylib", ".so", ".dll"):
            continue

        core_short = stem.removesuffix("_libretro")
        size = f.stat().st_size

        # Try parsing .info file
        info_path = cores_dir / f"{stem}.info"
        display_name = core_short
        system_name = ""
        extensions: list[str] = []

        if info_path.is_file():
            info = _parse_info_file(info_path)
            display_name = info.get("display_name", core_short)
            system_name = info.get("systemname", "")
            ext_str = info.get("supported_extensions", "")
            if ext_str:
                extensions = [e.strip() for e in ext_str.split("|") if e.strip()]

        results.append(InstalledCore(
            filename=f.name,
            display_name=display_name,
            system_name=system_name,
            supported_extensions=extensions,
            size_bytes=size,
        ))

    return results


def _parse_info_file(path: Path) -> dict[str, str]:
    """Parse a RetroArch .info file (key = "value" format, one per line)."""
    result: dict[str, str] = {}
    try:
        for line in path.read_text(errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"')
                result[key] = value
    except OSError:
        pass
    return result
