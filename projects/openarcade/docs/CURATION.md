# OpenArcade Curation Guide

The purpose of the in-app assistant (and any agent): when a game or collection is
added, **auto-curate everything** — vibrant art, the right core, and a gamelist
entry — so the library looks great and just works. This doc is the map.

## Art sources (libretro-thumbnails)

Base CDN: `https://thumbnails.libretro.com/<System Folder>/<Kind>/<No-Intro Name>.png`

- **Kinds** (per system): `Named_Titles` (title screens — vibrant, wide),
  `Named_Snaps` (gameplay), `Named_Boxarts` (box art).
- **Vibrant tiles = title/snap art**, NOT box art. Curation preference order:
  **title → snap → boxart** (see `wall/art_curator.py::ART_PREFERENCE`).
- **System folder names** live in `wall/art_resolver.py::SYSTEM_FOLDERS`
  (e.g. SNES → `Nintendo - Super Nintendo Entertainment System`). Add systems there.
- **Name** = the full No-Intro stem incl. region tag, e.g. `Killer Instinct (USA)`.
  It must match the gamelist `<image>` basename.

## Where things live (this dev machine)

- **ROMs**: `/tmp/oa_arcade/<system>/*.zip` (pulled selectively from the cabinet
  `playbox4` @ pi@192.168.86.120 — SSH; media is selective, never bulk-mirrored).
- **Cover slot** (what tiles show): `/tmp/oa_arcade/<system>/boxart/<name>.png`.
  The gamelist `<image>` points here; curation writes the chosen art kind here.
- **Gamelists**: `/tmp/oa_arcade/gamelists/<system>/gamelist.xml` (EmulationStation
  format: `<game><name><path><image><desc>...`). Metadata is small — pull freely.
- **Cores** (macOS): `~/Library/Application Support/RetroArch/cores/<stem>_libretro.dylib`.
  System→core-stem map: `wall/core_resolver.py::DEFAULT_CORE_STEMS` (snes→snes9x, …).

## Core resolution

`wall/core_resolver.py::resolve_core_path(system)` → the real core library path
(`.dylib` on mac, `.so` on linux), env-overridable via `OPENARCADE_CORES_DIR`.
Returns "" if not installed (honest — never a fake path).

## Launch (macOS reality)

Must use `open -a RetroArch.app --args -L <core.dylib> <rom> --appendconfig <cfg>`
(exec'ing the inner binary exits 0 without launching). See `wall/launch_handler.py`.

## Curation flow (per game / collection)

1. Ensure the ROM is present locally (SSH-pull from the cabinet if needed, selective).
2. Ensure a gamelist entry exists (`<name>`, `<path>`, `<image>=./boxart/<name>.png`).
3. **Enrich art**: download best-available kind (title→snap→boxart) into the cover
   slot — MCP tool `curate_art(kind="title")` / `enrich_tiles_art()`.
4. Resolve the core (`resolve_core_path`) so Play works.
5. Verify: art file exists, core path exists, ROM path resolves.

## MCP tools (drive these — one source of truth for assistant + any agent)

- `curate_art(kind)` — enrich the whole library's art into cover slots.
- `scan_directory` / `import_games` — detect + add ROMs to the gamelist.
- `install_core` — download a libretro core.
- `get_game` / `list_games` / `list_systems` / `get_system_info` — read the library.
- `launch_game` — hand off to RetroArch.
