"""Library importer — IO edge: write/merge EmulationStation gamelist.xml.

NO-CLOBBER MERGE: existing entries keep their hand-edited metadata;
new entries are appended. Relative <path> convention preserved.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import (
    Element,
    SubElement,
    fromstring,
    tostring,
    indent,
)

from .library_scan import RomCandidate


def write_gamelist(
    candidates: list[RomCandidate],
    gamelist_path: Path,
    *,
    merge: bool = True,
) -> int:
    """Write/merge RomCandidate entries into a gamelist.xml.

    NO-CLOBBER: if merge=True and gamelist exists, read it first and
    only APPEND entries whose <path> is not already present. Never
    overwrites existing entries' hand-edited metadata.

    Returns count of NEW entries written.
    """
    existing_paths: set[str] = set()
    root: Element

    if merge and gamelist_path.exists():
        xml_text = gamelist_path.read_text(encoding="utf-8")
        root = fromstring(xml_text)
        # Collect existing <path> values so we skip them
        for game_el in root.iter("game"):
            path_el = game_el.find("path")
            if path_el is not None and path_el.text:
                existing_paths.add(path_el.text.strip())
    else:
        root = Element("gameList")

    # Only append genuinely new entries
    new_count = 0
    for c in candidates:
        if c.rom_path in existing_paths:
            continue
        game_el = SubElement(root, "game")
        _add_child(game_el, "path", c.rom_path)
        _add_child(game_el, "name", c.title)
        existing_paths.add(c.rom_path)
        new_count += 1

    if new_count > 0:
        gamelist_path.parent.mkdir(parents=True, exist_ok=True)
        indent(root, space="  ")
        gamelist_path.write_text(
            '<?xml version="1.0"?>\n' + tostring(root, encoding="unicode"),
            encoding="utf-8",
        )

    return new_count


def _add_child(parent: Element, tag: str, text: str) -> None:
    """Append a simple text child element."""
    el = SubElement(parent, tag)
    el.text = text
