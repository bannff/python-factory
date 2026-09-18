"""Tests for Cores & Updates — cores_query + downloader + cores_tools.

Behavior-named, AAA style, FakeCoreDownloader only — NO network.
Security controls verified: allowlist, zip-slip, oversize, confinement, cleanup.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path

import pytest

from control_plane.cores_query import (
    KNOWN_CORES,
    CoreValidationError,
    InstalledCore,
    build_download_url,
    get_library_extension,
    list_installed_cores,
    validate_core_name,
)
from control_plane.downloader import (
    CoreDownloader,
    DownloadError,
    FakeCoreDownloader,
    install_core,
    _MAX_MEMBER_SIZE,
)


# ===== cores_query: validate_core_name =====


class TestValidateCoreName:
    """Security control #1: allowlist + charset validation."""

    def test_valid_core_passes(self):
        assert validate_core_name("snes9x") == "snes9x"
        assert validate_core_name("mupen64plus_next") == "mupen64plus_next"
        assert validate_core_name("mame2003_plus") == "mame2003_plus"

    def test_rejects_empty(self):
        with pytest.raises(CoreValidationError, match="non-empty"):
            validate_core_name("")

    def test_rejects_path_traversal(self):
        with pytest.raises(CoreValidationError, match="invalid characters"):
            validate_core_name("../../../etc/passwd")

    def test_rejects_dots(self):
        with pytest.raises(CoreValidationError, match="invalid characters"):
            validate_core_name("snes9x.so")

    def test_rejects_slashes(self):
        with pytest.raises(CoreValidationError, match="invalid characters"):
            validate_core_name("cores/snes9x")

    def test_rejects_backslash(self):
        with pytest.raises(CoreValidationError, match="invalid characters"):
            validate_core_name("cores\\snes9x")

    def test_rejects_spaces(self):
        with pytest.raises(CoreValidationError, match="invalid characters"):
            validate_core_name("snes 9x")

    def test_rejects_uppercase(self):
        with pytest.raises(CoreValidationError, match="invalid characters"):
            validate_core_name("SNES9X")

    def test_rejects_null_byte(self):
        with pytest.raises(CoreValidationError, match="null byte"):
            validate_core_name("snes9x\x00")

    def test_rejects_unknown_core(self):
        with pytest.raises(CoreValidationError, match="not in the known cores allowlist"):
            validate_core_name("totally_fake_core_xyz")

    def test_rejects_url_encoded(self):
        with pytest.raises(CoreValidationError, match="invalid characters"):
            validate_core_name("snes9x%2F..%2Fetc")


# ===== cores_query: build_download_url =====


class TestBuildDownloadUrl:
    """Security control #2: URL pinning from hardcoded base."""

    def test_macos_arm64(self):
        url = build_download_url("snes9x", "darwin", "arm64")
        assert url == "https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/snes9x_libretro.dylib.zip"

    def test_linux_x86_64(self):
        url = build_download_url("mupen64plus_next", "linux", "x86_64")
        assert url == "https://buildbot.libretro.com/nightly/linux/x86_64/latest/mupen64plus_next_libretro.so.zip"

    def test_unsupported_platform_raises(self):
        with pytest.raises(CoreValidationError, match="Unsupported platform"):
            build_download_url("snes9x", "freebsd", "riscv64")

    def test_invalid_core_name_revalidated(self):
        with pytest.raises(CoreValidationError):
            build_download_url("../../etc", "darwin", "arm64")


# ===== cores_query: list_installed_cores =====


class TestListInstalledCores:
    def test_empty_dir(self, tmp_path):
        assert list_installed_cores(tmp_path) == []

    def test_nonexistent_dir(self, tmp_path):
        assert list_installed_cores(tmp_path / "nope") == []

    def test_scans_dylib_with_info(self, tmp_path):
        # Create a fake core + info
        core = tmp_path / "snes9x_libretro.dylib"
        core.write_bytes(b"x" * 1024)
        info = tmp_path / "snes9x_libretro.info"
        info.write_text(
            'display_name = "Nintendo - SNES / SFC (Snes9x)"\n'
            'systemname = "Super Nintendo"\n'
            'supported_extensions = "smc|sfc|swc|fig"\n'
        )
        result = list_installed_cores(tmp_path)
        assert len(result) == 1
        c = result[0]
        assert c.display_name == "Nintendo - SNES / SFC (Snes9x)"
        assert c.system_name == "Super Nintendo"
        assert c.supported_extensions == ["smc", "sfc", "swc", "fig"]
        assert c.size_bytes == 1024

    def test_fallback_when_no_info(self, tmp_path):
        core = tmp_path / "gambatte_libretro.so"
        core.write_bytes(b"y" * 512)
        result = list_installed_cores(tmp_path)
        assert len(result) == 1
        assert result[0].display_name == "gambatte"
        assert result[0].system_name == ""

    def test_ignores_non_libretro_files(self, tmp_path):
        (tmp_path / "random.txt").write_text("hello")
        (tmp_path / "notacore.dylib").write_bytes(b"z")
        assert list_installed_cores(tmp_path) == []


# ===== downloader: FakeCoreDownloader =====


class TestFakeCoreDownloader:
    def test_produces_valid_zip_with_expected_member(self):
        dl = FakeCoreDownloader(sentinel_content=b"TEST_CORE")
        url = "https://buildbot.libretro.com/nightly/apple/osx/arm64/latest/snes9x_libretro.dylib.zip"
        data = dl.download(url)
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert "snes9x_libretro.dylib" in zf.namelist()
        assert zf.read("snes9x_libretro.dylib") == b"TEST_CORE"


# ===== downloader: install_core (via FakeCoreDownloader) =====


class TestInstallCore:
    """Happy path + security controls via fake downloader."""

    def test_happy_path_installs_core(self, tmp_path):
        cores_dir = tmp_path / "cores"
        dl = FakeCoreDownloader()
        path = install_core(
            "snes9x",
            platform="darwin",
            arch="arm64",
            cores_dir=cores_dir,
            downloader=dl,
        )
        assert path.exists()
        assert path.name == "snes9x_libretro.dylib"
        assert path.parent == cores_dir
        assert path.read_bytes() == b"FAKE_CORE_BINARY"

    def test_invalid_core_name_rejects(self, tmp_path):
        dl = FakeCoreDownloader()
        with pytest.raises(CoreValidationError, match="invalid characters"):
            install_core("../../etc/passwd", platform="darwin", arch="arm64",
                         cores_dir=tmp_path, downloader=dl)

    def test_unknown_core_rejects(self, tmp_path):
        dl = FakeCoreDownloader()
        with pytest.raises(CoreValidationError, match="allowlist"):
            install_core("nonexistent_core_xyz", platform="darwin", arch="arm64",
                         cores_dir=tmp_path, downloader=dl)

    def test_install_disabled_when_downloader_none(self):
        """ServerContext.core_downloader=None means install is disabled."""
        # This is tested at the tool level, not here directly.
        pass


# ===== Security control #3: Zip-slip =====


class TestZipSlipRejection:
    """Zip members with traversal paths must be rejected."""

    def _make_evil_zip(self, member_name: str, content: bytes = b"evil") -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(member_name, content)
        return buf.getvalue()

    def test_rejects_dotdot_path(self, tmp_path):
        """Member with '../' component is rejected."""
        class EvilDownloader:
            def download(self, url: str) -> bytes:
                return self._make_evil_zip("../../../etc/passwd")
            def _make_evil_zip(self, name):
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    zf.writestr(name, b"evil")
                return buf.getvalue()

        dl = EvilDownloader()
        cores_dir = tmp_path / "cores"
        with pytest.raises(DownloadError, match="traversal"):
            install_core("snes9x", platform="darwin", arch="arm64",
                         cores_dir=cores_dir, downloader=dl)
        # Security control #5: no partial file left behind
        if cores_dir.exists():
            assert not any(cores_dir.iterdir())

    def test_rejects_absolute_path(self, tmp_path):
        """Member with absolute path is rejected."""
        class AbsDownloader:
            def download(self, url: str) -> bytes:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as zf:
                    zf.writestr("/etc/passwd", b"evil")
                return buf.getvalue()

        dl = AbsDownloader()
        cores_dir = tmp_path / "cores"
        with pytest.raises(DownloadError, match="absolute path"):
            install_core("snes9x", platform="darwin", arch="arm64",
                         cores_dir=cores_dir, downloader=dl)


# ===== Security control #3: Oversize member =====


class TestOversizeMemberRejection:
    def test_rejects_oversize_member(self, tmp_path):
        """Zip member exceeding 100 MB declared file_size is rejected.

        We test the extraction guard directly since zipfile.writestr
        recalculates file_size from actual content. We construct a valid
        zip then patch the ZipInfo before extraction.
        """
        from unittest.mock import patch
        from control_plane.downloader import _extract_with_guards, _MAX_MEMBER_SIZE

        # Create a normal small zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("snes9x_libretro.dylib", b"x" * 100)
        zip_bytes = buf.getvalue()

        # Patch zipfile.ZipFile.infolist to return oversized file_size
        original_infolist = zipfile.ZipFile.infolist

        def patched_infolist(self):
            infos = original_infolist(self)
            for info in infos:
                info.file_size = _MAX_MEMBER_SIZE + 1
            return infos

        dest = tmp_path / "extract"
        dest.mkdir()
        with patch.object(zipfile.ZipFile, "infolist", patched_infolist):
            with pytest.raises(DownloadError, match="maximum allowed size"):
                _extract_with_guards(zip_bytes, dest, tmp_path / "cores")


# ===== Security control #4: Write confinement =====


class TestWriteConfinement:
    def test_installed_file_stays_under_cores_dir(self, tmp_path):
        """Final installed path must resolve under cores_dir."""
        cores_dir = tmp_path / "cores"
        dl = FakeCoreDownloader()
        path = install_core("snes9x", platform="darwin", arch="arm64",
                            cores_dir=cores_dir, downloader=dl)
        assert path.resolve().is_relative_to(cores_dir.resolve())


# ===== Security control #5: Failed download leaves no partial =====


class TestFailedDownloadCleanup:
    def test_network_error_leaves_no_partial(self, tmp_path):
        """On download failure, cores_dir has no leftover files."""
        class FailingDownloader:
            def download(self, url: str) -> bytes:
                raise DownloadError("Network timeout")

        cores_dir = tmp_path / "cores"
        with pytest.raises(DownloadError, match="timeout"):
            install_core("snes9x", platform="darwin", arch="arm64",
                         cores_dir=cores_dir, downloader=FailingDownloader())
        # cores_dir may not even exist
        if cores_dir.exists():
            assert not any(cores_dir.iterdir())

    def test_invalid_zip_leaves_no_partial(self, tmp_path):
        """On bad zip, cores_dir has no leftover files."""
        class BadZipDownloader:
            def download(self, url: str) -> bytes:
                return b"not a zip file at all"

        cores_dir = tmp_path / "cores"
        with pytest.raises(DownloadError, match="Invalid zip"):
            install_core("snes9x", platform="darwin", arch="arm64",
                         cores_dir=cores_dir, downloader=BadZipDownloader())
        if cores_dir.exists():
            assert not any(cores_dir.iterdir())


# ===== MCP Tool: install_core_tool via FakeCoreDownloader =====


class TestInstallCoreTool:
    """Integration: tool function invoked directly (no MCP transport)."""

    @pytest.fixture()
    def minimal_server(self, tmp_path):
        from control_plane.server import build_server
        import asyncio

        gamelist = tmp_path / "gamelists" / "snes" / "gamelist.xml"
        gamelist.parent.mkdir(parents=True)
        gamelist.write_text(
            '<?xml version="1.0"?>\n<gameList>\n'
            '  <game id="./roms/test.sfc" source="screenscraper.fr">\n'
            '    <path>./roms/test.sfc</path><name>Test</name></game>\n'
            '</gameList>\n'
        )
        cfg_dir = tmp_path / "retroarch_cfg" / "snes"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "emulators.cfg").write_text('default = "lr-snes9x2002"\n')

        # Monkeypatch build_server to inject cores context
        from control_plane.context import ServerContext
        from wall.gamelist_source import load_gamelist
        from factory.mcp_utils.runtime.tool_catalog import ToolCatalog

        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        tiles = load_gamelist(gamelist, system="snes", media_root=tmp_path,
                              roms_root=tmp_path / "snes", require_media=False)
        ctx = ServerContext(
            tiles=tiles, system="snes", media_root=tmp_path,
            roms_root=tmp_path / "snes", launcher=None, transport_factory=None,
            cores_dir=cores_dir, platform="darwin", arch="arm64",
            core_downloader=FakeCoreDownloader(),
        )
        mcp = ToolCatalog("test")
        from control_plane import cores_tools
        cores_tools.register(mcp, context=ctx)
        return mcp, cores_dir

    def _get_tool(self, server, name: str):
        import asyncio
        tools = asyncio.run(server.list_tools())
        return next((t for t in tools if t.name == name), None)

    def test_install_core_happy_path(self, minimal_server):
        mcp, cores_dir = minimal_server
        tool = self._get_tool(mcp, "install_core_tool")
        result = tool.fn(core_name="snes9x")
        assert result["installed"] is True
        assert (cores_dir / "snes9x_libretro.dylib").exists()

    def test_install_core_invalid_name_returns_error(self, minimal_server):
        mcp, _ = minimal_server
        tool = self._get_tool(mcp, "install_core_tool")
        result = tool.fn(core_name="../etc/passwd")
        assert "error" in result

    def test_install_disabled_when_no_downloader(self, tmp_path):
        """When core_downloader is None, tool returns error."""
        from control_plane.context import ServerContext
        from factory.mcp_utils.runtime.tool_catalog import ToolCatalog
        from control_plane import cores_tools

        ctx = ServerContext(
            tiles=[], system="snes", media_root=tmp_path,
            roms_root=tmp_path, launcher=None, transport_factory=None,
            cores_dir=tmp_path / "cores", platform="darwin", arch="arm64",
            core_downloader=None,
        )
        mcp = ToolCatalog("test")
        cores_tools.register(mcp, context=ctx)
        import asyncio
        tools = asyncio.run(mcp.list_tools())
        tool = next(t for t in tools if t.name == "install_core_tool")
        result = tool.fn(core_name="snes9x")
        assert "error" in result
        assert "disabled" in result["error"]


# ===== MCP Tool: list_cores =====


class TestListCoresTool:
    def test_list_cores_with_installed(self, tmp_path):
        from control_plane.context import ServerContext
        from factory.mcp_utils.runtime.tool_catalog import ToolCatalog
        from control_plane import cores_tools

        cores_dir = tmp_path / "cores"
        cores_dir.mkdir()
        (cores_dir / "snes9x_libretro.dylib").write_bytes(b"x" * 2048)
        (cores_dir / "snes9x_libretro.info").write_text('display_name = "Snes9x"\nsystemname = "SNES"\n')

        ctx = ServerContext(
            tiles=[], system="snes", media_root=tmp_path,
            roms_root=tmp_path, launcher=None, transport_factory=None,
            cores_dir=cores_dir, platform="darwin", arch="arm64",
        )
        mcp = ToolCatalog("test")
        cores_tools.register(mcp, context=ctx)
        import asyncio
        tools = asyncio.run(mcp.list_tools())
        tool = next(t for t in tools if t.name == "list_cores")
        result = tool.fn()
        assert len(result) == 1
        assert result[0]["display_name"] == "Snes9x"
        assert result[0]["system_name"] == "SNES"

    def test_list_cores_empty_when_no_dir(self, tmp_path):
        from control_plane.context import ServerContext
        from factory.mcp_utils.runtime.tool_catalog import ToolCatalog
        from control_plane import cores_tools

        ctx = ServerContext(
            tiles=[], system="snes", media_root=tmp_path,
            roms_root=tmp_path, launcher=None, transport_factory=None,
            cores_dir=None,
        )
        mcp = ToolCatalog("test")
        cores_tools.register(mcp, context=ctx)
        import asyncio
        tools = asyncio.run(mcp.list_tools())
        tool = next(t for t in tools if t.name == "list_cores")
        result = tool.fn()
        assert result == []
