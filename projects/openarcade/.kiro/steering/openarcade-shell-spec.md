---
inclusion: always
---
# OpenArcade Shell Spec — SHELL FIRST (read with openarcade-mission.md)

BLUF: Build and perfect the **shell** — every capability RetroArch exposes,
reskinned beautifully + MCP-backed + agent-drivable, PLUS the AI assistant —
**before** adding or playing real games. Games are the LAST thing we wire, only
to test a finished shell. Do not propose game/content work while shell parity is
incomplete.

## The wrapper principle (non-negotiable)

A "beautiful wrapper" = **RetroArch's capabilities, presented as our own
beautiful screens.** If RetroArch has a menu for it, OpenArcade has a screen for
it (reskinned per minimalist-ui-design) OR an explicit handoff to RGUI. We never
reimplement the emulator; we surface or hand off. Missing menus are unbuilt
scope, not architecture — build them.

## Spec source of truth

- **RetroArch menu** (the parity target): the user-provided RetroArch Main Menu
  screenshot + the upstream project `https://github.com/libretro/RetroArch`
  (menu structure under `menu/`). Mirror the USER-FACING capabilities, not code.
- When unsure what a shell screen must do, look at what RetroArch's equivalent
  menu does and reskin that.

## Shell parity checklist = DEFINITION OF DONE

The shell is "done" only when every row below has: a beautiful OpenArcade screen,
an MCP tool behind it (UI + assistant consume the same tool), and tests.

| RetroArch capability | OpenArcade screen | MCP tool(s) | Status |
|---|---|---|---|
| Playlists / History / Favorites | Library wall | list_games/search_games/get_game | ✅ done |
| Settings: Video/Audio/Latency | Settings | get_global_settings/set_setting | ✅ done |
| Settings: **Input / Controller remap** | **Controllers** | get_remap/set_remap | ❌ build (write, not display-only) |
| **Import Content** (add/scan games) | **Library Manager** | scan_directory/import_game | ❌ build |
| **Online Updater** (cores, thumbnails, assets) | **Cores & Updates** | list_cores/install_core/update_assets (or honest RGUI handoff) | ❌ build |
| **Information** (system/core/stability) | **Information** | get_system_info | ❌ build |
| Configuration File | (handoff to RGUI) | — | handoff |
| Load Core / Contentless Cores | (advanced; handoff) | — | defer/handoff |
| **AI Assistant** (the main use case) | **Assistant panel** | consumes ALL tools above | ❌ build |
| Launch a game | Play button | launch_game | ✅ tool real; full play-test = LAST |

Nav rail must grow from 3 icons to one entry per built shell screen.

## How each shell screen is built (every bead)

1. GATE (meta-architect, mission + this spec checklist) → APPROVED.
2. BUILD (implementer): own `*_tools.py` module (cerv6 pattern) + a beautiful
   screen (minimalist-ui-design) + nav-rail entry. Pure core shared by UI+tool;
   UI never imports the MCP server.
3. BREAK (qa-tester): behavior contracts; no-clobber + negative-input covered.
4. VERIFY: suite green; visual screens flagged for real-display confirm (headless
   cannot judge motion/fidelity).
5. commit + `bd close`. Then next shell screen.

## The AI assistant (first-class, not an afterthought)

The assistant is a shell surface, not a feature bolt-on. It is a thin consumer of
the MCP tools every shell screen exposes — it can browse, search, change settings,
remap controllers, import games, update cores, read system info, and launch. It
NEVER sits in the gameplay hot loop. Build it AFTER its tools exist (so it has
real hands), but it IS part of "shell done."

## STOP condition (no-excuse)

The loop stops ONLY when every ❌ row above is ✅ (screen + MCP tool + tests) and
the assistant can drive them. Until then there is always shell work — never idle,
never pivot to game content.
