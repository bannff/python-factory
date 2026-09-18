# OpenArcade — Open Issues (loop-native backlog)

This is the source of truth for the goal loop + sub-agent team. The loop reads this
each cycle alongside `north_star.md` and `tasks.md`. Beads is NOT used (its `bd`
mutations fail to sync past protected `main`). Status: OPEN / IN-PROGRESS / DONE.
`parallel-safe` = can be built concurrently with other parallel-safe issues (different
files, no shared seam) — spawn these as simultaneous implementers.

> North-star check on every issue: we WRAP RetroArch (reskin + surface its real values
> or hand off), never reimplement RGUI. Templated, MCP-exposable, framework-first.

---

## OA-1 — Tile/hero art is stretched/distorted  [OPEN] [parallel-safe] [P0]
**Problem:** Box art is visibly distorted on a real display (not just cropped). Headless
screenshots verified the box is *bounded* but missed aspect distortion → false confidence.
**Root-cause candidates to check:** the art `fit` on the tile vs hero, and the cell
aspect ratio (`_bounded_art_region` cover-filling a too-tall portrait cell). Confirm the
`ft.Image` uses `fit="cover"` (preserve aspect, crop) — NOT `fill` — and that the cell
aspect matches box-art ratio (~0.7 w/h for SNES) so cover crops minimally.
**Acceptance:** box art renders undistorted at correct aspect in a **non-headless**
capture (real window or `flet-web` on the display machine); tile + detail hero both correct.
**Files:** `wall/components.py` (`_bounded_art_region`), `wall/theme.py` (cell/aspect tokens).
**Verify:** must be eyeballed on a real display — headless is insufficient for this class.

## OA-2 — Only games with a local snap animate  [OPEN] [parallel-safe] [P1]
**Problem:** Only Super Baseball animates; others fall back to static art because only one
`.mp4` was pulled locally (selective/no-mirror rule). Intended behavior is every opened
game animates.
**Fix:** on-demand single-snap fetch — when a detail opens, `scp` that ONE game's snap from
playbox4 into `MEDIA_ROOT/{system}/snap/` if absent, then play it. Never bulk-mirror.
Async/background so it never blocks the UI; show art until the snap lands.
**Acceptance:** open any game → its snap auto-fetches once and plays in the hero; second open
is instant (cached); no full-library pull; UI never blocks on the fetch.
**Files:** new `wall/snap_fetch.py` (injected transport, fake in tests), `wall/navigator.py`
detail-open hook. Reuse the `tools/arcade_master.exp` ControlMaster socket.

## OA-3 — Controls must SHOW RetroArch's real settings (not a handoff link)  [OPEN] [P0]
**Problem:** Controls tab shows 4 read-only values + an "Open RetroArch Menu" link — it's
*less* than RetroArch. User wants what RetroArch shows, rendered nicer **and editable**.
**Fix:** surface the real settings as editable Settings-row templates: per-core **core
options** (read the core's `.opt` + the option list), **input remap** (per-game `.rmp`),
**shader** preset picker, run-ahead, smoothing — write back via the existing
`arcade_config` writer (`save_runahead`/`write_config`/`.rmp` serializer). Keep the
"Open RetroArch Menu" affordance ONLY as a last-resort for the deep long-tail, not the
whole tab. Each editable setting is also an MCP tool (pillar #2).
**Acceptance:** Controls shows real core options + remap + shader for the game, editable,
persisted to the correct override `.cfg/.opt/.rmp`; verified by reading the file back.
**Files:** `wall/controls_vm.py`, `wall/components.py` (`controls_panel`),
`components/arcade_config/...` (option-list read), `control_plane/server.py` (expose as tools).

## OA-4 — No sidebar / no depth — add navigation + the real app surface  [OPEN] [P0]
**Problem:** No left nav; the app is a wall + a thin detail. It shows *less* than RetroArch,
so there's no reason to use it. Needs the surfaces that make it nicer AND more.
**Fix (templated, incremental):** persistent left sidebar — Systems, Search, Collections/
Favorites, Settings. Wire the existing MCP `search_games` to a real search box. A global
Settings surface (global RetroArch config via the same editable Settings-row template as OA-3).
**Acceptance:** sidebar nav switches systems, search filters the wall live, Settings surface
edits global config; all token-driven/templated; screenshot-verified on a real display.
**Files:** `wall/app.py` (nav shell), `wall/components.py` (sidebar + search), reuse
`library_query` + `arcade_config`.

## OA-5 — launch_game (make it actually playable)  [BLOCKED: NCI spike] [P0-value]
**Problem:** Can't launch a game → the app is a catalog, not a front-end. This is the single
biggest "why would I use it" gap.
**Blocked on:** the human NCI spike in `HANDOFF.md` / `spike/` — prove cold-launch
`retroarch -L core rom` + `GET_STATUS` UDP readiness on a Mac. Scaffolding exists
(`components/launch/runtime/nci/{udp,ports,status,status_probe}.py`).
**Fix after spike:** implement `launch_game` (launch + poll GET_STATUS → PLAYING → hide
"launching" state), wire the detail "Play" button + an MCP `launch_game` tool.
**Acceptance:** clicking Play (and the MCP tool) launches the game and the UI reflects ready.

## OA-6 — Backlog / lower priority  [OPEN]
- Per-game `.rmp` remap display for systems that have them (arcade/N64).
- Pull more systems' media selectively (NES/Genesis/N64) for a fuller wall.
- Rive feasibility spike in Flet (richer attract animation) — non-blocking.
- Embedded management-plane assistant (v2): NL search/curation as an in-app client of the
  MCP tools (Layer 2 — never in the gameplay hot loop).

---

## How to run this loop FAST (operating model)
1. **Run on the machine with a DISPLAY.** Headless screenshots missed OA-1's distortion;
   real visual QA is mandatory for UI issues. The agent on the code+display machine verifies
   for real, not headless.
2. **Parallelize.** OA-1, OA-2, OA-3, OA-4 are largely independent (`parallel-safe`) — spawn
   them as simultaneous implementers, don't serialize one-per-cycle.
3. **Batch-gate the punch-list once** (meta-architect approves all four seams together)
   instead of gating each cycle — removes the per-cycle stall.
4. **One branch, accumulate commits**, human lands when ready. No per-issue branches.
5. Update this file's statuses + `tasks.md` as the decision log.
