# OpenArcade — Session Handoff (fresh-agent onboarding)

**Last updated:** 2026-06-29 · **Branch:** `feat/openarcade-build` (work uncommitted)
**Read this first if you are a fresh agent picking up OpenArcade on a new machine.**

---

## BLUF

OpenArcade is a **beautiful, agent-drivable wrapper on top of RetroArch — NOT a
reimplementation**. Reskin what RetroArch already has in Flutter (Flet); expose
every module over MCP so an agent drives it; beat Polycade on animation/attract +
the agent control plane. The UI + library + real-config-read + MCP control plane
are **built and verified**. The ONE remaining unproven piece is the **NCI launch
handoff**, which needs a ~30-min human spike on a Mac with RetroArch installed
(instructions below). Until that spike passes, `launch_game` stays a stub.

Full thesis + Templating Law: `/Users/wdaniero/workplace/openarcade/north_star.md`.

---

## Where we are (built + verified this session, all on `feat/openarcade-build`, uncommitted)

| # | Cycle | Status | Notes |
|---|-------|--------|-------|
| 1 | Templated Tile | ✅ | Uniform bounded cells; art cover-fills via shared `_bounded_art_region` primitive (Templating Law). |
| 2 | Templated Detail | ✅ | Hero reuses the same primitive; real gamelist metadata; duplicated boxart removed. |
| 3 | Video-snap attract | ✅ | Detail hero autoplays the game `.mp4` snap via `flet_video.Video` (gated to hero by `allow_video`; tiles stay image-only). |
| 4 | Real RetroArch controls | ✅ | Controls tab shows REAL config (Run-Ahead, Shader, Smoothing, Core) + "Open RetroArch Menu" handoff. No fakes/"Coming soon". |
| 5 | MCP control plane (READ) | ✅ | `list_games` / `search_games` / `get_game` / `get_controls`. |
| 6 | MCP "tune" write | ✅ | `set_runahead` writes a per-game `.cfg` override. |

**Tests:** 241 green (wall + control_plane + arcade_config). Self-verified via the
screenshot harness + real-data smoke tests.

### Your 4 original screenshot complaints — all addressed
1. Tiles unbounded → bounded uniform template ✅
2. Detail duplicated art / no motion → video-snap hero, no dup ✅
3. Controls tab hollow → real RetroArch values + RGUI handoff ✅
4. Metadata "Coming soon" → real Players/Genre/Dev/Pub/Release/Rating ✅

---

## Architecture you must respect

- **THESIS:** wrapper over RetroArch, not a rebuild. Never reimplement RGUI; surface
  RetroArch's REAL values or hand off to its menu. Never fake "Coming soon".
- **TEMPLATING LAW:** everything is a template parameterized by data. Art auto-fills a
  fixed bounded box (cover-fit + clip). ONE Tile template, ONE Detail template, ONE
  Settings-row template. If a surface isn't a reusable template, it's wrong.
- **Two agent layers:**
  - *Layer 1 — MCP control plane (BUILT):* `control_plane/server.py` `build_server()`
    exposes the tools as a FastMCP **stdio** server; ANY external agent can drive it.
  - *Layer 2 — embedded in-app assistant (v2, NOT built):* the optional management-plane
    agent (library curation + NL game discovery; NEVER in the gameplay hot loop). It is
    just another client of the same Layer-1 tools — no rework needed.
- **Lean-env rule:** the wall app must NOT import fastmcp. `flet-video` and `fastmcp`
  are optional extras. `import wall.app` must work without them.

### Key paths
- Project: `/Users/wdaniero/workplace/python-factory-openarcade/projects/openarcade`
- UI: `wall/components.py` (`_bounded_art_region`, `controls_panel`), `wall/app.py`,
  `wall/navigator.py` (IO edge that reads RetroArch cfg)
- Data: `wall/gamelist_source.py` (gamelist parse + selective loader), `wall/library_query.py`
- Settings domain: `components/arcade_config/.../runtime/settings.py`
  (`resolve_runtime_settings`), `serializers.py` (`parse_cfg`), `wall/config_service.py`
  (`save_runahead` writer)
- MCP: `control_plane/server.py` (5 tools)
- Self-verify harness: `tools/shoot.py` (venv arm64 Playwright; the MCP browser
  x64/Rosetta crashes on Apple Silicon — do not use it)
- tasks.md = full per-cycle decision log.

### How to run / verify
```bash
cd /Users/wdaniero/workplace/python-factory-openarcade/projects/openarcade
# tests (set PYTHONPATH to project + each component src, as run.sh does)
PYTHONPATH=".:../../components/curator/src:../../components/ui/src:../../components/launch/src:../../components/library/src:../../components/arcade_config/src:../../components/state/src" \
  ./.venv/bin/python -m pytest wall control_plane ../../components/arcade_config -q
# native desktop app
./run.sh
# web mode + screenshot (gamelist mode uses the pulled Pi media at /tmp/oa_arcade)
./run_web.sh   # serves 127.0.0.1 web mode
./.venv/bin/python tools/shoot.py http://127.0.0.1:8560/ /tmp/oa.png 9000
```

### Media / arcade source (SELECTIVE — never bulk-mirror)
- Pi `playbox4` 192.168.86.120 (pi / PlayBox), RetroPie. Gamelists + scraped media
  (boxart ~1.2GB, snaps ~8.4GB). **Pull only the few games we show, on demand.**
- Local working set already pulled: `/tmp/oa_arcade` (gamelists 6.2M, ~30 SNES covers,
  1 snap, the real `retroarch_cfg/` files). On a fresh machine these may be absent —
  fixtures mode still works; re-pull selectively if you need real media.
- SSH: `tools/arcade_master.exp` opens a passwordless ControlMaster socket.

---

## THE NCI SPIKE (the one blocker — human, ~30 min on a Mac)

**Why:** to launch a game OpenArcade starts RetroArch with a core+ROM and must know it
actually came up. NCI (RetroArch **Network Control Interface**, UDP port 55355) is
**fire-and-forget — no ACK**. We must prove cold-launch + `GET_STATUS` readiness
detection works before building `launch_game` for real.

**Three questions to answer:**
1. Does launching `retroarch -L core.so rom` + polling `GET_STATUS` over UDP reliably
   report `PLAYING` once the game is up?
2. How long until it's ready (so the UI knows when to hide its "launching…" state)?
3. Does the handoff feel seamless or janky?

**Steps:**
1. Install RetroArch: `brew install retroarch` (or the .dmg). Download one free core
   (Online Updater → e.g. Snes9x/Nestopia) + one homebrew/free ROM.
2. Enable NCI in `retroarch.cfg`:
   ```
   network_cmd_enable = "true"
   network_cmd_port = "55355"
   ```
3. Launch RetroArch, then confirm the port answers:
   ```bash
   echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 55355
   ```
   Expect a status line (e.g. `GET_STATUS PLAYING <core>,<game>,...` or `CONTENTLESS`).
4. Test the cold-launch path — kill RetroArch, then:
   ```bash
   retroarch -L /path/to/core.dylib /path/to/rom &
   # poll until PLAYING, timing how long it takes:
   for i in $(seq 1 50); do
     echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 55355
     sleep 0.2
   done
   ```
   Record: does it reach `PLAYING`? after how long (~ms)? any dropped/no-reply polls?

**Go/no-go:** if cold-launch + GET_STATUS readiness works → `launch_game` design is
unblocked, build it for real (poll `GET_STATUS` until `PLAYING`, then hide the
launching state). If UDP polling is flaky → we learn it cheaply here, not on the cabinet.

(There's a `spike/` dir in the project — a ready-to-run `nci_probe.sh` can be added there;
ask the agent to write it if not present.)

---

## What's left after NCI

- **`launch_game`** MCP tool + UI "Play" wiring (unblocked once spike passes).
- Backlog polish (all unblocked, low-priority): interactive run-ahead UI toggle
  (writer exists, just not UI-wired), on-demand single-snap fetch on detail open,
  per-game `.rmp` remap display, pull a few more systems' media selectively.
- **Commit the worktree** — 6 cycles uncommitted on `feat/openarcade-build`; review
  and land per the team's grouping.

## Loop notes for a fresh agent
- The autonomous goal loop's GOAL lives at `.goal-loop/GOAL.md` (NOTE: `.goal-loop/`
  may be git-excluded, so it might not travel — this HANDOFF.md is the durable record).
- No commits/push/STOP file from inside the loop — the human controls those.
- Subagent completion events were dropping in the prior session → always disk-verify
  (grep + test run + screenshot) after spawning, never trust event-based completion alone.
