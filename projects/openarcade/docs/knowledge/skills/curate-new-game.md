# Skill: Curate a New Game (End-to-End)

## When to use
- User wants to add a new game to the library
- A ROM exists but isn't showing on the wall
- Bulk-importing a new system's games

## Steps

1. **Scan for the ROM**: call `scan_directory` to detect new ROMs in the
   system's ROM folder. This finds files not yet in the gamelist.

2. **Import**: call `import_games` to add discovered ROMs to the gamelist XML.
   This creates `<game>` entries with `<name>`, `<path>`, and placeholder `<image>`.

3. **Resolve art**: call `curate_art(kind="title")` to download the best
   available art (title screen preferred, falls back to snap then boxart).
   Art lands in `<system>/boxart/<Name>.png`.

4. **Verify core**: call `get_system_info` to confirm the system's default
   core is installed. If not, `install_core_tool`.

5. **Confirm on wall**: call `list_games` or `search_games(query="<title>")`.
   The game should now appear (cover art present + ROM resolved = curated).

6. **Test launch**: call `launch_game(game_id="<id>")` to confirm it boots.

## Troubleshooting

- Game imported but NOT on wall → art download failed. Check region tag matches
  No-Intro naming. Try `curate_art(kind="snap")` or `curate_art(kind="boxart")`
  as fallback.
- "Content cannot be loaded" → wrong romset version or missing BIOS.
- Multiple games with same title → region variants. Each is a separate entry;
  keep the one matching your cabinet's region preference.

## Bulk workflow

For a full new system:
1. Pull gamelists from cabinet (small, pull freely)
2. `scan_directory` + `import_games` for the whole folder
3. `curate_art` enriches all tiles at once
4. `install_core_tool` for the system's core
5. Spot-check a few launches
