# ROM Naming Conventions

OpenArcade's art resolution and gamelist matching depend on standardized ROM
naming. Two databases define the canonical names:

## No-Intro (cartridge-based systems)

Format: `Title (Region)[flags].ext`

Examples:
- `Super Metroid (USA, Europe).sfc`
- `Killer Instinct (USA).zip`
- `Legend of Zelda, The - A Link to the Past (USA).sfc`

### Region tags (common)
- `(USA)` / `(Europe)` / `(Japan)` / `(World)`
- Multi-region: `(USA, Europe)` — comma-separated, alphabetical.

### Flags (in square brackets, after region)
- `[!]` — verified good dump (older convention)
- `(Rev 1)` / `(Rev A)` — revision
- `(Beta)` / `(Proto)` — pre-release
- `(Unl)` — unlicensed

### Key rules
- "The" moves to the end: `Legend of Zelda, The - ...`
- Subtitles after ` - `: `Mega Man X2 - ...` (not colon)
- Region is REQUIRED for art lookup (libretro-thumbnails index by full stem)

## Redump (disc-based: PSX, Dreamcast, Saturn, Sega CD)

Same naming schema but file is `.cue`/`.bin` or `.chd` (compressed).

Examples:
- `Castlevania - Symphony of the Night (USA).chd`
- `Sonic CD (USA).cue` + associated `.bin` tracks

## Art matching

libretro-thumbnails uses the EXACT No-Intro/Redump stem (without extension)
as the filename:

```
https://thumbnails.libretro.com/<System Folder>/Named_Titles/<Stem>.png
```

If art doesn't resolve, the most common cause is a region tag mismatch
(e.g. ROM says `(USA, Australia)` but thumbnail DB expects `(USA)`).

## Gamelist XML

EmulationStation gamelist.xml `<path>` uses the filename as-is. The `<name>`
field is the display title (cleaned — no region tag, no article-move).
The `<image>` path must match what's in the `boxart/` folder.
