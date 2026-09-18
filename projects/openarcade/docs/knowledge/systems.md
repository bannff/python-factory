# System → Core Mapping

Default core assignments for each emulated system. These are the cores
RetroArch loads via `-L <core>_libretro.{dylib,so}`.

| System     | Core Stem              | Full Name                        |
|------------|------------------------|----------------------------------|
| snes       | snes9x                 | Snes9x (fast, accurate enough)   |
| nes        | nestopia               | Nestopia UE                      |
| genesis    | genesis_plus_gx        | Genesis Plus GX                  |
| n64        | mupen64plus_next       | Mupen64Plus-Next (ParaLLEl RSP)  |
| psx        | pcsx_rearmed           | PCSX ReARMed                     |
| gba        | mgba                   | mGBA                             |
| gb         | gambatte               | Gambatte                         |
| gbc        | gambatte               | Gambatte (GBC mode)              |
| arcade     | mame                   | MAME (current)                   |
| dreamcast  | flycast                | Flycast                          |
| saturn     | mednafen_saturn        | Mednafen Saturn                  |
| segacd     | genesis_plus_gx        | Genesis Plus GX (Sega CD mode)   |
| sega32x    | picodrive              | PicoDrive                        |
| gamegear   | genesis_plus_gx        | Genesis Plus GX (GG mode)        |
| mastersystem | genesis_plus_gx      | Genesis Plus GX (SMS mode)       |
| atari2600  | stella                 | Stella                           |
| pce        | mednafen_pce           | Mednafen PCE                     |
| ngp        | mednafen_ngp           | Mednafen Neo Geo Pocket          |
| wonderswan | mednafen_wswan         | Mednafen WonderSwan              |
| ps2        | pcsx2                  | PCSX2 (heavy, x86_64 only)       |
| gamecube   | dolphin                | Dolphin (heavy)                  |
| wii        | dolphin                | Dolphin (Wii mode)               |

## Notes

- Arcade games may need a SPECIFIC MAME version romset (0.78, 0.174, current).
  Check the ROM's expected emulator before assuming `mame` works.
- N64: `mupen64plus_next` with ParaLLEl RSP is strongly preferred over the
  older `mupen64plus` (no suffix) core for accuracy + speed.
- Dreamcast/Saturn/PS2/GC/Wii are "heavy" cores — may not run at full speed
  on low-end hardware (Ryzen 5800U ceiling: PSX/N64/Dreamcast comfortable;
  Saturn marginal; PS2/GC/Wii require 7840HS+ class).
