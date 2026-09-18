"""Reentrant process and directory authority lock for local CAN lifecycle I/O."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
import threading
from typing import Iterator

_PROCESS_LOCK = threading.RLock()
_DEPTH = threading.local()


@contextmanager
def lock_authority(directory_fd: int) -> Iterator[None]:
    """Serialize threads and processes, while permitting nested effect locks."""
    with _PROCESS_LOCK:
        depth = getattr(_DEPTH, "value", 0)
        if depth:
            _DEPTH.value = depth + 1
            try:
                yield
            finally:
                _DEPTH.value -= 1
            return
        authority = os.open(
            ".", os.O_RDONLY | os.O_NOFOLLOW | os.O_DIRECTORY,
            dir_fd=directory_fd,
        )
        try:
            fcntl.flock(authority, fcntl.LOCK_EX)
            _DEPTH.value = 1
            yield
        finally:
            _DEPTH.value = 0
            fcntl.flock(authority, fcntl.LOCK_UN)
            os.close(authority)


__all__ = ["lock_authority"]
