# Curation Guide

Curation = making a game fully playable and beautiful on the wall: art resolved,
core assigned, gamelist entry present, ROM accessible.

## Art sources

Base CDN: `https://thumbnails.libretro.com/<System Folder>/<Kind>/<No-Intro Name>.png`

Kinds per system:
- **Named_Titles** — title screens (vibrant, wide)
- **Named_Snaps** — gameplay screenshots
- **Named_Boxarts** — box cover scans

**Preference order for wall tiles: title → snap → boxart** (vibrant > informative > safe).

System folder names: `wall/art_resolver.py::SYSTEM_FOLDERS`
(e.g. `snes` → `Nintendo - Super Nintendo Entertainment System`).

## Curation flow (per game)

1. Ensure ROM is present locally (SSH-pull from cabinet if needed — selective only).
2. Ensure gamelist entry exists: `<name>`, `<path>`, `<image>=./boxart/<Name>.png`.
3. Enrich art: download best-available kind into the cover slot via `curate_art`.
4. Resolve core: `get_system_info` confirms the default core is installed.
5. Verify: art file exists, core path exists, ROM path resolves, tile shows on wall.

## MCP tools for curation

- `curate_art(kind)` — enrich library art into cover slots (title/snap/boxart).
- `scan_directory` / `import_games` — detect ROMs + add to gamelist.
- `install_core_tool` — download/install a libretro core.
- `list_games` / `get_game` — verify game appears curated on the wall.

## File layout (dev machine)

- ROMs: `/tmp/oa_arcade/<system>/*.zip`
- Cover art: `/tmp/oa_arcade/<system>/boxart/<Name>.png`
- Gamelists: `/tmp/oa_arcade/gamelists/<system>/gamelist.xml`
- Cores (macOS): `~/Library/Application Support/RetroArch/cores/`

## Common failures

- Art not resolving → region tag mismatch between ROM filename and thumbnail DB.
- Game not on wall → missing cover art (load_gamelist with require_media=True
  filters games without local cover file).
- Launch fails → wrong core or missing core. Check `get_system_info`.
