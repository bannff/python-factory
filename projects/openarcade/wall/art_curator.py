"""Curation art sources — boxart / title / snap URL resolution. Pure, no I/O.

Polycade-style vibrant tiles come from TITLE-screen / gameplay-SNAP art (wide,
colorful) rather than box art. libretro-thumbnails hosts all three per system:
  Named_Boxarts / Named_Titles / Named_Snaps
This module builds those URLs; the curation tool downloads the best available
kind into the local cover slot the gamelist already points at.
"""

from __future__ import annotations

from urllib.parse import quote

from .art_resolver import SYSTEM_FOLDERS, _CDN

# Preference order for a vibrant, Polycade-like grid: title first, then snap,
# then box art as the last resort.
ART_PREFERENCE: tuple[str, ...] = ("title", "snap", "boxart")

_KIND_DIR: dict[str, str] = {
    "boxart": "Named_Boxarts",
    "title": "Named_Titles",
    "snap": "Named_Snaps",
}


def art_url(system: str, name: str, kind: str = "title") -> str:
    """Build a libretro-thumbnails URL for the given art kind, or "" if unknown.

    name is the full No-Intro stem incl. region tag, e.g. "Killer Instinct (USA)".
    """
    if not name:
        return ""
    folder = SYSTEM_FOLDERS.get(system.upper())
    if folder is None or kind not in _KIND_DIR:
        return ""
    return f"{_CDN}/{quote(folder)}/{_KIND_DIR[kind]}/{quote(name)}.png"


def art_urls_in_preference(system: str, name: str) -> list[tuple[str, str]]:
    """Return [(kind, url), ...] in vibrant-first preference order for a game."""
    out: list[tuple[str, str]] = []
    for kind in ART_PREFERENCE:
        u = art_url(system, name, kind)
        if u:
            out.append((kind, u))
    return out
