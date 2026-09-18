"""Pure domain models for the game wall. ZERO imports from factory.*."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GameTile:
    """A single game entry in the wall."""

    id: str
    title: str
    system: str  # e.g. "MAME", "SNES", "N64"
    art_url: str  # URL to box art image (empty => placeholder)
    art_name: str | None = None  # canonical libretro stem (incl. region); scraper fills this later
    video_url: str = ""  # relative local snap path (empty => no video; set => local file exists)
    expected_snap_path: str = ""  # relative path from XML <video>; set => remote snap known (fetch-eligible)
    playable: bool = True
    status_detail: str | None = None
    players: str = ""
    genre: str = ""
    year: str = ""
    publisher: str = ""
    rom_path: str = ""
    core: str | None = None
    # B17 detail fields (all Optional -> muted "--" when absent metadata; hidden when unbuilt feature)
    description: str | None = None
    developer: str | None = None
    release_date: str | None = None
    rating: str | None = None
    category: str | None = None
    screenshots: tuple[str, ...] = ()
    last_played: str | None = None
    play_count: int | None = None


@dataclass
class WallViewModel:
    """View-model for the game wall grid."""

    tiles: list[GameTile] = field(default_factory=list)
    columns: int = 4
