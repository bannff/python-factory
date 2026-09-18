"""Box-art URL resolution via the libretro-thumbnails CDN. Pure, no I/O."""

from urllib.parse import quote

# System short-code -> libretro-thumbnails repo folder name.
SYSTEM_FOLDERS: dict[str, str] = {
    "SNES": "Nintendo - Super Nintendo Entertainment System",
    "N64": "Nintendo - Nintendo 64",
    "GBA": "Nintendo - Game Boy Advance",
    "NES": "Nintendo - Nintendo Entertainment System",
    "MAME": "MAME",
}
_CDN = "https://thumbnails.libretro.com"


def box_art_url(system: str, art_name: str | None) -> str:
    """Build a libretro-thumbnails box-art URL, or '' if the system is unknown
    or art_name is empty. art_name is the FULL canonical No-Intro stem incl.
    region tag, e.g. "Street Fighter II (USA)"."""
    if not art_name:
        return ""
    folder = SYSTEM_FOLDERS.get(system.upper())
    if folder is None:
        return ""
    return f"{_CDN}/{quote(folder)}/Named_Boxarts/{quote(art_name)}.png"
