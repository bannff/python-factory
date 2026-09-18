"""Curation tools — enrich the library with vibrant art (title/snap/boxart).

The agent's core job: given the library, fetch the best art so tiles look great
(Polycade-style title/snap art), writing into the local cover slot each tile
already points at. register() wires this onto FastMCP (cerv6 pattern); the pure
enrich_tiles_art() is downloader-injectable so tests never hit the network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from wall.art_curator import ART_PREFERENCE, art_url
from wall.models import GameTile

from .context import ServerContext


class ArtDownloader(Protocol):
    """Fetches image bytes for a URL, or None if unavailable (non-200/error)."""

    def get(self, url: str) -> bytes | None: ...  # pragma: no cover


def enrich_tiles_art(
    tiles: list[GameTile],
    media_root: Path,
    system: str,
    *,
    downloader: ArtDownloader,
    preference: tuple[str, ...] = ART_PREFERENCE,
) -> dict[str, Any]:
    """Download the best-available art per tile into its local cover slot.

    For each tile, tries the art kinds in `preference` order (title -> snap ->
    boxart by default) and writes the first that resolves to the path the tile's
    art_url already references (media_root / art_url). Honest: a tile whose art
    can't be fetched is counted as skipped, never faked.
    """
    curated = 0
    skipped = 0
    by_kind: dict[str, int] = {}
    for t in tiles:
        if not t.art_url:
            skipped += 1
            continue
        stem = Path(t.art_url).stem  # No-Intro name, e.g. "Killer Instinct (USA)"
        dest = media_root / t.art_url
        got = False
        for kind in preference:
            url = art_url(system, stem, kind)
            if not url:
                continue
            data = downloader.get(url)
            if data:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                by_kind[kind] = by_kind.get(kind, 0) + 1
                curated += 1
                got = True
                break
        if not got:
            skipped += 1
    return {"curated": curated, "skipped": skipped, "by_kind": by_kind}


class _UrllibDownloader:
    """Real HTTP downloader (stdlib). Returns bytes on 200, else None."""

    def get(self, url: str) -> bytes | None:
        import urllib.request

        try:
            with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
                if getattr(resp, "status", 200) == 200:
                    return resp.read()
        except Exception:
            return None
        return None


def register(mcp: Any, *, context: ServerContext) -> None:
    """Register curation tools (curate_art)."""

    @mcp.tool()
    def curate_art(kind: str = "title") -> dict[str, Any]:
        """Curate library art: download vibrant `kind` art (title|snap|boxart)
        for every game into its local cover slot. Falls back through the other
        kinds when the preferred one isn't available. Returns curated/skipped counts.
        """
        pref = (kind, *[k for k in ART_PREFERENCE if k != kind])
        return enrich_tiles_art(
            context.tiles,
            context.media_root,
            context.system,
            downloader=_UrllibDownloader(),
            preference=pref,
        )
