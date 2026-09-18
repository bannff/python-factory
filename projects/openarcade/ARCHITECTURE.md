# OpenArcade — Architecture (as-built)

## BLUF

OpenArcade is a free, open arcade-cabinet UI for retro games — the polish of
Polycade's launcher atop RetroArch/MAME, but unlocked and not tied to proprietary
software. As of this worktree state it delivers a **complete Flet-native game wall
with keyboard navigation, animated detail pages, a working Play→launch pipeline
with NCI GET_STATUS readiness probing, and a per-game + global config
persistence layer** (runahead write/read-back proven end-to-end). The entire B10–B23
body of work sits **uncommitted on branch `feat/openarcade-build`** — the human
controls commit.

---

## Module Map

### UI shell — `projects/openarcade/wall/`

| File | Responsibility | Key seam |
|------|----------------|----------|
| `app.py` | Entry point — wires Navigator + fixture tree + config dir | `ft.run()`, injects `config_dir` from env |
| `models.py` | `GameTile` dataclass (frozen, optional detail fields) | Shared value object — domain + UI |
| `components.py` | Pure Flet builders (tile, detail_view, metadata_row, tabs, carousel, controls_panel, etc.) | Zero IO; token-driven; return `ft.Control` |
| `navigator.py` | Imperative shell — page state machine (`library`/`detail`/`settings`), keyboard dispatch, callbacks | The single IO boundary inside wall/ |
| `chrome.py` | Pure builders for nav rail, filter bar, A-Z index, hint bar, settings view | AA contrast, never icon-only |
| `filters.py` | Pure `filter_tiles(tiles, query, active_filters)` | No imports outside stdlib |
| `focus.py` | Pure `focus_move(index, direction, *, count, columns)` + `Direction` enum | Clamp-not-wrap 2D grid |
| `controls_vm.py` | Pure `ControlsVM` + `controls_view_model()` mapper | Zero Flet; 16-button canonical order |
| `config_service.py` | Thin orchestrator for config read/write (save/load runahead, per-game + global) | Composes brick parts; single IO call to writer |
| `launch_intent.py` | Pure guard: validates a tile has enough data to launch | Returns typed `LaunchArgs` or `None` |
| `art_resolver.py` | Resolves game title+system → libretro-thumbnails URL | Graceful fallback to procedural placeholder |
| `curator_bridge.py` | Bridges `factory.curator` scan results → `GameTile` list | Adapter at the edge |
| `fixtures.py` | Generates synthetic ROM/cores/BIOS tree for dev/test | `tempfile`-based; no real ROMs |
| `theme.py` | Design tokens (colors, spacing, radius, font sizes) | Single import for all builders |

### Control-plane bricks (Polylith `components/`)

| Brick | Responsibility | Key seam |
|-------|----------------|----------|
| `arcade_config` | RetroArch config value objects + serializers + resolver + writer | `runtime/models.py` = frozen VOs with illegal-state guards; `writer.py` = only IO edge; `serializers.py` = pure text↔model |
| `launch` | NCI transport + orchestrator + GET_STATUS probe | `runtime/nci/ports.py` = `NciTransport` Protocol; `status.py` = pure parse; `status_probe.py` = `GetStatusProbe` (polls readiness); `mock.py` + `udp.py` (parked) |
| `curator` | ROM library scanner (pre-existing) | Consumed read-only via `curator_bridge.py` |

### Dependency direction

```
domain (arcade_config, launch, curator)
         ↑ never imports ↓
wall/ UI shell (components, navigator, chrome…)
         ↑ builders pure; navigator = imperative shell
app.py (entry point, DI wiring)
```

Domain bricks are framework-free (no Flet, no UI imports). UI builders are pure
functions returning controls — no IO, no network. `navigator.py` is the single
imperative shell: state transitions + page mutations + IO callbacks.

### Test coverage

**219 tests** across the three areas (160 wall + 31 arcade_config + 28 launch) —
all pure-function property checks, view-model probes, and integration paths.
Run: `cd projects/openarcade && .venv/bin/python -m pytest wall/ -q`

---

## Key Decisions & WHY

| Decision | Rationale |
|----------|-----------|
| **Flet (Python-driven Flutter) — locked** | Reuses python-factory's polymorphic `ui` brick adapter; single language for control-plane + UI; native desktop window (no Electron); DECISIONS §7 final, never re-litigated. |
| **Wrap RetroArch via NCI — not fork** | RetroArch is 500K+ LOC; we can't out-build it. Every serious frontend (Lakka, EmulationStation, Batocera) wraps it. NCI gives launch + live toggles; config files give everything else. |
| **Honesty rule** | Real data or "Coming soon" — never fabricated metadata, invented core options, or placeholder controls. Enforced by type guards (`CoreOption` rejects values not in `allowed`; `InputRemap` rejects unknown RetroPad buttons). |
| **Config writes = override files, base_dir always injected** | RetroArch's documented override precedence (global → core → content-dir → game .cfg) is the native seam. We write files *before* launch. `base_dir` defaults to `./openarcade_config` (never `~/.config/retroarch`) with `OPENARCADE_CONFIG_DIR` env override. Zero `expanduser`/`Path.home()` in write paths. |
| **GET_STATUS probe = launch readiness ACK** | NCI launch is fire-and-forget UDP (no response). Top risk was "did it start?" `GetStatusProbe` polls `GET_STATUS` — ready iff `PLAYING`. Closes the abstraction gap; real UDP `recvfrom` is the single parked hardware spike. |
| **Local-first library** | MAME XML + No-Intro/Redump DATs for ROM metadata; libretro-thumbnails CDN for box art. No external API dependency for core functionality. ScreenScraper supplement only. |

---

## Real vs. Parked

| Status | Capability | Notes |
|--------|-----------|-------|
| ✅ REAL | Animated game wall (hover lift/glow, focus ring, box art via libretro-thumbnails) | B10–B14 |
| ✅ REAL | Keyboard/click navigation, A-Z jump, hint bar | B15–B16 |
| ✅ REAL | Rich detail page (Description \| Controls tabs, metadata sidebar, carousel) | B17 |
| ✅ REAL | Play → launch with mock NCI + GET_STATUS readiness probe | B20 |
| ✅ REAL | Per-game runahead toggle: persist + read-back (config round-trip proven) | B21–B22 |
| ✅ REAL | Global runahead via Settings nav-rail screen | B23 |
| ✅ REAL | Controls tab: 16-row RetroPad view (identity-mapped, read-only) | B19 |
| 🅿️ PARKED | Real NCI UDP `recvfrom` socket (needs hardware spike on real RetroArch) | Abstraction built; `UdpNciTransport.query()` = NotImplementedError |
| 🅿️ PARKED | Phase-3 scraper (metadata + art source to fill all "Coming soon" fields) | Models ready (`GameTile` optional fields); source = MAME XML + DATs + ScreenScraper |
| 🅿️ PARKED | Brook udev player-order on real Linux | OS-level (`udev` pin by USB port path); out-of-scope until hardware available |
| 🅿️ PARKED | Core options / shader picker / input remap editing | Config brick supports it; UI gated on Phase-3 (need real core-declared data) |

---

## How to Run

```bash
cd projects/openarcade && ./run.sh
```

Requires `flet-desktop==0.85.3` in the project `.venv`. Arrow keys navigate, Enter
opens/plays, Escape goes back, Tab toggles detail tabs.

**Config dir:** override with `OPENARCADE_CONFIG_DIR=/path/to/dir` (default
`./openarcade_config`). RetroArch override files are written here.

**Tests:**

```bash
cd projects/openarcade
.venv/bin/python -m pytest wall/ -q                          # 160 wall tests
.venv/bin/python -m pytest ../../components/arcade_config/ -q # 31 brick tests
.venv/bin/python -m pytest ../../components/launch/ -q        # 28 launch tests
```

---

## Suggested Commit Grouping

Each commit should be coherent and tests should pass at that point. Recommended
sequence over the uncommitted files:

| # | Scope | Files (approx) | Rationale |
|---|-------|-----------------|-----------|
| **a** | Component system + renderer (B10–B14) | `wall/{models,components,flet_wall,theme,fixtures,curator_bridge,art_resolver}.py` + tests | Foundation: data model, pure builders, Flet renderer, fixture tree |
| **b** | Library chrome (B15) | `wall/chrome.py` + `test_chrome.py` | Nav rail, filter bar, A-Z index, hint bar |
| **c** | Keyboard nav + focus (B16) | `wall/{focus,navigator}.py` + `test_focus.py`, `test_navigator.py` | Pure focus model + imperative shell wiring |
| **d** | Rich detail tabs (B17) | `wall/components.py` (detail additions), `wall/models.py` (optional fields) | Polycade-parity detail page |
| **e** | R-RA research doc | `research/R-RA-retroarch-capabilities.md` | Decision record — no code |
| **f** | arcade_config control-plane (B18) | `components/arcade_config/src/.../runtime/{models,serializers,resolver,writer}.py` + `interface.py` + test | Pure config domain + single IO edge |
| **g** | Controls tab + VM (B19) | `wall/{controls_vm,config_service}.py` + `test_controls_vm.py` | Display-first, wired to config brick |
| **h** | GET_STATUS probe (B20) | `components/launch/src/.../nci/{ports,status,status_probe}.py` + test | Closes top-risk #1 in abstraction |
| **i** | Config write + read-back (B21–B22) | `wall/config_service.py` (save/load), `components/arcade_config/.../serializers.py` (parse_cfg) + tests | Round-trip proven end-to-end |
| **j** | Settings screen (B23) | `wall/{chrome,navigator}.py` (settings additions), `test_settings.py` | Global runahead + nav-rail routing |
| **k** | Launch intent guard | `wall/launch_intent.py` + `test_launch_intent.py` | Pure validation for Play action |
| **l** | tasks.md + ARCHITECTURE.md | This file + task log | Meta — the doc layer |

Adjust grouping to taste. The key constraint: **a** must land first (everything
depends on models + components), and **f** before **g** (Controls tab imports the
config brick).
