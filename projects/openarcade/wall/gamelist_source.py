"""EmulationStation gamelist.xml parser + selective loader. Pure core / IO at edge."""

from dataclasses import replace
from pathlib import Path
from xml.etree.ElementTree import fromstring, Element

from .models import GameTile


def _text(el: Element, tag: str) -> str | None:
    """Extract text from child element; empty/whitespace -> None."""
    child = el.find(tag)
    if child is None or not (child.text and child.text.strip()):
        return None
    return child.text.strip()


def _parse_releasedate(raw: str | None) -> str | None:
    """'YYYYMMDD...' -> 'YYYY-MM-DD', or None if empty/malformed/zero."""
    if not raw or len(raw) < 8 or raw[:8] == "00000000":
        return None
    try:
        y, m, d = raw[:4], raw[4:6], raw[6:8]
        int(y); int(m); int(d)
        if int(y) == 0:
            return None
        return f"{y}-{m}-{d}"
    except (ValueError, IndexError):
        return None


def _derive_art_url(image_text: str | None, system: str) -> str:
    """Derive relative art path: strip './' prefix, prepend system dir."""
    if not image_text:
        return ""
    rel = image_text.lstrip("./")
    return f"{system.lower()}/{rel}"


def _derive_video_url(video_text: str | None, system: str) -> str:
    """Derive relative video snap path: strip './' prefix, prepend system dir."""
    if not video_text:
        return ""
    rel = video_text.lstrip("./")
    return f"{system.lower()}/{rel}"


def parse_gamelist(xml_text: str, *, system: str) -> list[GameTile]:
    """Parse gamelist.xml text into GameTile list. PURE -- no IO."""
    root = fromstring(xml_text)
    tiles: list[GameTile] = []
    for game in root.iter("game"):
        path_text = _text(game, "path")
        if not path_text:
            continue
        stem = Path(path_text).stem
        title = _text(game, "name") or stem
        art_url = _derive_art_url(_text(game, "image"), system)
        video_url = _derive_video_url(_text(game, "video"), system)
        tiles.append(GameTile(
            id=f"{system.lower()}-{stem}".lower(),
            title=title,
            system=system.upper(),
            art_url=art_url,
            art_name=None,
            video_url=video_url,
            expected_snap_path=video_url,  # always set; carries "where" even before local fetch
            playable=True,
            description=_text(game, "desc"),
            developer=_text(game, "developer"),
            publisher=_text(game, "publisher") or "",
            genre=_text(game, "genre") or "",
            players=_text(game, "players") or "",
            rating=_text(game, "rating"),
            release_date=_parse_releasedate(_text(game, "releasedate")),
            rom_path=path_text,
        ))
    return tiles


def load_gamelist(
    gamelist_path: Path,
    *,
    system: str,
    media_root: Path,
    roms_root: Path,
    require_media: bool = True,
) -> list[GameTile]:
    """IO edge: read XML, parse, resolve rom paths, optionally filter to tiles with local cover."""
    xml_text = gamelist_path.read_text(encoding="utf-8")
    tiles = parse_gamelist(xml_text, system=system)
    if not require_media:
        # Still resolve rom paths even without media filter
        return _resolve_rom_paths(tiles, roms_root)
    covered = [t for t in tiles if t.art_url and (media_root / t.art_url).is_file()]
    # Clear video_url when local snap file is absent (keeps invariant: set => exists)
    result = []
    for t in covered:
        if t.video_url and not (media_root / t.video_url).is_file():
            t = replace(t, video_url="")
        result.append(t)
    return _resolve_rom_paths(result, roms_root)


def _resolve_rom_paths(tiles: list[GameTile], roms_root: Path) -> list[GameTile]:
    """Resolve relative rom_path to absolute; mark unresolvable tiles as non-playable."""
    resolved: list[GameTile] = []
    for t in tiles:
        if not t.rom_path:
            resolved.append(replace(t, playable=False, rom_path=""))
            continue
        candidate = roms_root / Path(t.rom_path).name
        if candidate.is_file():
            resolved.append(replace(t, rom_path=str(candidate)))
        else:
            resolved.append(replace(t, playable=False, rom_path=""))
    return resolved
