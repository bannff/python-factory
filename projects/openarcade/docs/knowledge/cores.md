# RetroArch Cores Reference

A core is a libretro emulator plugin (`.dylib` on macOS, `.so` on Linux).
RetroArch loads one core per game launch via `-L <path>`.

## Core locations

- macOS: `~/Library/Application Support/RetroArch/cores/<stem>_libretro.dylib`
- Linux: `/usr/lib/libretro/<stem>_libretro.so` or `~/.config/retroarch/cores/`
- Env override: `OPENARCADE_CORES_DIR`

## When to use which core

### SNES
- **snes9x** — default. Fast, accurate for 99% of games.
- **bsnes** — cycle-accurate. Use for problem titles (Super Mario RPG timing,
  Megaman X2/X3 Cx4 chip). Heavier CPU.

### NES
- **nestopia** — default. Accurate mapper support.
- **mesen** — higher accuracy, slightly heavier.

### Genesis / Mega Drive / Sega CD / Game Gear / Master System
- **genesis_plus_gx** — covers all Sega 8/16-bit. Default for all.
- **picodrive** — needed for 32X only.

### N64
- **mupen64plus_next** — ONLY correct choice. ParaLLEl RSP/RDP for accuracy.
  Never use plain `mupen64plus` (legacy, broken on many titles).

### PlayStation
- **pcsx_rearmed** — ARM-optimized, good for Pi/low-end. Default.
- **beetle_psx_hw** — GPU-accelerated, higher accuracy. Use on desktop if
  pcsx_rearmed has glitches.

### GBA
- **mgba** — the only sensible choice. Fast, accurate.

### Arcade (MAME)
- **mame** (current) — default for modern romsets.
- **mame2003_plus** — use for MAME 0.78 romsets (common on Pi setups).
- **fbneo** — Final Burn Neo. Good for CPS1/2/3, Neo Geo. Faster than MAME
  for supported titles.

### Dreamcast
- **flycast** — the only maintained option. Needs decent CPU.

## Troubleshooting

- "Content cannot be loaded" → wrong romset version for the core, or missing
  BIOS files (psx needs `scph1001.bin`, dreamcast needs `dc_boot.bin` in system/).
- "Core not found" → stem is wrong or core isn't installed. Run `install_core_tool`.
- Slow/stuttering → core is too heavy for hardware. Drop to a lighter core
  (beetle_psx_hw → pcsx_rearmed, bsnes → snes9x).
