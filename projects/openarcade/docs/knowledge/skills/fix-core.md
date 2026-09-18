# Skill: Fix Wrong or Missing Core

## When to use
- Game launches but runs wrong emulator (wrong system, graphical glitches)
- "Core not found" error on launch
- Game runs too slowly (core too heavy for hardware)

## Steps

1. **Identify the current core**: call `get_system_info` for the game's system.
   Note the `default_core` and whether it's installed.

2. **Determine the correct core**: check `knowledge_search("core for <system>")`.
   Cross-reference with cores.md for guidance on when alternatives are needed.

3. **Install if missing**: call `install_core_tool(core_name="<stem>")`.
   Wait for download to complete.

4. **Verify**: call `get_system_info` again — confirm core path is now valid.

5. **Test launch**: call `launch_game(game_id="<id>")`. Confirm it starts
   successfully (no "content cannot be loaded" error).

## Common scenarios

- SNES game with Cx4 chip glitches → switch from snes9x to bsnes
- N64 game broken → ensure mupen64plus_next (NOT plain mupen64plus)
- Arcade ROM "content cannot be loaded" → romset version mismatch; need the
  ROM version matching the MAME core version (0.78 for mame2003_plus, current for mame)
- PSX game black screen → missing BIOS (`scph1001.bin` in RetroArch system/ dir)
