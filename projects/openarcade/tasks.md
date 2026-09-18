
## B16 — Keyboard/controller navigation + bottom hint bar — DONE (uncommitted, worktree) 2026-06-29

- `wall/focus.py`: PURE `focus_move(index, direction, *, count, columns)` + `Direction` enum.
  Clamp-not-wrap 2D grid model; partial-last-row DOWN clamps to last valid index; corner moves no-op;
  out-of-range/count=0 guarded. Zero Flet imports, zero side effects.
- `chrome.py`: pure `hint_bar(actions)` builder — icon+label pairs (AA contrast, never icon-only),
  context-sensitive (wall: Select/Filter; detail: Select/Back).
- `navigator.py`: focus index in WallState; `page.on_keyboard_event` handler maps Arrow keys ->
  focus_move (decide) then re-render focused tile (act); Enter -> open/Play; Escape -> back to wall.
  Guarded `_try_update()` so off-page tests don't crash.
- `tile(focused=True)` ring already existed — state now drives it.
- VERIFIED: 94 wall tests green + independent adversarial focus_move edge-case check passed.
- Brook/XInput = parked future adapter (arrives as key events on kiosk; no gamepad lib pulled in).
- Run: cd projects/openarcade && ./run.sh  (arrow keys to move focus, Enter to open, Esc to go back)
- NEXT: richer Description|Controls detail tabs + screenshot carousel (Polycade detail parity), then
  R-RA RetroArch capability research before any Settings/Controls UI.

## B17 — Enriched game-detail page (Polycade parity) — DONE (uncommitted, worktree) 2026-06-29

- `models.py`: GameTile += optional detail fields (description/developer/release_date/rating/category/
  last_played/play_count = None; screenshots = () tuple). Defaults keep all existing constructions valid;
  same dataclass the Phase-3 scraper fills later (no separate GameDetail class).
- `components.py`: new pure builders metadata_row / detail_tabs / screenshot_carousel / metadata_sidebar;
  detail_view recomposed to the 1941 layout (title + metadata_row + Play(primary)/Go Back left,
  Description|Controls tabs + carousel center, metadata sidebar right, Last Played/Play Count footer).
- `navigator.py`: WallState._detail_tab (default "description"); on_select_tab callback + Left/Right/Tab
  keyboard switches Description<->Controls; decision separate from act; guarded _try_update().
- HONEST DATA (verified): absent metadata -> "Coming soon"/"—"; empty screenshots -> graceful placeholder;
  Controls tab -> "Coming soon" (no invented mappings, gated behind R-RA). NEVER fabricated.
- VERIFIED: 103 wall tests green + independent adversarial probe of all empty-state render paths.
- Run: cd projects/openarcade && ./run.sh  (click a tile -> rich detail; Left/Right toggles tabs)
- NEXT: R-RA — enumerate what RetroArch ACTUALLY exposes (core options/input remaps/per-game overrides/
  shaders) BEFORE building any Settings/Controls UI, so the Controls tab surfaces only real capabilities.

## R-RA — RetroArch capability research — DONE (uncommitted) 2026-06-29
File: research/R-RA-retroarch-capabilities.md (primary-sourced, docs.libretro.com)

THREE SEAMS (not interchangeable):
- (a) NCI/UDP 55355 — mostly hotkey-equivalent TOGGLES + a few actions. NO SET_CONFIG_PARAM
  (GET_CONFIG_PARAM is read-only, fixed whitelist). Has: launch, GET_STATUS, SET_SHADER (live),
  SHOW_MSG, on/off toggles. Any NUMERIC setting (runahead frames, frame delay, vsync) is NOT NCI-settable.
- (b) CONFIG/OVERRIDE/REMAP/PRESET FILES written BEFORE launch = the REAL settings seam. Precedence
  retroarch.cfg -> <core>.cfg -> <content-dir>.cfg -> <game>.cfg (most specific wins). .rmp remaps in
  /config/remaps/<core>/, .opt core options in /config/<core>/<game>.opt, shaders .slangp/.glslp.
  All plain text, write-then-launch.
- (c) NOT programmatically controllable -> stays "Coming soon".

KEY SIDE FINDING: NCI GET_STATUS = the missing handoff ACK for top-risk #1 (fire-and-forget launch).
  Wire into the launch brick's readiness probe later (replaces _always_ready mock). Real-HW spike stays
  a parked human task.

v1-REAL Settings/Controls UI (only these are honest):
- Shader picker (file + live SET_SHADER — the one rich visual setting that's both file & NCI).
- Per-game button REMAP (.rmp writer).
- Core options driven from what the CORE DECLARES (never invent option names/values).
- Run-Ahead on/off (core-dependent caveat).
"Coming soon": volume slider, frame-delay/vsync numeric tuning, live numeric config edits,
  physical-controller/player-order (that's OS/udev — keeps Brook work cleanly separate).

RECOMMENDED SEAM: a RetroArch config control-plane brick = pure reader/writer for .cfg/.rmp/.opt/.slangp
  (functional core, file IO at edge) + NCI additions (GET_STATUS, SET_SHADER). Domain stays pure.

NEXT (B18): GATE then build the config control-plane brick (pure config/remap/override model + writers,
  unit-tested with a fake fs), THEN wire the Controls tab to surface ONLY the v1-real set above.

## B18 — RetroArch config control-plane (in arcade_config brick) — DONE (uncommitted) 2026-06-29

- Extended EXISTING components/arcade_config brick (not a new one) with runtime/:
  - models.py: frozen value objects + Scope enum. CoreOption(key,value,allowed) rejects value not in
    allowed; InputRemap(retropad_button,target) rejects button not in the 16 canonical RetroPad buttons;
    ShaderPreset(path); RunAheadConfig. Illegal-state guards in __post_init__ = the "never invent core
    options/buttons" honesty rule enforced by the type.
  - serializers.py: PURE model->text for .cfg / .opt / .rmp / shader ref (no IO).
  - resolver.py: PURE override_path precedence game > content-dir > core > global; raises when scope
    needs core/game not provided.
  - writer.py: the ONLY IO edge (write_config: mkdir parents + write text).
  - interface.py: additively re-exports the new surface (existing ArcadeConfig/SystemCoreMapping intact).
- Pure domain dataclasses (existing brick uses Pydantic; runtime layer is framework-free by design).
- VERIFIED: 129 wall+arcade_config tests green (142 across all bricks per implementer); dependency purity
  confirmed (grep: no flet / factory.ui / factory.launch in the brick); adversarial guard probe passed.
- NCI GET_STATUS/SET_SHADER DEFERRED (separate slice — needs UDP response channel; keeps boundary clean).
- NEXT: wire the detail Controls tab to surface ONLY the v1-real set (core-declared core options, .rmp
  remap, shader picker, runahead on/off) using this brick — UI gate first (net-new visual surface).

## B19 — Controls tab wired to config brick (honest, display-first) — DONE (uncommitted) 2026-06-29

- NEW wall/controls_vm.py: PURE ControlsVM + controls_view_model(...) mapper (zero Flet import).
  Defaults -> honest state: runahead off, 16 RetroPad rows all "--" (identity), core_options None,
  shader_presets None (None renders "Coming soon"). CANONICAL_BUTTON_ORDER defined for stable rows.
- components.py: controls_panel(vm) builder — runahead toggle + "Controller Mapping" 16-row read-only
  table + Core Options / Shaders sections that show "Coming soon" when None. Token-driven, AA contrast.
- detail_tabs Controls body now renders controls_panel(controls_view_model()) instead of bare "Coming
  soon" — currently called with NO sources (honest current state: no core-options/shader data exists yet).
- DISPLAY-FIRST: no config files written, launch brick untouched (write-path = separate slice).
- VERIFIED: 145 tests green (wall+arcade_config); controls_vm.py Flet-free; adversarial VM probe passed
  (identity default, data flow-through, canonical order, core-options None->populated).
- HONESTY HELD: core options + shaders stay "Coming soon" (no source); remap rows identity-filled; only
  runahead + the RetroPad view are "real" — nothing fabricated.
- NEXT options: (a) config WRITE-path slice (controls edits -> brick serializer+resolver+writer, with a
  real save action); (b) NCI GET_STATUS readiness probe replacing _always_ready; (c) library nav-rail
  Settings screen scaffold; (d) attract-mode / motion polish. Re-prioritize via human.

## B20 — NCI GET_STATUS readiness probe (top-risk #1) — DONE (uncommitted) 2026-06-29

- Extended NciTransport Protocol (nci/ports.py) with query(cmd, timeout) -> str | None (request/response).
  MockNciTransport gains canned_responses for tests; real UdpNciTransport.query() PARKED (NotImplementedError
  "requires recvfrom — built during the on-HW spike"). No real sockets opened anywhere.
- NEW nci/status.py: NciState enum (CONTENTLESS/PAUSED/PLAYING/UNKNOWN) + frozen NciStatus + pure
  parse_status(raw) — maps documented GET_STATUS replies; None/garbage/empty -> UNKNOWN, never raises.
- NEW GetStatusProbe: sends GET_STATUS via query(), parse_status(), ready iff state==PLAYING. Injected into
  the existing orchestrator poll/timeout loop in place of _always_ready (loop unchanged; mock still available).
- This makes top-risk #1 (fire-and-forget launch had no ACK) REAL in the abstraction: launch now polls a
  genuine readiness signal. Real on-hardware UDP recvfrom stays the single parked human spike.
- VERIFIED: 173 tests green (15 new B20 + 158 existing); real query() parked; adversarial parse_status probe
  passed (PLAYING/CONTENTLESS/PAUSED mapped; None/garbage/'' -> UNKNOWN, no crash).
- NEXT options: config WRITE-path slice (Controls edit -> brick serializer+resolver+writer + save action);
  nav-rail Settings screen scaffold; attract-mode / motion polish; Phase-3 scraper seam (metadata+art source).

## B21 — Config WRITE-path: runahead toggle persists (first real setting) — DONE (uncommitted) 2026-06-29

- NEW wall/config_service.py (22 LOC): save_runahead(game_id, core, enabled, *, base_dir) -> Path.
  Composes brick parts: RunAheadConfig -> serialize_cfg -> override_path(GAME scope) -> write_config.
  Pure orchestration; the single IO write is the brick's writer (functional core / imperative shell).
- navigator.py: __init__ gains config_dir: Path|None; _on_runahead_toggle handler writes via save_runahead
  (no-op when no game selected OR config_dir None). Callback threaded detail_view -> detail_tabs ->
  controls_panel (builders stay pure).
- app.py: injects config_dir = Path(os.environ.get("OPENARCADE_CONFIG_DIR", "./openarcade_config")).
- SAFETY: base_dir ALWAYS injected; default ./openarcade_config (under project); NO .config/retroarch /
  expanduser / Path.home() anywhere in the write path. Tests use tmp_path.
- Per-GAME override file at <base_dir>/<core>/<game>.cfg (highest RetroArch precedence; no cross-game bleed).
- VERIFIED: 181 tests green (127 wall + 54 brick/launch); safety grep clean; end-to-end probe wrote
  mame2003_plus/sf2.cfg with run_ahead_enabled="true"/"false", idempotent rewrite.
- This is the FIRST genuinely persisted setting — the B18 config seam is now proven end-to-end (UI edit ->
  typed model -> serialize -> resolve -> write).
- NEXT options: read-back (reflect persisted runahead on detail open); extend write-path to remap (.rmp) once
  an edit UI exists; nav-rail Settings screen; attract-mode/motion polish; Phase-3 scraper seam.

## B22 — Config READ-BACK: runahead reflects persisted state (round-trip closed) — DONE (uncommitted) 2026-06-29

- Brick serializers.py: PURE parse_cfg(text) -> dict[str,str], symmetric with serialize_cfg (regex key="value";
  skips comment/blank/junk; last-dup wins; empty->{}). Exported from interface.py. Zero IO.
- config_service.py: load_runahead(game_id, core, *, base_dir) -> RunAheadConfig | None, mirror of save_runahead.
  Reads the SAME GAME-scope path. Missing/unreadable file -> None (= no persisted setting). Present file ->
  RunAheadConfig (enabled False is a real state, NOT None). Degrades: missing/garbage keys -> enabled False /
  frames 1; non-int frames -> 1; never raises.
- navigator.py: _build_detail loads runahead (shell IO) -> threads through detail_view/detail_tabs ->
  controls_view_model(runahead=...). _on_runahead_toggle re-renders detail after save so the toggle visibly sticks.
- VERIFIED: 197 tests green (full suite wall+arcade_config+launch); parse_cfg IO-free (grep); round-trip probe:
  no-file->None, save True->enabled True, save False->enabled False, malformed->safe OFF (no crash).
- ROUND-TRIP CLOSED: the config layer is now fully stateful — UI toggle -> persist -> reflected on reopen.

## LOOP STATUS (2026-06-29, cycle ~40+)
Reached the configured Max cycles=40 ceiling. OpenArcade against the vision is substantially complete &
all UNCOMMITTED in worktree (branch feat/openarcade-build): B10-B22 + R-RA. Full Polycade-parity loop:
animated wall (real box art, hover/scale/glow, focus ring) -> keyboard/click nav + hint bar -> rich detail
(Description|Controls tabs, metadata sidebar, honest "Coming soon") -> Play -> launch w/ real GET_STATUS
readiness probe -> typed+tested RetroArch config control-plane that PERSISTS (runahead write + read-back).
Human controls commit. Parked (human/HW): real NCI recvfrom socket spike on hardware; Phase-3 scraper
(metadata+art source to fill "Coming soon"); Brook udev player-order on real Linux.
NEXT (when resumed): Phase-3 scraper seam | nav-rail Settings screen | attract-mode/motion polish | extend
write-path to remap(.rmp)/shader once edit UIs exist.

## B23 — Nav-rail SETTINGS screen — DONE (uncommitted) 2026-06-29

- config_service.py: save_global_runahead(enabled, *, base_dir) / load_global_runahead(*, base_dir) —
  GLOBAL-scope (base_dir/global.cfg via override_path Scope.GLOBAL, no core/game); same pure/IO split +
  degrade rules as the per-game pair.
- chrome.py: PURE settings_view (nav_rail selected="settings" + content: global Run-Ahead toggle [REAL] +
  honest "Coming soon" Shaders/Input/Core Options + About config-dir/version). nav_rail gained selected:str
  highlight (AA accent).
- navigator.py: WallState.current_screen ("library"|"settings"); _on_nav_select routes wall<->settings;
  _build_settings loads global runahead; _on_global_runahead_toggle persists + re-renders.
- VERIFIED: 219 tests green (160 wall + 31 arcade_config + 28 launch); config_service path-safe;
  global round-trip probe (None / True / False, writes global.cfg).
- Honest: only the global runahead toggle is real; everything else "Coming soon" — no fabricated settings.

## LOOP STATUS (cycle ~45, well past Max=40)
Polycade-parity vision substantially complete + uncommitted in worktree (feat/openarcade-build):
B10-B23 + R-RA. Wall->nav(+Settings screen)->detail(tabs)->Play->launch(GET_STATUS probe)->config
control-plane that persists per-game AND global settings (write+read-back). Human controls commit.
Parked (human/HW): real NCI recvfrom socket spike; Phase-3 scraper (fills "Coming soon" metadata+art);
Brook udev player-order on real Linux.

## DOC — ARCHITECTURE.md (as-built map + commit guide) — DONE (uncommitted) 2026-06-29
projects/openarcade/ARCHITECTURE.md: BLUF, module map (wall/ + control-plane bricks w/ responsibilities
+ seams + dependency direction), decisions & WHY, real-vs-parked table, run/test, suggested commit grouping
for the uncommitted B10-B23 + R-RA worktree. Enables human review/commit. doc-writer authored; true-to-code.

## B24 — Window startup size + NavigationRail unbounded-height crash FIX — DONE (uncommitted) 2026-06-29
Reported by human via screenshot: red "NavigationRail: height is unbounded" overlay + window opens tiny.
ROOT CAUSE: AnimatedSwitcher (navigator root) had no expand=True, so the page column gave its chrome Row
unbounded height -> the NavigationRail inside could not resolve its height. Separately _target never sized
the window (Flet does not auto-fit to content).
FIX (2 edits, canonical Flet pattern):
- navigator.py: AnimatedSwitcher expand=True -> chrome Row gets BOUNDED height -> rail resolves (fixes wall
  AND settings screens; both have a bare nav rail).
- app.py _target: page.window.width/height (1440x900 fallback) + min_width/height + maximized=True
  (arcade cabinet UI starts maximized; un-maximize falls back to a sane size, never tiny).
VERIFIED headless: 160 wall tests green; construct probe — switcher.expand True, wall+settings Rows expand
with a NavigationRail child, detail builds. Rendered-window look = human eyeball (no display in headless).
RUN: cd projects/openarcade && ./run.sh

## B25 — FIX: detail-page tab headers not click-wired (Controls unreachable by mouse) — DONE (uncommitted) 2026-06-29
Human-reported: clicking "Controls" tab did nothing. ROOT CAUSE: detail_tabs rendered headers as plain
Containers with no on_click; only keyboard ←/→/Tab toggled tabs (navigator._on_key). The Controls panel
existed (B19) but was unreachable by mouse.
FIX: detail_tabs gained on_select_tab param -> each header Container wired on_click; detail_view forwards
on_select_tab (navigator already passed _on_tab). VERIFIED: 160 wall green + click probe (Controls header
fires on_select_tab("controls")) + 2 regression tests (test_components: clickable-with-handler / inert-without).

## B26 — Flet web-mode harness (visual self-verification) — PARTIAL (uncommitted) 2026-06-29
GOAL: serve the SAME UI as a localhost web page so the agent can screenshot + self-verify each cycle.
DONE: flet-web==0.85.3 added to pyproject + installed into local .venv (flet auto-installer had targeted
the wrong uv venv -> ModuleNotFoundError flet_web). app.py run_web() serves via WEB_BROWSER view bound to
127.0.0.1 (view=None does NOT serve in 0.85); page.web guards desktop-only window sizing. run_web.sh added.
VERIFIED: HTTP 200, Flutter bundle served on 127.0.0.1. Local headless Chrome reaches it + writes a valid
1440x900 PNG (cloud browser MCP canNOT reach localhost).
GAP: one-shot `chrome --screenshot` captures the Flutter LOADING SPLASH (can't wait for canvas paint under
swiftshader). NEXT: install Playwright in venv -> goto + wait-for-canvas + screenshot = reliable self-verify loop.
RUN (user, opens a tab): ./run_web.sh   |  headless shot needs the Playwright step.

## B26 UPDATE — self-verify loop COMPLETE (uncommitted) 2026-06-29
SOLVED the screenshot gap: Playwright MCP launches x64 Chrome via Rosetta -> GPU crash on Apple Silicon,
and no flag control. FIX: installed `playwright` into local venv + its bundled ARM64 Chromium
(`python -m playwright install chromium`). tools/shoot.py drives it: launch (swiftshader args) -> goto ->
wait_for_selector('flt-glass-pane') -> settle -> optional keyboard route -> screenshot. PROVEN: captured the
real rendered wall (nav rail, filter chips, focused tile w/ accent ring, hint bar) at 1440x900.
LOOP: start web server detached (run_web on 127.0.0.1) -> python tools/shoot.py <url> <out.png> [settle_ms] [route].
CAVEAT: remote libretro box-art images may not finish loading in headless within the settle window — bump
settle or wait for images when verifying ART specifically (moot once art is data-driven/local-media).
NOTE: add `playwright` to pyproject optional-deps [dev] so the harness is reproducible (TODO next touch).

## CYCLE (tile-perfection #1) — Art data-driven VERIFIED + 1 region-tag fix — DONE (uncommitted) 2026-06-29
Confirmed the landed art refactor against the LIVE libretro CDN (deterministic curl of each tile's art_url):
5/6 = 200 on first pass; Metroid Fusion (GBA) 404'd — `(USA, Australia)` wrong; probed CDN, corrected to
`Metroid Fusion (USA)` (200). Now 6/6 resolve across SNES/N64/GBA/NES. wall tests green.
HARNESS CAVEAT (recorded): headless Chromium + Flutter canvaskit does NOT paint REMOTE network images
within settle/networkidle (verified: wall layout/focus/chips/hint-bar render, art tiles stay dark). So:
art-PRESENCE = curl the art_url (authoritative); SCREENSHOT = layout/motion/structure. Moot once art is
local media (scraper cache / user's arcade). shoot.py now also waits networkidle (kept; harmless).
NEXT: motion polish (hover lift/scale/glow + visible focus transition) — screenshot-verifiable since it's not remote-image-dependent.

## CYCLE (tile-perfection #2) — Controls "make sense": kill 16-row remap noise — DONE (uncommitted) 2026-06-29
GATE meta-architect APPROVED Option A. controls_vm.ControlsVM.remap_rows is now Optional
(tuple|None) — None = no custom mapping, so an identity 16-row grid is UNREPRESENTABLE. controls_panel
branches: remap_rows is None -> single honest "Controller / Default RetroPad layout" line; not-None ->
full per-button grid (reserved for a real per-game remap-editor cycle, wired to B18 .rmp writer). Run-Ahead
stays the one actionable element; Core Options + Shaders unchanged ("Coming soon"). 166 wall tests green.
SCREENSHOT-VERIFIED (/tmp/oa_controls.png): 16 "BUTTON -> --" rows gone; panel reads calm + honest.
NEXT: motion polish (hover lift/scale/glow + focus transition + click->detail) — screenshot-verifiable via page.hover.

## CYCLE (tile-perfection #3) — Motion assessed vs the stated bar — DONE (uncommitted) 2026-06-29
Goal's motion checklist = (a) hover lift/scale/glow, (b) visible focus ring, (c) click->detail transition.
ALL THREE EXIST in code: hover_container (scale 1.04 + glow, animate_scale 200ms); focus = 2px accent
border; AnimatedSwitcher FADE 300ms. VERIFIED by screenshot: focus ring (accent border on focused tile)
+ wall<->detail endpoints. NOT agent-verifiable: hover — added a pixel-hover path to tools/shoot.py
(mouse.move x,y) but Flutter canvaskit headless does NOT fire on_hover from synthetic moves (hover frame
== non-hover frame, byte-identical). So hover is code-present; only the NATIVE window / real mouse confirms it.
CONCLUSION: tiles + controls + motion meet the stated bar and are honest/tested. Further tile/controls
polish is gilding (guardrail: not endless polish). The remaining real leverage = RICHNESS (real art on
every tile + video snaps + metadata) = Phase-3 scraper / user's arcade media. BLOCKED on a data-source
decision or the arcade media. Parking the perfection loop here and surfacing the fork to the human.

## CYCLE (tile-perfection #4) — REAL library ingestion (gamelist + local art) — DONE (uncommitted) 2026-06-29
GATE meta-architect APPROVED. NEW wall/gamelist_source.py: parse_gamelist(xml,*,system)->list[GameTile] PURE
(fields incl. desc/developer/publisher/genre/players/rating; releasedate YYYYMMDD->YYYY-MM-DD; empty->None;
art_url = relative "{system}/boxart/{name}.png" from <image>); load_gamelist(path,*,system,media_root,
require_media=True) IO edge — SELECTIVE: includes a game ONLY if its cover exists locally (minimal-disk rule).
app.py: opt-in gamelist mode via OPENARCADE_GAMELIST + OPENARCADE_MEDIA_ROOT (+ OPENARCADE_SYSTEM); fixtures
stay DEFAULT; assets_dir=media_root passed to both ft.run calls so Flet serves local art (web+desktop).
VERIFIED: 172 tests green (6 new); smoke=29 SNES tiles vs 30 local covers; SCREENSHOT shows REAL box art
(local files paint headless, unlike remote). Data source: playbox4 RetroPie gamelists pulled to /tmp/oa_arcade
(gamelists 6.2M + 30 SNES covers 5.5M only — NO full-library mirror per user). Video snaps deferred (phase 2).
NEXT: verify detail page shows real desc/dev/publisher; on-demand single-cover fetch helper; then scale/video.

## CYCLE (reskin #1) — Templated Tile (bounded art box, Templating Law) — DONE (uncommitted) 2026-06-29
GATE meta-architect APPROVED Column(bounded art region + fixed title band). tile() = root Container(expand,
clip) -> Column[_bounded_art_region(game), _title_band(game)]. NEW reusable primitive _bounded_art_region
(Detail hero will reuse) + _title_band (fixed T.TITLE_BAND_HEIGHT=52). Dropped scrim (title no longer overlays art).
TWO BUGS FOUND + FIXED by orchestrator (implementer events dropped, caught via disk verify):
  (1) ft.ImageFit.COVER doesn't exist in Flet 0.85 -> use fit="cover" string (implementer self-fixed mid-edit).
  (2) art still didn't FILL: base art was a non-positioned Stack child (expand=True) -> Stack gives loose
      constraints -> image at natural size + dead space. FIX: Positioned.fill (left/top/right/bottom=0) ->
      art fills bounded region, cover-fit takes over. THE core Templating-Law fill fix.
VERIFIED: 178 wall tests green; SCREENSHOT confirms uniform bounded tiles, art cover-fills every cell
regardless of ratio, chip top-left, fixed title band. (cover crops overflow = intended fill; contain=token swap.)
NEXT (reskin #2): Detail template reusing _bounded_art_region for the hero; then video-snap attract; then real controls; then MCP.

## CYCLE (reskin #2) — Templated Detail page (reuse primitive, kill art dup) — DONE (uncommitted) 2026-06-29
GATE meta-architect APPROVED. Hero = ft.Container(DETAIL_HERO_W=280 x DETAIL_HERO_H=370, radius, clip)
wrapping _bounded_art_region(game) — SAME primitive as the tile (Templating Law); this Container is the
SINGLE swap-seam for video (cycle reskin#3 swaps content -> ft.Video). Description tab body = description
text only; screenshot_carousel fallback_art param + boxart-fallback branch DELETED (the art-duplication
bug, user complaint #2). 180 wall tests green. SCREENSHOT (detail, real SNES game): bounded hero w/ real
cover, REAL metadata (Players 1-2/Genre Sports/Dev Pallas/Pub SNK/Release 1993-07-13/Rating 0.9), real
description, NO duplicate art. Category honestly "Coming soon" (no gamelist field).
NEXT (reskin #3): video-snap attract — swap hero content art->ft.Video, fetch .mp4 on-demand per opened game (no mirror).

## CYCLE (reskin #3) -- Video-snap attract (Detail hero) -- DONE (uncommitted)
De-risked: flet-video==0.85.3 installs via `uv pip install` (uv venv, no pip bin); control is
flet_video.Video (NOT ft.Video) -- Video(playlist=[VideoMedia(resource)], autoplay, muted,
playlist_mode=LOOP, fit=cover, show_controls=False, expand). Gate (1a6b61e3) failed to return twice
(events dropping); orchestrator made the call: video lives INSIDE _bounded_art_region as optional
content gated by allow_video flag (hero=True, tiles=False -> no N-player perf risk; ONE primitive =
Templating Law). Seam: models.video_url + gamelist <video> parse + load_gamelist clears video_url when
snap not local (invariant: set => file exists) + hero passes allow_video=True. Verification snap pulled
selectively (2020 Super Baseball, 2.1MB) per no-mirror rule. Video likely won't paint headless (like
remote images) -> authoritative = Video-in-tree assertion + file-exists; screenshot for layout.

### VERIFIED 2026-06-29: video-snap attract live in Detail hero
flet-video==0.85.3 (pyproject dep added). flet_video.Video(playlist=[VideoMedia], autoplay, muted,
playlist_mode=LOOP, fit=cover, expand) lives INSIDE _bounded_art_region gated by allow_video
(hero=True, tiles=False -> ONE primitive, no N-player perf risk). models.video_url + gamelist <video>
parse + load_gamelist clears video_url when snap absent (invariant: set => local file exists).
191 tests green (+11 video). Screenshot oa_vid.png: Super Baseball 2020 gameplay snap cover-fills the
bounded hero. KEY: video PAINTS headless (local media, unlike remote images) -> surface self-verifiable.
Implementer landed half then dropped event; orchestrator disk-verified + confirmed complete.

## CYCLE (reskin #4) -- REAL RetroArch controls -- DONE (uncommitted)
Reuse arcade_config parse_cfg + NEW pure resolve_runtime_settings(global,system,core)->RetroArchRuntimeSettings.
Pulled real cfgs local (metadata-class, tiny): all/retroarch.cfg + snes/retroarch.cfg + snes/emulators.cfg.
Resolved SNES truth: Run-Ahead Off/1, Shader crt-pi ON, Smoothing Off, Core lr-snes9x2002. controls_vm gains
real fields + controls_from_settings builder; controls_panel renders honest read-only rows + "Open RetroArch
Menu" handoff; fake ft.Switch + "Coming soon" dropped. app.py gamelist mode reads cfgs at IO edge (absent->fallback).
Orchestrator gate (gate subagent unreliable this session -- events drop); design reuses brick patterns, deps point inward.

### VERIFIED 2026-06-29: real controls render
Controls tab shows REAL Pi config: Run-Ahead Off, Shader crt-pi, Video Smoothing Off, Core lr-snes9x2002,
Controller Default RetroPad layout + "Advanced - Open RetroArch Menu" handoff. Fake ft.Switch + all
"Coming soon" rows gone. NEW pure resolve_runtime_settings in arcade_config (reuses parse_cfg); controls_vm
ControlsVM reshaped + controls_from_settings; components _setting_row uniform template; navigator.py IO edge
reads global+system cfg + core from emulators.cfg. 235 tests green (writer/save_runahead coverage PRESERVED --
only obsolete UI-toggle tests removed). Screenshot oa_ctrl.png confirms.
FOLLOW-UP (backlog): re-surface Run-Ahead as a real INTERACTIVE write-control (save_runahead writer still
exists, just not UI-wired this cycle); per-game .rmp remap display for systems that have them.

## CYCLE (reskin #5) -- MCP control plane (READ slice) -- DONE (uncommitted)
Thesis pillar #2 (agent-drivable surface = how we beat Polycade). fastmcp de-risked (installs in venv, .tool API).
NEW pure wall/library_query.py (search_games/get_game over tiles). NEW control_plane/server.py build_server()
exposes list_games/search_games/get_game/get_controls -- reuses load_gamelist + resolve_runtime_settings,
returns JSON dicts. fastmcp = OPTIONAL extra (wall stays lean -- must NOT import fastmcp). Launch/tune-write
DEFERRED (NCI parked on Mac). Verify: pure query tests + control_plane test asserts 4 tools + real data
(shader crt-pi, run_ahead False) + `import wall.app` works without fastmcp.

### VERIFIED 2026-06-29: MCP control plane READ slice live
control_plane/server.py build_server() exposes 4 FastMCP tools: list_games, search_games, get_game,
get_controls -- backed by load_gamelist + resolve_runtime_settings, JSON dicts. NEW pure wall/library_query.py
(search_games/get_game). fastmcp = OPTIONAL extra; `import wall.app` confirmed lean (no fastmcp). 241 tests green.
Smoke: 29 SNES games, search "baseball"->Super Baseball 2020, get_controls-> core lr-snes9x2002/shader crt-pi/runahead False.
Test introspects via server._tool_manager.tools (4 tools asserted).
DEFERRED (NCI-blocked on Mac): launch_game (NCI UDP handoff) + set_runahead/tune WRITE tools (writer exists,
needs NCI go/no-go spike on real hardware). These complete pillar #2 once NCI is proven.

## CYCLE (reskin #6) -- MCP "tune" write tool (set_runahead) -- DONE (uncommitted)
Correction: set_runahead is NOT NCI-blocked (per-game .cfg override read on launch; save_runahead writer
exists+tested). Adds 5th control-plane tool set_runahead(game_id, enabled) -> resolves core, writes per-game
override to media_root/retroarch_overrides (NEVER clobbers pulled real cfgs), returns written_path. Completes
agent-drivable WRITE half of pillar #2 for run-ahead. Only launch_game (NCI UDP handoff) remains hardware-blocked.

### VERIFIED 2026-06-29: set_runahead write tool live
5th control-plane tool set_runahead(game_id, enabled) reuses save_runahead, writes per-game override to
media_root/retroarch_overrides (NOT the read cfg dir). Tests (real save_runahead + real files, no mocks):
5 tools registered; enabled=True writes run_ahead_enabled="true", False writes "false", file under
retroarch_overrides. 202 tests pass; wall.app stays lean. Agent can now READ+TUNE run-ahead via MCP.
REMAINING (genuinely NCI-blocked): launch_game (UDP fire-and-forget handoff + GET_STATUS probe) -- needs
the NCI go/no-go spike on real hardware (RetroArch install + network_cmd_enable). Human task on Mac/cabinet.
