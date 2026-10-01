"""Reject accidental host-only files before staging an audio cohort."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

CLIP_NAME = re.compile(r"clip-[0-9]{3}\.wav")
SHA256 = re.compile(r"[0-9a-f]{64}")


def validate_payload(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("payload must be a regular directory")
    cohort = json.loads((root / "cohort.json").read_text(encoding="utf-8"))
    if set(cohort) != {"schema_version", "clips"} or cohort["schema_version"] != 1:
        raise ValueError("payload cohort fields are invalid")
    clips = cohort["clips"]
    if not isinstance(clips, list) or not clips:
        raise ValueError("payload cohort must contain clips")
    expected = {"model.npz", "cohort.json"}
    ids: set[str] = set()
    for clip in clips:
        if not isinstance(clip, dict) or set(clip) != {"clip_id", "filename", "sha256"}:
            raise ValueError("payload clip metadata must be label-free")
        name, digest = clip["filename"], clip["sha256"]
        if (
            not isinstance(name, str) or CLIP_NAME.fullmatch(name) is None
            or clip["clip_id"] != name[:-4] or clip["clip_id"] in ids
            or not isinstance(digest, str) or SHA256.fullmatch(digest) is None
        ):
            raise ValueError("payload clip identity or hash is invalid")
        ids.add(clip["clip_id"])
        relative = f"clips/{name}"
        expected.add(relative)
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("payload WAV hash mismatch")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("payload cannot contain symlinks")
        relative = path.relative_to(root).as_posix()
        if path.is_file():
            actual.add(relative)
        elif path.is_dir() and relative != "clips":
            raise ValueError("payload has an unexpected directory")
    if actual != expected:
        raise ValueError("payload has missing or extra files")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: payload_layout.py PAYLOAD_DIR")
    validate_payload(Path(sys.argv[1]))
