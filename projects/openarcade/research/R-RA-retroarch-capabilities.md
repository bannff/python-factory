# R-RA — RetroArch Capability Catalog (Honest-Data Rule for Settings)

**Status:** Research complete · primary-sourced against docs.libretro.com (RetroArch 1.21 docs, fetched 2026-06-29)
**Purpose:** Define exactly what RetroArch *actually* exposes as configurable so OpenArcade's
Controls tab + future Settings UI surface only **real** capabilities — never invented toggles.
**Scope gate:** This is the honest-data rule applied to settings. If RetroArch can't honor it, OpenArcade
must not show it as a live control.

---

## BLUF

RetroArch is configurable along **three distinct seams**, and they are NOT interchangeable:

1. **(a) Live over NCI (UDP 55355)** — the seam OpenArcade already uses for launch.
   NCI is overwhelmingly **hotkey-equivalent toggles + a small set of action commands**.
   You can *toggle/cycle* features and *load a shader by path*, but you **cannot set an arbitrary
   config value to a specific number** (there is no `SET_CONFIG_PARAM`; `GET_CONFIG_PARAM` is
   read-only and limited to a fixed whitelist of mostly directory paths).
   [NCI](https://docs.libretro.com/development/retroarch/network-control-interface/)

2. **(b) Config / override / remap / preset files written at or before launch** — this is the
   **real settings seam**. Core options (`.opt` / `retroarch-core-options.cfg`), config overrides
   (`.cfg` per core/dir/game), input remaps (`.rmp` per core/dir/game), and shader presets
   (`.slangp`/`.glslp`/`.cgp`) are all plain-text files with a documented precedence hierarchy.
   They are loaded when content launches. OpenArcade should **write these files before sending the
   NCI launch command.**
   [Overrides](https://docs.libretro.com/guides/overrides/)

3. **(c) Not cleanly programmatically controllable** — enumerating a core's available options over
   NCI, setting an absolute audio volume, or pushing a live numeric config change to a running
   instance. These require either driving the menu blindly (`MENU_*` button commands) or are simply
   not exposed. Treat as **"Coming soon"** in v1.

**Recommended architecture:** a small **control-plane brick** that (1) reads/writes RetroArch's
`.cfg`/`.opt`/`.rmp`/preset files on disk and (2) uses NCI only for live toggles + launch + shader
load. The launcher writes the desired config files, *then* launches. This matches how every serious
RetroArch frontend (Lakka, EmulationStation, Batocera) operates.

---

## 1. Network Control Interface (NCI) — what's drivable live

NCI is a **UDP** interface (default port `55355`), enabled with `network_cmd_enable = "true"` /
`network_cmd_port = "55355"` in `retroarch.cfg`. Commands are plain UDP datagrams — sendable via
`retroarch --command "CMD;HOST;PORT"` or raw `nc -u`. Some commands return a UDP response to the
sender.
[NCI](https://docs.libretro.com/development/retroarch/network-control-interface/)

### Action commands (accept args / return data)

| Command | Args | Returns | Relevance to settings |
|---|---|---|---|
| `VERSION` | none | version string | Capability detection (e.g. `1.21.0`) |
| `GET_STATUS` | none | `PAUSED\|PLAYING system_id,game_basename,crc32=…` or `CONTENTLESS` | **Launch-handoff confirmation** (the missing ACK for the NCI fire-and-forget risk) |
| `GET_CONFIG_PARAM` | `<param>` | `<param> <value>` | **Read-only, whitelist only** — see below |
| `SHOW_MSG` | `<text>` | — | OSD toast (e.g. "OpenArcade: launching…") |
| `SET_SHADER` | `<shader path>` | — | **Live shader preset load by path** ✅ |
| `LOAD_CORE` | `<core path>` | — | Load a core by path |
| `READ_CORE_MEMORY` / `WRITE_CORE_MEMORY` | addr + bytes | hex / status | Memory access (not a settings concern) |
| `LOAD_STATE_SLOT` / `SAVE_FILES` / `LOAD_FILES` | slot / none | status | Save-state / SRAM management |

**`GET_CONFIG_PARAM` supported parameters (the entire whitelist):**
`video_fullscreen`, `savefile_directory`, `savestate_directory`, `runtime_log_directory`,
`log_dir`, `cache_directory`, `system_directory`, `netplay_nickname`, `active_replay`.
There is **no general config reader and no config writer over NCI.**
[NCI · GET_CONFIG_PARAM](https://docs.libretro.com/development/retroarch/network-control-interface/#get_config_param)

### State/button commands (no args — simulate a hotkey press; mostly toggles)

These trigger the same action as the bound hotkey. Settings-relevant ones:

| Command | Effect | Caveat for a UI |
|---|---|---|
| `RUNAHEAD_TOGGLE` | toggle run-ahead latency reduction | **Toggle only** — can't set frame count live |
| `PREEMPT_TOGGLE` | toggle preemptive frames | Toggle only |
| `VRR_RUNLOOP_TOGGLE` | toggle VRR runloop | Toggle only |
| `SHADER_TOGGLE` / `SHADER_NEXT` / `SHADER_PREV` | enable/cycle shader presets | Cycles through automatic presets; `SET_SHADER` is the targeted version |
| `MUTE` / `VOLUME_UP` / `VOLUME_DOWN` | audio | **No absolute set** — toggle/step only |
| `FAST_FORWARD` / `SLOWMOTION` / `REWIND` | speed | Toggle/hold |
| `FULLSCREEN_TOGGLE` | windowed/fullscreen | Toggle only |
| `FPS_TOGGLE` / `STATISTICS_TOGGLE` | overlays | Toggle only |
| `RESET` / `PAUSE_TOGGLE` / `CLOSE_CONTENT` / `QUIT` | game/run control | Useful for an arcade shell exit flow |
| `MENU_TOGGLE` / `MENU_UP/DOWN/LEFT/RIGHT/A/B` | drive the RGUI menu | **Last-resort** way to reach settings NCI can't set directly — fragile, no state feedback |

**Key NCI takeaway:** live numeric/value settings are not in scope. NCI gives you (1) launch +
handoff confirmation (`GET_STATUS`), (2) live shader load (`SET_SHADER`), (3) a bank of on/off
toggles, and (4) blind menu navigation as an escape hatch. Everything with a *value* (runahead
frames, vsync, core options, remaps) belongs to seam (b).

---

## 2. Core options — per-core configurable behavior

Core options are the per-core knobs under **Quick Menu → Options** (e.g. region, internal
resolution, BIOS toggle). They are persisted as plain text:

- **Global:** `retroarch-core-options.cfg` (next to `retroarch.cfg`), auto-created when a core that
  supports options loads.
- **Per-game:** `/config/<core>/<game>.opt` — created via *Quick Menu → Options → Game-options file*.
  Loaded instead of the global file when present. Requires **"Load Content-Specific Core Options
  Automatically = On."**
- **Options/`.opt` are full configurations** (loaded *instead of* the base, not merged).

[Overrides · Core options](https://docs.libretro.com/guides/overrides/#core-options)

**Programmatic read/set:** by **writing the `.cfg`/`.opt` text files**, not over NCI. The set of valid
options/values per core is defined by the core itself (libretro core-options API); RetroArch does not
expose an NCI enumerator for them. To know the legal values, OpenArcade must read the core's option
definitions (core info / generated `.opt`/`-core-options.cfg`) rather than invent them.
[Core options sample](https://git.libretro.com/libretro/libretro-3dengine/-/tree/master/libretro-common/samples/core_options)

---

## 3. Input remapping — `.rmp` files

Two distinct concepts, **do not conflate them**:

- **RetroPad binds** (Settings → Input → RetroPad Binds): map a *physical* controller/keyboard to the
  virtual RetroPad. This is the hardware-binding layer.
- **Input remaps** (`.rmp`): alter *how the core receives* the RetroPad input (e.g. swap A/B for one
  core) **without** changing menu navigation or the hardware binding. This is the per-core/per-game
  layer a launcher cares about.
[Input & Controls · Remapping](https://docs.libretro.com/guides/input-and-controls/#remapping-controls-for-individual-cores-or-content)

`.rmp` files use the **same precedence as overrides** (game > content-dir > core) and save by default
to `/config/remaps/<core>/` (path set under *Settings → Directory → Input Remapping*).
[Overrides · Input Remaps](https://docs.libretro.com/guides/overrides/#input-remaps)

**Settable without a gamepad library:** yes. `.rmp` is a plain text file describing RetroPad-button →
core-input mapping; OpenArcade can write it directly. Physical-device *autoconfig* (mapping a raw
USB pad to the RetroPad) is a separate database-driven concern and is **not** something to surface as
a v1 setting — on a fixed arcade cabinet the controller is wired once via autoconfig/udev, not
per-game.
[Controller autoconfiguration](https://docs.libretro.com/guides/controller-autoconfiguration/)

> **OpenArcade tie-in:** this confirms the Brook-board player-order work (udev pin by USB port path)
> lives at the OS/autoconfig layer, *not* in a RetroArch per-game `.rmp`. Keep them separate.

---

## 4. Config overrides — `.cfg` precedence

Any global `retroarch.cfg` setting can be overridden per **core**, **content-directory**, or **game**.
Overrides are *lightweight diffs* — they store only settings that differ from the parent.

**Load hierarchy (most specific wins):**
```
retroarch.cfg                                  (defaults)
  └─ <core>.cfg            /config/<core>/<core>.cfg
       └─ <content-dir>.cfg /config/<core>/<content-dir>.cfg
            └─ <game>.cfg    /config/<core>/<game>.cfg
```
Same precedence applies to `.rmp` remaps. Core- and dir-level overrides persist into more specific
loads unless overridden.
[Overrides · Logic](https://docs.libretro.com/guides/overrides/#logic)

**Warning from the docs:** some settings *cannot* be saved to an override from the menu but **can be
added manually to the override file** — which is exactly OpenArcade's write-the-file approach. Once an
override exists, future menu changes must be re-saved via Quick Menu.
[Overrides · Configuration Files](https://docs.libretro.com/guides/overrides/#configuration-files-location)

---

## 5. Shaders — presets + parameters

- **Preset files:** `.slangp` (Slang/Vulkan/glcore), `.glslp` (GLSL/GLES), `.cgp` (Cg, legacy).
- **Automatic presets** save per **Global / Core / Content-Directory / Game** (most specific wins),
  to `/config/<core>/…` or `/config/global.<ext>`. Game/dir presets are also core-specific.
- **Simple Preset** = a `#reference` to a base preset + parameter overrides (inherits upstream
  changes). **Full Preset** = self-contained chain. Editing the *chain* forces a Full Preset; editing
  only *parameters* can stay a Simple Preset.
- **Live load:** `SET_SHADER <path>` over NCI, or `--set-shader "<path>"` at launch (an empty string
  disables automatic presets). Shader *parameters* are exposed as tweakable values previewed live in
  the menu and persisted into the preset file.
[Shaders](https://docs.libretro.com/guides/shaders/) ·
[Shaders · Command Line](https://docs.libretro.com/guides/shaders/#command-line)

**OpenArcade implication:** shaders are the **one rich visual setting that is both file-configurable
AND live-drivable over NCI.** A curated shader picker (CRT/scanline/off) is a realistic v1 feature:
ship a handful of bundled `.slangp` presets and apply via `SET_SHADER`.

---

## 6. Runahead / latency / sync

Exposed RetroArch settings (all live in `retroarch.cfg` / overrides as numeric/bool values):
run-ahead (on/off + frame count + second-instance mode), preemptive frames, frame delay, hard GPU
sync, V-Sync, audio sync. Over **NCI** only the **on/off toggles** exist
(`RUNAHEAD_TOGGLE`, `PREEMPT_TOGGLE`, `VRR_RUNLOOP_TOGGLE`) — **the numeric values (runahead frame
count, frame delay) are config-file only.**
[NCI · Performance](https://docs.libretro.com/development/retroarch/network-control-interface/#performance)

**Safe to expose in v1?** A simple **"Reduce latency (Run-Ahead)" on/off** is safe (file-set the frame
count to a conservative default, toggle live via NCI). Fine-grained frame-delay/vsync tuning is
**expert/footgun territory** — defer or hide behind an advanced flag. Run-ahead is also
**core-dependent** (cores using internal threading can break) — version/core-dependent, so don't
present it as universally available.

---

## Capability table

| Setting | Scope | How set | Safe to expose in OpenArcade v1? |
|---|---|---|---|
| Launch content (core + ROM) | game | `LOAD_CORE` + content, or CLI `-L <core> <rom>` | **Y** — already used |
| Launch handoff confirmation | — | `GET_STATUS` over NCI | **Y** — closes the fire-and-forget ACK gap |
| Shader preset (CRT/scanline/off) | global/core/dir/game | `.slangp`/`.glslp` file **+** live `SET_SHADER`/`--set-shader` | **Y** — curated picker, bundled presets |
| Shader on/off toggle | live | `SHADER_TOGGLE` NCI | **Y** |
| Core options (region, resolution, BIOS, etc.) | global/game | `retroarch-core-options.cfg` / `<game>.opt` file | **Y (read-from-core only)** — never invent option values; surface only what the core declares |
| Input remap (swap buttons per game) | core/dir/game | `.rmp` file in `/config/remaps/<core>/` | **Y** — write file; arcade-relevant for button layouts |
| Config override (any `retroarch.cfg` key) | core/dir/game | `<core\|dir\|game>.cfg` file | **Y (curated subset)** — expose only chosen keys, not the raw cfg |
| Run-Ahead (reduce latency) | global/override | file sets frame count; `RUNAHEAD_TOGGLE` live | **Y as on/off** — conservative default, core-dependent caveat |
| Aspect ratio / integer scale | global/override | `.cfg` override file | **Y (curated)** |
| Audio mute / volume | live | `MUTE` / `VOLUME_UP/DOWN` NCI | **Partial** — toggle/step only, no absolute slider |
| Fullscreen | live + file | `FULLSCREEN_TOGGLE` NCI / `video_fullscreen` cfg | **Y** (kiosk is fullscreen anyway) |
| Frame delay / hard-sync / vsync numeric tuning | global/override | `.cfg` file only | **N (v1)** — footgun; defer to advanced |
| Set arbitrary config value live to a number | — | **No `SET_CONFIG_PARAM` exists** | **N** — not possible; write file + relaunch |
| Enumerate a core's option list over NCI | — | **Not exposed over NCI** | **N** — read core info / `.opt` instead |
| Absolute audio volume slider | — | not in NCI; cfg `audio_volume` + relaunch | **N (v1)** — only stepping is live |
| Physical controller → RetroPad autoconfig | hardware | autoconfig DB / udev (OS layer) | **N (v1)** — wired once at cabinet setup, not a per-game UI |

---

## OpenArcade Controls / Settings UI implications

**Real for v1 (build these tabs/sections):**
- **Display → Shader picker.** Curated bundled presets (Off / CRT / Scanlines / …). File-set the
  automatic preset *and* apply live via `SET_SHADER`. The only rich visual setting that is both
  file-configurable and live-drivable — highest ROI.
- **Controls → Per-game button remap.** Write `.rmp` to `/config/remaps/<core>/`. Maps RetroPad
  buttons to core inputs. Genuinely useful for arcade layouts (e.g. 6-button fighters).
- **Core options (read-only-driven).** Render the options the loaded core *declares* (parsed from its
  `.opt`/`-core-options.cfg`), let the user pick among the core's legal values, write the `.opt`.
  **Never hardcode option names/values** — different cores expose different options.
- **Performance → "Reduce latency (Run-Ahead)" on/off.** Conservative file default + live
  `RUNAHEAD_TOGGLE`. Label the core-dependent caveat.
- **Display → Aspect/scale (curated subset of cfg keys).**

**Must stay "Coming soon" / hidden in v1:**
- Absolute audio volume slider (NCI only steps/mutes).
- Fine-grained frame-delay / vsync / hard-GPU-sync numeric tuning (footgun, version-dependent).
- Live numeric config edits to a running game (no `SET_CONFIG_PARAM`; requires relaunch).
- Physical controller autoconfig / player-order (OS/udev layer at cabinet setup, not per-game UI).

**Recommended seam — an OpenArcade "RetroArch control-plane" brick:**
1. **File writer/reader** for `retroarch.cfg`, `<scope>.cfg` overrides, `<game>.opt` core options,
   `.rmp` remaps, and shader presets — honoring the documented precedence (game > dir > core > global)
   and writing to the documented `/config/<core>/…` and `/config/remaps/<core>/` paths.
2. **NCI client** (already exists for launch) for: `GET_STATUS` (handoff ACK), `SET_SHADER`,
   `SHOW_MSG`, and the live toggles. Reuse `components/hardware` patterns.
3. **Order of operations:** write the desired config/remap/preset/option files → send NCI launch →
   poll `GET_STATUS` to confirm content actually loaded (this also helps the Phase-1 fire-and-forget
   handoff spike). Live, post-launch tweaks are limited to the toggle set + `SET_SHADER`.

This keeps OpenArcade **honest**: every control in the UI maps to either a real config file RetroArch
reads on launch or a real NCI command — nothing invented.

---

## Uncertainties / version notes (stated, not guessed)

- NCI command set above is from the **RetroArch 1.21-era docs** (page footer March 2026). Older builds
  (e.g. shipping on a Batocera image) may lack newer commands — **gate features on `VERSION`** at
  runtime rather than assuming. [NCI](https://docs.libretro.com/development/retroarch/network-control-interface/)
- `--set-shader` and `-L` launch flags are documented on the Shaders/CLI pages; other launch flags
  (`--config`, `--appendconfig`) are standard RetroArch but were **not deep-verified in this pass** —
  confirm against the [CLI guide](https://docs.libretro.com/guides/cli-intro/) before relying on exact
  flag semantics. The file-write-then-launch approach does not depend on them.
- Run-ahead viability is **core-dependent** (per RetroArch's own guidance); don't present it as
  universally safe.
- Exact `.opt`/`.rmp`/`.cfg` line formats are plain text but **not formally specified** in the user
  docs — derive the format from a live RetroArch-generated file during the Phase-1 spike rather than
  hand-authoring blind.

---

### Sources (all primary, docs.libretro.com unless noted)
- Network Control Interface — https://docs.libretro.com/development/retroarch/network-control-interface/
- Overrides (cfg/rmp/opt precedence + paths) — https://docs.libretro.com/guides/overrides/
- Shaders (presets, parameters, `--set-shader`) — https://docs.libretro.com/guides/shaders/
- Input and Controls (RetroPad, remap vs bind) — https://docs.libretro.com/guides/input-and-controls/
- Controller Auto-Configuration — https://docs.libretro.com/guides/controller-autoconfiguration/
- CLI Introduction — https://docs.libretro.com/guides/cli-intro/
- Core options sample (libretro core-options API) — https://git.libretro.com/libretro/libretro-3dengine/-/tree/master/libretro-common/samples/core_options
