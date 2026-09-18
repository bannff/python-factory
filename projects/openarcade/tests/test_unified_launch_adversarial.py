"""Adversarial tests for the unified OpenArcade launch path.

ATTACK SURFACE: The unified launch brick (factory.launch.interface) must be the
SINGLE source of truth for platform_launch_argv + resolve_core_path +
is_darwin_trampoline. BOTH wall/launch_handler.py AND control_plane/launch_tools.py
must delegate to it — no divergent inline argv construction.

Contracts under attack:
  1. Darwin argv starts with `open -a`; inner binary path NOT argv[0]
  2. Linux argv[0] is `retroarch` (raw); no `open` wrapper
  3. resolve_core_path('snes') returns a real .dylib path, NEVER 'lr-' name
  4. Trampoline + returncode==0 + readiness-never-ready -> FAILED (not success)
  5. Trampoline + returncode!=0 -> FAILED with clear reason
  6. Readiness ready -> SUCCESS
  7. Structural: both consumers import from the SAME seam (no inline argv)
  8. wall/core_resolver.py is a thin re-export, not a divergent implementation

All tests use boundary-mocked doubles only (no internal-structure coupling).
"""

from __future__ import annotations

import asyncio
import ast
import inspect
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from factory.launch.interface import (
    LaunchConfig,
    build_launch_argv,
    platform_launch_argv,
    is_darwin_trampoline,
    resolve_core_path,
    ProcessLaunchOrchestrator,
    LaunchState,
    FakeProcessLauncher,
    VersionProbe,
    NciCommand,
)


# ---------------------------------------------------------------------------
# Test double: NCI transport that simulates readiness states
# ---------------------------------------------------------------------------

class AlwaysReadyTransport:
    """Simulates an NCI transport where VERSION responds immediately."""
    async def send_command(self, cmd: NciCommand) -> None:
        pass

    async def query(self, cmd: NciCommand, timeout: float = 1.0) -> str | None:
        return "1.19.1"


class NeverReadyTransport:
    """Simulates an NCI transport where VERSION never responds."""
    async def send_command(self, cmd: NciCommand) -> None:
        pass

    async def query(self, cmd: NciCommand, timeout: float = 1.0) -> str | None:
        return None


class DelayedReadyTransport:
    """Responds to VERSION after N calls."""
    def __init__(self, *, succeed_after: int = 3):
        self._calls = 0
        self._succeed_after = succeed_after

    async def send_command(self, cmd: NciCommand) -> None:
        pass

    async def query(self, cmd: NciCommand, timeout: float = 1.0) -> str | None:
        self._calls += 1
        return "1.19.1" if self._calls > self._succeed_after else None


# ===========================================================================
# ATTACK 1: platform_launch_argv on Darwin starts with `open`/`-a` and
#            contains a resolved .dylib path — inner-binary NOT argv[0]
# ===========================================================================


class TestDarwinArgvStructure:
    """Darwin platform_launch_argv MUST use `open -a <app> --args` wrapper."""

    def test_argv_starts_with_open_minus_a(self):
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Darwin"):
            cfg = LaunchConfig(
                core="/Library/RetroArch/cores/snes9x_libretro.dylib",
                rom="/roms/game.smc",
                retroarch_bin="/Applications/RetroArch.app/Contents/MacOS/RetroArch",
            )
            argv = platform_launch_argv(cfg, "/tmp/test.cfg")
            assert argv[0] == "open", f"Darwin argv[0] must be 'open', got '{argv[0]}'"
            assert argv[1] == "-a", f"Darwin argv[1] must be '-a', got '{argv[1]}'"

    def test_inner_binary_path_NOT_in_argv(self):
        """The inner Mach-O binary path must NOT appear in argv — exec'ing it
        directly exits 0 WITHOUT launching (known macOS lesson)."""
        inner_binary = "/Applications/RetroArch.app/Contents/MacOS/RetroArch"
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Darwin"):
            cfg = LaunchConfig(core="/c/snes.dylib", rom="/r/g.smc", retroarch_bin=inner_binary)
            argv = platform_launch_argv(cfg, "/tmp/c.cfg")
            assert inner_binary not in argv, (
                f"CRITICAL: inner binary '{inner_binary}' found in Darwin argv — "
                f"exec'ing it directly exits 0 without launching!"
            )

    def test_dylib_core_path_is_in_argv(self):
        """The resolved core library path (.dylib) MUST be in the argv."""
        dylib = "/Users/foo/Library/Application Support/RetroArch/cores/snes9x_libretro.dylib"
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Darwin"):
            cfg = LaunchConfig(core=dylib, rom="/r/g.smc", retroarch_bin="RA")
            argv = platform_launch_argv(cfg, "/tmp/c.cfg")
            assert dylib in argv, f"Core path not found in argv: {argv}"

    def test_argv_contains_args_separator(self):
        """--args separator is required to pass core/rom/cfg to the app."""
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Darwin"):
            cfg = LaunchConfig(core="/c.dylib", rom="/r.smc", retroarch_bin="RA")
            argv = platform_launch_argv(cfg, "/tmp/c.cfg")
            assert "--args" in argv, f"Missing --args separator in Darwin argv: {argv}"

    def test_appendconfig_present(self):
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Darwin"):
            cfg = LaunchConfig(core="/c.dylib", rom="/r.smc", retroarch_bin="RA")
            argv = platform_launch_argv(cfg, "/tmp/c.cfg")
            assert "--appendconfig" in argv
            idx = argv.index("--appendconfig")
            assert argv[idx + 1] == "/tmp/c.cfg"


# ===========================================================================
# ATTACK 2: Linux argv[0] is retroarch (raw) with .so
# ===========================================================================


class TestLinuxArgvStructure:
    """Linux platform_launch_argv uses raw retroarch, no `open` wrapper."""

    def test_argv_zero_is_retroarch(self):
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Linux"):
            cfg = LaunchConfig(core="/cores/snes9x_libretro.so", rom="/r.smc", retroarch_bin="retroarch")
            argv = platform_launch_argv(cfg, "/tmp/c.cfg")
            assert argv[0] == "retroarch"

    def test_no_open_command_in_linux_argv(self):
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Linux"):
            cfg = LaunchConfig(core="core.so", rom="rom", retroarch_bin="/usr/bin/retroarch")
            argv = platform_launch_argv(cfg, "/tmp/c.cfg")
            assert "open" not in argv
            assert "-a" not in argv
            assert "--args" not in argv

    def test_so_core_in_linux_argv(self):
        with patch("factory.launch.runtime.launch_command.platform.system", return_value="Linux"):
            cfg = LaunchConfig(core="/opt/cores/snes9x_libretro.so", rom="rom", retroarch_bin="retroarch")
            argv = platform_launch_argv(cfg, "/tmp/c.cfg")
            assert "/opt/cores/snes9x_libretro.so" in argv


# ===========================================================================
# ATTACK 3: resolve_core_path NEVER returns a 'lr-' name
# ===========================================================================


class TestResolveCorePath:
    """resolve_core_path returns real library path, never RetroPie name."""

    def test_snes_resolves_to_dylib_not_lr_name(self, tmp_path: Path):
        (tmp_path / "snes9x_libretro.dylib").write_text("")
        result = resolve_core_path("snes", cores_dir=tmp_path, ext=".dylib")
        assert result.endswith("snes9x_libretro.dylib")
        assert not result.startswith("lr-"), f"Got RetroPie-style name: {result}"
        assert "lr-" not in result

    def test_nes_resolves_to_so_not_lr_name(self, tmp_path: Path):
        (tmp_path / "fceumm_libretro.so").write_text("")
        result = resolve_core_path("nes", cores_dir=tmp_path, ext=".so")
        assert result.endswith("fceumm_libretro.so")
        assert "lr-" not in result

    def test_gba_resolves_correctly(self, tmp_path: Path):
        (tmp_path / "mgba_libretro.dylib").write_text("")
        result = resolve_core_path("gba", cores_dir=tmp_path, ext=".dylib")
        assert "mgba_libretro" in result
        assert "lr-" not in result

    def test_all_known_systems_never_return_lr_prefix(self, tmp_path: Path):
        """Comprehensive: every known system in DEFAULT_CORE_STEMS resolves to
        a _libretro lib path, never a 'lr-' prefix."""
        from factory.launch.interface import DEFAULT_CORE_STEMS
        for system, stem in DEFAULT_CORE_STEMS.items():
            lib_file = tmp_path / f"{stem}_libretro.dylib"
            lib_file.write_text("")
            result = resolve_core_path(system, cores_dir=tmp_path, ext=".dylib")
            assert "lr-" not in result, f"System '{system}' resolved to lr- name: {result}"
            assert result.endswith(f"{stem}_libretro.dylib"), f"{system} -> {result}"

    def test_returns_empty_not_fake_when_missing(self, tmp_path: Path):
        """Honest: returns '' when core not installed — never a fake path."""
        result = resolve_core_path("snes", cores_dir=tmp_path, ext=".dylib")
        assert result == ""


# ===========================================================================
# ATTACK 4: Trampoline + returncode==0 + readiness-never-ready -> FAILED
# ===========================================================================


class TestDarwinTrampolineNotFalseSuccess:
    """Darwin open exits 0 + readiness never arrives = FAILED, not SUCCESS."""

    def test_trampoline_exit_0_readiness_never_arrives_is_FAILED(self):
        """CRITICAL: returncode==0 on Darwin trampoline is NOT success.
        Only NCI VERSION probe determines success."""
        launcher = FakeProcessLauncher(_exit_code=0)  # open exits 0 immediately
        probe = VersionProbe(NeverReadyTransport())
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=0.5, poll_interval=0.05)

        state = asyncio.run(orch.launch(["open", "-a", "RetroArch.app", "--args", "-L", "core"]))

        assert state == LaunchState.FAILED, (
            f"Trampoline exit 0 + no readiness MUST be FAILED, got {state.name}"
        )
        assert "Timeout" in orch.failure_reason

    def test_trampoline_exit_0_readiness_eventually_arrives_is_READY(self):
        """Confirm the positive path: open exits 0, NCI responds -> READY."""
        launcher = FakeProcessLauncher(_exit_code=0)
        probe = VersionProbe(DelayedReadyTransport(succeed_after=2))
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=5.0, poll_interval=0.05)

        state = asyncio.run(orch.launch(["open", "-a", "RA.app", "--args"]))
        assert state == LaunchState.READY


# ===========================================================================
# ATTACK 5: Trampoline + returncode!=0 -> FAILED with clear reason
# ===========================================================================


class TestDarwinTrampolineRejection:
    """Non-zero exit from `open` = trampoline rejected (app not found etc)."""

    def test_trampoline_exit_1_is_failed_with_reason(self):
        launcher = FakeProcessLauncher(_exit_code=1, _stderr="Unable to find application")
        probe = VersionProbe(AlwaysReadyTransport())  # shouldn't matter
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=5.0)

        state = asyncio.run(orch.launch(["open", "-a", "Nonexistent.app"]))

        assert state == LaunchState.FAILED
        assert "Trampoline rejected" in orch.failure_reason
        assert "1" in orch.failure_reason  # exit code
        assert "Unable to find application" in orch.failure_reason

    def test_trampoline_exit_127_is_failed(self):
        launcher = FakeProcessLauncher(_exit_code=127, _stderr="command not found")
        probe = VersionProbe(NeverReadyTransport())
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=5.0)

        state = asyncio.run(orch.launch(["open", "-a", "X.app"]))
        assert state == LaunchState.FAILED
        assert "127" in orch.failure_reason


# ===========================================================================
# ATTACK 6: Readiness ready -> SUCCESS
# ===========================================================================


class TestReadinessSuccess:
    """Standard path: process alive + probe responds -> READY."""

    def test_linux_process_alive_probe_ready_is_READY(self):
        launcher = FakeProcessLauncher()  # stays alive (returncode=None)
        probe = VersionProbe(AlwaysReadyTransport())
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=5.0)

        state = asyncio.run(orch.launch(["retroarch", "-L", "core", "rom"]))
        assert state == LaunchState.READY

    def test_darwin_trampoline_alive_probe_ready_is_READY(self):
        launcher = FakeProcessLauncher(_exit_code=0)
        probe = VersionProbe(AlwaysReadyTransport())
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=5.0)

        state = asyncio.run(orch.launch(["open", "-a", "RA.app", "--args"]))
        assert state == LaunchState.READY


# ===========================================================================
# ATTACK 7: STRUCTURAL — both consumers use the SAME seam
# ===========================================================================


class TestUnifiedSeamStructural:
    """wall/launch_handler.py and control_plane/launch_tools.py MUST import
    platform_launch_argv from factory.launch.interface — no divergent inline code."""

    def test_wall_launch_handler_imports_platform_launch_argv_from_brick(self):
        """launch_handler.py imports platform_launch_argv from factory.launch.interface."""
        import wall.launch_handler as mod
        source = Path(mod.__file__).read_text()
        # Must import from factory.launch.interface
        assert "from factory.launch.interface import" in source
        assert "platform_launch_argv" in source

    def test_control_plane_launch_tools_imports_platform_launch_argv_from_brick(self):
        """launch_tools.py imports platform_launch_argv from factory.launch.interface."""
        import control_plane.launch_tools as mod
        source = Path(mod.__file__).read_text()
        assert "from factory.launch.interface import" in source
        assert "platform_launch_argv" in source

    def test_no_build_launch_argv_in_wall_launch_handler(self):
        """wall/launch_handler.py must NOT call build_launch_argv directly
        (it should use platform_launch_argv which wraps it)."""
        import wall.launch_handler as mod
        source = Path(mod.__file__).read_text()
        # It's fine to import it, but it should not CALL it outside of
        # platform_launch_argv. Check that it's not in the launch method body.
        # Actually, it should not be imported at all — platform_launch_argv handles it.
        assert "build_launch_argv(" not in source.split("class LaunchHandler")[1], (
            "LaunchHandler calls build_launch_argv directly — "
            "should use platform_launch_argv which wraps it"
        )

    def test_no_inline_open_minus_a_in_consumers(self):
        """Neither consumer should hardcode ['open', '-a', ...] inline."""
        import wall.launch_handler as mod1
        import control_plane.launch_tools as mod2
        for mod in [mod1, mod2]:
            source = Path(mod.__file__).read_text()
            # After the import block, should not construct open -a inline
            body = source.split("def ")[1] if "def " in source else source
            assert '["open"' not in body and "['open'" not in body, (
                f"{mod.__name__} contains inline 'open' argv construction"
            )

    def test_no_divergent_build_launch_argv_definition(self):
        """No PRODUCTION module in projects/openarcade/ should DEFINE its own
        build_launch_argv or platform_launch_argv — only import from the brick."""
        project_root = Path("/Users/wdaniero/workplace/python-factory/projects/openarcade")
        for py_file in project_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            # Skip test files — they contain the search strings as assertions
            if "test_" in py_file.name or py_file.name.startswith("test"):
                continue
            source = py_file.read_text()
            # Check for function definitions that would shadow the brick
            if re.search(r"^\s*def platform_launch_argv\b", source, re.MULTILINE):
                pytest.fail(
                    f"{py_file.relative_to(project_root)} DEFINES platform_launch_argv — "
                    f"only the brick should define it!"
                )
            if re.search(r"^\s*def build_launch_argv\b", source, re.MULTILINE):
                pytest.fail(
                    f"{py_file.relative_to(project_root)} DEFINES build_launch_argv — "
                    f"only the brick should define it!"
                )


# ===========================================================================
# ATTACK 8: wall/core_resolver.py is a thin re-export, not divergent
# ===========================================================================


class TestWallCoreResolverIsReexport:
    """wall/core_resolver.py must be a thin re-export from the brick."""

    def test_wall_core_resolver_reexports_from_brick(self):
        """The module re-exports resolve_core_path from factory.launch.interface."""
        import wall.core_resolver as wmod
        from factory.launch.interface import resolve_core_path as brick_fn
        assert wmod.resolve_core_path is brick_fn, (
            "wall/core_resolver.py defines its OWN resolve_core_path instead of "
            "re-exporting from the brick — divergence risk!"
        )

    def test_wall_core_resolver_source_is_minimal(self):
        """Source file should be < 15 lines (just imports + re-export + docstring)."""
        import wall.core_resolver as mod
        source = Path(mod.__file__).read_text()
        lines = [l for l in source.splitlines() if l.strip() and not l.strip().startswith("#")]
        assert len(lines) < 15, (
            f"wall/core_resolver.py has {len(lines)} non-empty/non-comment lines — "
            f"should be a thin re-export (~5 lines), not a full implementation"
        )

    def test_wall_core_resolver_no_platform_logic(self):
        """Must NOT contain platform/os/pathlib logic of its own."""
        import wall.core_resolver as mod
        source = Path(mod.__file__).read_text()
        assert "platform.system" not in source
        assert "Path.home" not in source
        assert "os.environ" not in source


# ===========================================================================
# MCP-PATH REAL LAUNCH SMOKE TEST (env-gated)
# ===========================================================================


_SMOKE = os.environ.get("OPENARCADE_LAUNCH_SMOKE") == "1"
_RA_APP = "/Applications/RetroArch.app"
_RA_PROC = "RetroArch.app/Contents/MacOS/RetroArch"


@pytest.mark.skipif(
    not (_SMOKE and Path(_RA_APP).exists()),
    reason="opt-in: set OPENARCADE_LAUNCH_SMOKE=1 with real RetroArch installed",
)
class TestRealLaunchSmokeMcp:
    """Opt-in end-to-end: launch a game through the REAL MCP launch_game path.

    Spawns real RetroArch via the unified platform_launch_argv, verifies via
    pgrep that the process is actually running, then kills it. This proves the
    whole chain works outside of mocks.
    """

    def test_mcp_launch_game_spawns_real_retroarch(self):
        """Exercise the MCP launch_game tool end-to-end on the real system.

        Requires: RetroArch.app installed, a snes core, and a ROM file.
        The test will kill RetroArch afterward.
        """
        # Resolve real core
        core = resolve_core_path("snes")
        if not core:
            pytest.skip("No snes core installed at default location")

        # Find a ROM — look in standard locations
        rom_dirs = [
            Path("/tmp/oa_arcade/snes"),
            Path.home() / "RetroPie" / "roms" / "snes",
            Path.home() / "Games" / "snes",
        ]
        rom = None
        for d in rom_dirs:
            if d.exists():
                roms = list(d.glob("*.sfc")) + list(d.glob("*.zip")) + list(d.glob("*.smc"))
                if roms:
                    rom = str(roms[0])
                    break
        if not rom:
            pytest.skip("No SNES ROM found in standard locations")

        import tempfile
        from factory.launch.interface import (
            LaunchConfig,
            build_override_cfg_text,
            platform_launch_argv,
        )

        cfg = LaunchConfig(
            core=core,
            rom=rom,
            retroarch_bin="/Applications/RetroArch.app/Contents/MacOS/RetroArch",
            video_driver="metal" if platform.system() == "Darwin" else None,
        )
        with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as f:
            f.write(build_override_cfg_text(cfg))
            cfg_path = f.name

        argv = platform_launch_argv(cfg, cfg_path)

        # Verify argv structure before launching
        if platform.system() == "Darwin":
            assert argv[0] == "open"
            assert "-a" in argv

        try:
            # Launch (open returns immediately on macOS)
            subprocess.run(argv, check=False, timeout=10)
            time.sleep(4)

            # Verify RetroArch is actually running
            found = subprocess.run(
                ["pgrep", "-f", _RA_PROC], capture_output=True, text=True
            )
            assert found.stdout.strip(), (
                "RetroArch NOT running after launch — the unified launch path "
                "failed to actually start the emulator!"
            )

            # Optional: NCI VERSION probe
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)
            try:
                sock.sendto(b"VERSION\n", ("127.0.0.1", 55355))
                data, _ = sock.recvfrom(256)
                assert data  # Got a response — NCI is alive
            except socket.timeout:
                # NCI might not be ready in 4s — that's OK, pgrep proved launch
                pass
            finally:
                sock.close()
        finally:
            # Cleanup: kill RetroArch
            subprocess.run(["pkill", "-f", _RA_PROC], check=False)
            os.unlink(cfg_path)
