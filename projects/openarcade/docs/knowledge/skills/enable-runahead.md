# Skill: Enable Runahead (Input Lag Reduction)

## What it does
Runahead runs the emulator N frames ahead internally, then displays the result,
effectively eliminating N frames of input lag. Essential for fighting games and
platformers on an arcade cabinet.

## When to use
- User reports "laggy" or "sluggish" controls
- Fighting games (KI, SF2, MK) feel unresponsive
- Platformers with tight jump windows

## Steps

1. **Check current setting**: call `get_global_settings()`. Look for
   `run_ahead_enabled` and `run_ahead_frames`.

2. **Enable**: call `set_runahead(frames=1)` for a safe default.
   - 1 frame: safe on all hardware, noticeable improvement
   - 2 frames: best for fighters, requires more CPU (~2x emulation speed needed)

3. **Verify feel**: launch a game and test responsiveness.

## Caveats

- Runahead DOUBLES (or triples for 2-frame) the CPU load — the core runs
  multiple frames per real frame. Heavy cores (N64, Dreamcast, PS2) likely
  can't sustain runahead.
- Safe for: SNES, NES, Genesis, GBA, GB/GBC, arcade (MAME 2D titles).
- Risky for: N64, PSX (depends on title), Dreamcast, Saturn.
- "Second instance" runahead (RetroArch advanced setting) is more compatible
  but uses 2x RAM. Not exposed via MCP tools currently.
