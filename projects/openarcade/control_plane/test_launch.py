"""Behavior tests for launch_game MCP tool — highest-risk path.

Contracts:
  - argv construction from LaunchConfig is correct
  - readiness success via VERSION round-trip
  - readiness timeout/failure within budget (no hang)
  - MCP launch_game tool surfaces success/failure via injectable fakes
  - no MockNciTransport hardcoded in product path

Test doubles: FakeProcessLauncher (records argv, configurable exit) +
FakeNciTransport (NciTransport protocol, configurable VERSION reply).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from factory.launch.interface import (
    LaunchConfig,
    build_launch_argv,
    build_override_cfg_text,
    ProcessLaunchOrchestrator,
    VersionProbe,
    LaunchState,
    NciCommand,
    NciTransport,
    FakeProcessLauncher,
)

from control_plane.server import build_server


# ---------------------------------------------------------------------------
# Test double: FakeNciTransport implementing NciTransport protocol
# ---------------------------------------------------------------------------


class FakeNciTransport:
    """Fake NCI transport — returns canned VERSION or times out (None).

    Implements the NciTransport protocol at the boundary.
    """

    def __init__(self, *, version_reply: str | None = "1.19.1") -> None:
        self._version_reply = version_reply
        self.queries: list[str] = []

    async def send_command(self, cmd: NciCommand) -> None:
        pass

    async def query(self, cmd: NciCommand, timeout: float = 1.0) -> str | None:
        self.queries.append(cmd.name)
        return self._version_reply


class TimeoutNciTransport:
    """Fake NCI transport that always returns None (simulates unreachable RetroArch)."""

    async def send_command(self, cmd: NciCommand) -> None:
        pass

    async def query(self, cmd: NciCommand, timeout: float = 1.0) -> str | None:
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_gamelist(tmp_path: Path) -> tuple[Path, Path]:
    """Create minimal gamelist + emulators.cfg + ROM file. Returns (gamelist_path, media_root)."""
    gamelist = tmp_path / "gamelists" / "snes" / "gamelist.xml"
    gamelist.parent.mkdir(parents=True)
    gamelist.write_text(
        '<?xml version="1.0"?>\n<gameList>\n'
        '  <game id="./roms/contra3.sfc" source="screenscraper.fr">\n'
        '    <path>./roms/contra3.sfc</path>\n'
        '    <name>Contra III</name>\n'
        '  </game>\n'
        '</gameList>\n'
    )
    # Create the ROM file so the tile is playable
    # _resolve_rom_paths looks for roms_root / Path(rom_path).name
    snes_dir = tmp_path / "snes"
    snes_dir.mkdir(parents=True)
    (snes_dir / "contra3.sfc").write_bytes(b"\x00")
    # Emulators cfg for core resolution
    cfg_dir = tmp_path / "retroarch_cfg" / "snes"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')
    return gamelist, tmp_path


# ---------------------------------------------------------------------------
# Unit: argv construction from LaunchConfig
# ---------------------------------------------------------------------------


class TestLaunchArgvConstruction:
    """build_launch_argv produces correct argv from LaunchConfig."""

    def test_argv_contains_core_rom_and_appendconfig(self):
        # Arrange
        cfg = LaunchConfig(
            core="/path/to/core.so",
            rom="/roms/game.sfc",
            retroarch_bin="/usr/bin/retroarch",
            video_driver="gl",
        )
        cfg_path = "/tmp/override.cfg"

        # Act
        argv = build_launch_argv(cfg, cfg_path)

        # Assert
        assert argv == [
            "/usr/bin/retroarch",
            "-L",
            "/path/to/core.so",
            "/roms/game.sfc",
            "--appendconfig",
            "/tmp/override.cfg",
        ]

    def test_override_cfg_text_includes_network_cmd_and_driver(self):
        # Arrange
        cfg = LaunchConfig(core="core", rom="rom", video_driver="metal", port=55355)

        # Act
        text = build_override_cfg_text(cfg)

        # Assert
        assert 'network_cmd_enable = "true"' in text
        assert 'network_cmd_port = "55355"' in text
        assert 'video_driver = "metal"' in text

    def test_override_cfg_text_omits_driver_when_none(self):
        # Arrange
        cfg = LaunchConfig(core="core", rom="rom", video_driver=None)

        # Act
        text = build_override_cfg_text(cfg)

        # Assert
        assert "video_driver" not in text


# ---------------------------------------------------------------------------
# Unit: readiness success via VERSION round-trip
# ---------------------------------------------------------------------------


class TestReadinessSuccess:
    """VersionProbe + ProcessLaunchOrchestrator reports READY on VERSION reply."""

    def test_readiness_reports_ready_on_version_reply(self):
        # Arrange
        transport = FakeNciTransport(version_reply="1.19.1")
        probe = VersionProbe(transport)
        launcher = FakeProcessLauncher()  # stays alive (returncode=None)
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=5.0)

        # Act
        state = asyncio.run(orch.launch(["retroarch", "-L", "core", "rom"]))

        # Assert
        assert state == LaunchState.READY
        assert launcher.launched_argv[0] == ["retroarch", "-L", "core", "rom"]
        assert "VERSION" in transport.queries


# ---------------------------------------------------------------------------
# Unit: readiness timeout/failure
# ---------------------------------------------------------------------------


class TestReadinessTimeout:
    """Timeout transport -> launch reports FAILED within budget, no hang."""

    def test_readiness_timeout_reports_failed(self):
        # Arrange — transport never responds
        transport = TimeoutNciTransport()
        probe = VersionProbe(transport)
        launcher = FakeProcessLauncher()
        orch = ProcessLaunchOrchestrator(
            launcher, probe, timeout=0.5, poll_interval=0.1
        )

        # Act
        state = asyncio.run(orch.launch(["retroarch"]))

        # Assert
        assert state == LaunchState.FAILED
        assert "Timeout" in orch.failure_reason

    def test_process_exit_reports_failed_immediately(self):
        # Arrange — process exits immediately with code 1
        transport = FakeNciTransport(version_reply="1.19.1")
        probe = VersionProbe(transport)
        launcher = FakeProcessLauncher(_exit_code=1, _stderr="core not found")
        orch = ProcessLaunchOrchestrator(launcher, probe, timeout=5.0)

        # Act
        state = asyncio.run(orch.launch(["retroarch"]))

        # Assert
        assert state == LaunchState.FAILED
        assert "exited with code 1" in orch.failure_reason
        assert "core not found" in orch.failure_reason


# ---------------------------------------------------------------------------
# Integration: MCP launch_game tool with fake launcher + transport
# ---------------------------------------------------------------------------


class TestMcpLaunchGameTool:
    """launch_game MCP tool uses injected fakes, no MockNciTransport in product path."""

    @pytest.fixture()
    def server_with_fakes(self, minimal_gamelist):
        """Build server with fake launcher + transport that responds to VERSION."""
        gamelist, media_root = minimal_gamelist
        fake_launcher = FakeProcessLauncher()
        fake_transport = FakeNciTransport(version_reply="1.19.1")

        server = build_server(
            gamelist_path=gamelist,
            system="snes",
            media_root=media_root,
            launcher=fake_launcher,
            transport_factory=lambda port: fake_transport,
        )
        return server, fake_launcher, fake_transport

    @pytest.fixture()
    def server_with_timeout_transport(self, minimal_gamelist):
        """Build server with fake launcher + transport that never responds."""
        gamelist, media_root = minimal_gamelist
        fake_launcher = FakeProcessLauncher()
        timeout_transport = TimeoutNciTransport()

        server = build_server(
            gamelist_path=gamelist,
            system="snes",
            media_root=media_root,
            launcher=fake_launcher,
            transport_factory=lambda port: timeout_transport,
        )
        return server, fake_launcher

    def test_launch_game_success_with_real_transport_injection(self, server_with_fakes):
        # Arrange
        server, fake_launcher, fake_transport = server_with_fakes
        tools = asyncio.run(server.list_tools())
        launch_tool = next(t for t in tools if t.name == "launch_game")

        # Act
        result = asyncio.run(launch_tool.fn(game_id="snes-contra3"))

        # Assert — successful launch
        assert result["state"] == "READY"
        assert result["game_id"] == "snes-contra3"
        # Core is either a real dylib path (resolve_core_path found it) or
        # the emulators.cfg fallback name. Both are valid unified behavior.
        assert result["core"]  # non-empty
        assert result["elapsed_seconds"] >= 0
        # Assert — launcher received correct argv structure
        assert len(fake_launcher.launched_argv) == 1
        argv = fake_launcher.launched_argv[0]
        assert "-L" in argv
        assert result["core"] in argv  # whatever core was resolved, it's in argv
        assert "--appendconfig" in argv
        # Assert — transport was queried for VERSION (not GET_STATUS)
        assert "VERSION" in fake_transport.queries

    def test_launch_game_timeout_surfaces_failure(self, server_with_timeout_transport):
        # Arrange
        server, fake_launcher = server_with_timeout_transport
        tools = asyncio.run(server.list_tools())
        launch_tool = next(t for t in tools if t.name == "launch_game")

        # Act
        result = asyncio.run(launch_tool.fn(game_id="snes-contra3"))

        # Assert — FAILED with timeout reason
        assert result["state"] == "FAILED"
        assert "reason" in result

    def test_launch_game_unknown_game_returns_failure(self, server_with_fakes):
        # Arrange
        server, _, _ = server_with_fakes
        tools = asyncio.run(server.list_tools())
        launch_tool = next(t for t in tools if t.name == "launch_game")

        # Act
        result = asyncio.run(launch_tool.fn(game_id="nonexistent"))

        # Assert
        assert result["state"] == "FAILED"
        assert "not found" in result["reason"].lower()


# ---------------------------------------------------------------------------
# Contract: no MockNciTransport in product code
# ---------------------------------------------------------------------------


class TestNoMockInProductPath:
    """MockNciTransport must never appear in the production server module."""

    def test_server_module_does_not_import_mock_transport(self):
        # Arrange
        import control_plane.server as mod
        source = Path(mod.__file__).read_text()

        # Assert — MockNciTransport is not referenced
        assert "MockNciTransport" not in source
