"""On-demand snap fetcher. Selective SCP — one file per call, never bulk."""

from __future__ import annotations

import asyncio
import shlex
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class SnapFetcher(Protocol):
    """Async interface for fetching a single video snap on demand."""

    async def fetch(self, relative_path: str, dest: Path) -> bool:
        """Fetch one snap to dest. Returns True iff file exists after call."""
        ...


class ScpSnapFetcher:
    """Real SCP-based fetcher. Pulls ONE file from the Pi over SSH."""

    def __init__(
        self,
        host: str = "192.168.86.120",
        remote_base: str = "~/RetroPie/roms",
        user: str = "pi",
    ) -> None:
        self._host = host
        self._remote_base = remote_base
        self._user = user

    async def fetch(self, relative_path: str, dest: Path) -> bool:
        """SCP one file. No retry storm — single attempt."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        # scp re-parses the REMOTE path through the Pi's shell, so it must be
        # shell-quoted or filenames with spaces/parens (most No-Intro names) split
        # and fail. Quote ONLY the relative path so remote_base's ~ still expands.
        remote = f"{self._user}@{self._host}:{self._remote_base}/{shlex.quote(relative_path)}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "scp", "-o", "StrictHostKeyChecking=no",
                "-o", "ConnectTimeout=5",
                remote, str(dest),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()
            return proc.returncode == 0 and dest.is_file()
        except OSError:
            return False


class FakeSnapFetcher:
    """Test double. Writes a stub file (or returns False) — no network."""

    def __init__(self, *, succeed: bool = True) -> None:
        self._succeed = succeed
        self.calls: list[tuple[str, Path]] = []

    async def fetch(self, relative_path: str, dest: Path) -> bool:
        self.calls.append((relative_path, dest))
        if self._succeed:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\x00\x00\x00\x1cftyp")  # stub mp4
            return True
        return False
