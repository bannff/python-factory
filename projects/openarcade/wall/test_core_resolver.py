"""Tests for core-library-path resolution + an opt-in REAL launch smoke test.

The unit tests are hermetic (fake cores dir, explicit ext — no real FS/platform
dependence). The smoke test actually spawns RetroArch and is SKIPPED unless
OPENARCADE_LAUNCH_SMOKE=1 — it's the honest end-to-end check that mocked suites
cannot provide.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from wall.core_resolver import resolve_core_path


# --- Unit: hermetic core-path resolution ---

def test_resolves_installed_core_path(tmp_path: Path):
    (tmp_path / "snes9x_libretro.dylib").write_text("")  # fake installed core
    got = resolve_core_path("snes", cores_dir=tmp_path, ext=".dylib")
    assert got == str(tmp_path / "snes9x_libretro.dylib")


def test_returns_empty_when_core_file_missing(tmp_path: Path):
    # mapped system, but no library file present -> honest "" (not a fake path)
    assert resolve_core_path("snes", cores_dir=tmp_path, ext=".dylib") == ""


def test_unknown_system_returns_empty(tmp_path: Path):
    assert resolve_core_path("dreamcast", cores_dir=tmp_path, ext=".dylib") == ""


def test_empty_system_returns_empty(tmp_path: Path):
    assert resolve_core_path("", cores_dir=tmp_path, ext=".dylib") == ""


def test_env_override_cores_dir(tmp_path: Path, monkeypatch):
    (tmp_path / "snes9x_libretro.so").write_text("")
    monkeypatch.setenv("OPENARCADE_CORES_DIR", str(tmp_path))
    # ext still explicit to stay platform-independent
    assert resolve_core_path("snes", ext=".so") == str(tmp_path / "snes9x_libretro.so")


# --- Hermetic: platform argv wrapper ---

def test_platform_launch_argv_wraps_open_on_mac(monkeypatch):
    from wall import launch_handler as LH
    from factory.launch.interface import LaunchConfig
    monkeypatch.setattr(LH.platform, "system", lambda: "Darwin")
    cfg = LaunchConfig(core="/c/snes9x_libretro.dylib", rom="/r/mk.zip", retroarch_bin="/App/RA")
    argv = LH.platform_launch_argv(cfg, "/tmp/c.cfg")
    assert argv[:4] == ["open", "-a", "/Applications/RetroArch.app", "--args"]
    assert "-L" in argv and "/c/snes9x_libretro.dylib" in argv and "/r/mk.zip" in argv


def test_platform_launch_argv_direct_on_linux(monkeypatch):
    from wall import launch_handler as LH
    from factory.launch.interface import LaunchConfig
    monkeypatch.setattr(LH.platform, "system", lambda: "Linux")
    cfg = LaunchConfig(core="snes9x.so", rom="/r/mk.zip", retroarch_bin="retroarch")
    argv = LH.platform_launch_argv(cfg, "/tmp/c.cfg")
    assert argv[0] == "retroarch" and "open" not in argv


# --- Opt-in REAL launch smoke test (no mocks) ---

_SMOKE = os.environ.get("OPENARCADE_LAUNCH_SMOKE") == "1"
_RA = "/Applications/RetroArch.app/Contents/MacOS/RetroArch"
_CORE = resolve_core_path("snes")
_ROM = "/tmp/oa_arcade/snes/Mortal Kombat (USA).zip"
_RA_PROC = "RetroArch.app/Contents/MacOS/RetroArch"


@pytest.mark.skipif(
    not (_SMOKE and Path(_RA).exists() and _CORE and Path(_ROM).exists()),
    reason="opt-in: set OPENARCADE_LAUNCH_SMOKE=1 with real RetroArch+core+rom",
)
def test_real_retroarch_launch_smoke():
    """Launch RetroArch through OpenArcade's REAL argv builder (platform_launch_argv)
    with the resolved core + a real ROM, confirm a RetroArch process is actually
    running, then terminate it. Proves the launch path end-to-end against the real
    emulator — the check mocked tests can't make. On macOS the launcher is `open`
    (returns immediately), so readiness = a live RetroArch process, not the wrapper."""
    from wall.launch_handler import platform_launch_argv
    from factory.launch.interface import LaunchConfig, build_override_cfg_text
    import tempfile

    cfg = LaunchConfig(core=_CORE, rom=_ROM, retroarch_bin=_RA, video_driver="metal")
    with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
        f.write(build_override_cfg_text(cfg))
        cfg_path = f.name
    argv = platform_launch_argv(cfg, cfg_path)

    subprocess.run(argv, check=False)  # `open` returns immediately after handoff
    try:
        time.sleep(5)
        found = subprocess.run(["pgrep", "-f", _RA_PROC], capture_output=True, text=True)
        assert found.stdout.strip(), "no RetroArch process running after launch"
    finally:
        subprocess.run(["pkill", "-f", _RA_PROC], check=False)
        os.unlink(cfg_path)
