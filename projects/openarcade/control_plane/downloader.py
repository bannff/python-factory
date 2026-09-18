"""Core downloader — Protocol + real/fake implementations.

Security controls:
- #2 URL pinning: HTTPS only, redirect host verification.
- #3 Zip-slip guard: reject absolute paths, '..', enforce size/count caps.
- #4 Write confinement: only writes under cores_dir.
- #5 Fail-secure: temp path -> validate -> atomic move; cleanup on failure.
- #6 No secrets/verbose internals leaked in errors.

Residual risk: buildbot.libretro.com does NOT publish per-file checksums
(SHA256/MD5) alongside nightly zips. We cannot verify integrity beyond TLS
transport security. If they add checksums in the future, verification should
be added here.
"""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from .cores_query import (
    CoreValidationError,
    build_download_url,
    get_library_extension,
    validate_core_name,
)


# --- Security control #3: Zip extraction limits ---
_MAX_MEMBER_SIZE = 100 * 1024 * 1024  # 100 MB per file
_MAX_TOTAL_SIZE = 200 * 1024 * 1024   # 200 MB total extracted
_MAX_MEMBER_COUNT = 10                  # Cores zips have 1 file; be generous


class DownloadError(Exception):
    """Raised on any download/install failure. Sanitized message only."""


@runtime_checkable
class CoreDownloader(Protocol):
    """Protocol for downloading core zip bytes. Testable seam."""

    def download(self, url: str) -> bytes:
        """Download the zip from url and return raw bytes.

        Raises DownloadError on any failure.
        """
        ...


class HttpCoreDownloader:
    """Real downloader using stdlib urllib. HTTPS + redirect guard.

    Security control #2: TLS verification ON (stdlib default).
    Redirect guard: reject any redirect whose host != buildbot.libretro.com.
    """

    _ALLOWED_HOST = "buildbot.libretro.com"
    _TIMEOUT = 60  # seconds

    def download(self, url: str) -> bytes:
        """Download core zip via HTTPS with redirect host verification."""
        try:
            # Custom opener with redirect handler
            opener = urllib.request.build_opener(_SafeRedirectHandler(self._ALLOWED_HOST))
            req = urllib.request.Request(url)
            with opener.open(req, timeout=self._TIMEOUT) as resp:
                return resp.read()
        except DownloadError:
            raise
        except urllib.error.HTTPError as e:
            raise DownloadError(f"HTTP {e.code} downloading core") from None
        except urllib.error.URLError as e:
            raise DownloadError("Network error downloading core") from None
        except Exception:
            raise DownloadError("Unexpected error downloading core") from None


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject redirects to hosts other than the allowed buildbot host.

    Security control #2: offsite redirect = abort.
    """

    def __init__(self, allowed_host: str) -> None:
        super().__init__()
        self._allowed_host = allowed_host

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlparse
        parsed = urlparse(newurl)
        if parsed.hostname != self._allowed_host:
            raise DownloadError(
                "Redirect to unauthorized host blocked"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class FakeCoreDownloader:
    """Test double: writes a valid zip containing a sentinel library file.

    NEVER hits the network. Used in tests.
    """

    def __init__(self, *, sentinel_content: bytes = b"FAKE_CORE_BINARY") -> None:
        self._sentinel = sentinel_content

    def download(self, url: str) -> bytes:
        """Create a zip in-memory with one file matching the expected core filename."""
        # Parse expected filename from URL: .../<core>_libretro.<ext>.zip
        # e.g. https://buildbot.../snes9x_libretro.dylib.zip -> snes9x_libretro.dylib
        basename = url.rsplit("/", 1)[-1]  # snes9x_libretro.dylib.zip
        if basename.endswith(".zip"):
            inner_name = basename[:-4]  # snes9x_libretro.dylib
        else:
            inner_name = basename

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(inner_name, self._sentinel)
        return buf.getvalue()


def install_core(
    core_name: str,
    *,
    platform: str,
    arch: str,
    cores_dir: Path,
    downloader: CoreDownloader,
) -> Path:
    """Download, validate, and install a core. Returns path to installed library.

    Full security pipeline:
    1. Validate core_name (allowlist + charset).
    2. Build URL from hardcoded base.
    3. Download via injected downloader (HTTPS + redirect guard).
    4. Extract with zip-slip + size guards.
    5. Atomic move into cores_dir.
    6. Cleanup on any failure.

    Raises:
        CoreValidationError: invalid core_name or platform.
        DownloadError: network/extraction/validation failure.
    """
    # 1. Validate (Security control #1)
    validate_core_name(core_name)

    # 2. Build URL (Security control #2 — hardcoded base)
    url = build_download_url(core_name, platform, arch)
    ext = get_library_extension(platform, arch)
    expected_filename = f"{core_name}_libretro.{ext}"

    # 3. Download
    zip_bytes = downloader.download(url)

    # 4. Extract with guards — to a temp dir first (Security control #5)
    tmp_dir = Path(tempfile.mkdtemp(prefix="oa_core_"))
    installed_path: Path | None = None

    try:
        _extract_with_guards(zip_bytes, tmp_dir, cores_dir)

        # Find the extracted library file
        extracted = tmp_dir / expected_filename
        if not extracted.is_file():
            # Zip might contain a slightly different name; find *_libretro.<ext>
            candidates = [f for f in tmp_dir.iterdir() if f.name.endswith(f"_libretro.{ext}")]
            if not candidates:
                raise DownloadError("Zip does not contain expected core library")
            extracted = candidates[0]

        # 5. Atomic move into cores_dir (Security control #4 + #5)
        cores_dir.mkdir(parents=True, exist_ok=True)
        final_path = cores_dir / extracted.name

        # Security control #4: verify final path is under cores_dir
        if not final_path.resolve().is_relative_to(cores_dir.resolve()):
            raise DownloadError("Write target escapes cores directory")

        shutil.move(str(extracted), str(final_path))
        installed_path = final_path

    except (CoreValidationError, DownloadError):
        raise
    except Exception:
        raise DownloadError("Failed to install core") from None
    finally:
        # Cleanup temp dir (Security control #5)
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return installed_path


def _extract_with_guards(zip_bytes: bytes, dest: Path, cores_dir: Path) -> None:
    """Extract zip with zip-slip + size guards (Security control #3).

    - Reject absolute paths and any '..' in member names.
    - (dest / member).resolve() MUST start with dest.resolve().
    - Per-file size cap: 100 MB.
    - Total size cap: 200 MB.
    - Member count cap: 10.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except (zipfile.BadZipFile, Exception):
        raise DownloadError("Invalid zip archive")

    members = zf.infolist()

    # Member count guard
    if len(members) > _MAX_MEMBER_COUNT:
        raise DownloadError("Zip contains too many entries")

    total_extracted = 0
    dest_resolved = dest.resolve()

    for info in members:
        # Skip directories
        if info.is_dir():
            continue

        member_name = info.filename

        # Zip-slip guard: reject absolute paths
        if os.path.isabs(member_name):
            raise DownloadError("Zip member has absolute path")

        # Zip-slip guard: reject '..' path components
        if ".." in member_name.split("/"):
            raise DownloadError("Zip member contains path traversal")
        if ".." in member_name.split("\\"):
            raise DownloadError("Zip member contains path traversal")

        # Resolve target and verify containment
        target = (dest / member_name).resolve()
        if not target.is_relative_to(dest_resolved):
            raise DownloadError("Zip member resolves outside extraction directory")

        # Per-file size guard
        if info.file_size > _MAX_MEMBER_SIZE:
            raise DownloadError("Zip member exceeds maximum allowed size")

        # Total size guard
        total_extracted += info.file_size
        if total_extracted > _MAX_TOTAL_SIZE:
            raise DownloadError("Zip total size exceeds maximum allowed")

        # Extract single file
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            dst.write(src.read())

    zf.close()
