---
inclusion: always
---
# OpenArcade — Mission (read FIRST, every agent, every task)

This file is the contract. Global skills (engineering-excellence, minimalist-ui-
design, test-strategy, secure-coding, systematic-debugging) still apply — this
SUPERSEDES them on any conflict about *what OpenArcade is*.

## The two over-arching goals (front and center)

1. **A beautiful, animated UI on top of RetroArch** — prettier and more alive
   than Polycade. We are a WRAPPER, not a re-implementation. Flutter (Flet)
   motion: hover/focus, hero transitions, attract video. We surface RetroArch's
   REAL capabilities (or hand off to its menu) — we never rebuild RGUI.

2. **An in-app agentic assistant** — built with agentic best practices
   (knowledge base + skills + memory) that helps the user **troubleshoot, add
   games, map controllers, find/launch games, manage cores/systems**. It is a
   thin consumer of OpenArcade's own MCP control plane. It NEVER sits in the
   gameplay hot loop.

Both goals are equal and permanent. A feature that serves neither does not ship.

## The laws (non-negotiable)

- **Wrap, don't rebuild.** RetroArch already does add-games (Import Content),
  core/asset downloads (Online Updater), controller remap (Input), stability/
  system info (Information). OpenArcade exposes these as beautiful templated
  screens that DRIVE RetroArch (config/CLI/NCI) or HAND OFF to RGUI. Never
  reimplement an emulator/launcher concern RetroArch owns.
- **MCP-first.** Every capability is a tool on the MCP control plane FIRST, then
  the UI and the assistant are both thin consumers of those same tools. If a new
  screen has no MCP tool behind it, the design is wrong.
- **Templated / agnostic / polymorphic.** Everything is a template parameterized
  by data, applicable to ANY game/system/core. One Tile template, one Detail
  template, one Settings-row template, one capability-screen template. No
  per-game or per-system special-casing in the UI.
- **No fake surfaces.** No "Coming soon" rows, no dead buttons, no placeholder
  that does nothing. Absent data → honest empty/`--`; unbuilt feature → hide it.
- **Real values or honest handoff.** Show RetroArch's actual resolved config, or
  link to the menu that owns it. Never invent values.

## Capability surface the skeleton must cover (templated, MCP-backed)

Library ✓ · Systems · Settings · **Add Games (import/scan)** · **Controller
Mapping (real remap, not display-only)** · **Cores/Updater management** ·
**Information/stability** · **Assistant panel**. Build the skeleton for ALL of
these (reusable capability-screen template + MCP tools) BEFORE polishing
"play one game." A playable game with no controller config / no add-games / no
assistant is not the product.

## Gate checklist (meta-architect MUST apply, reject if any fail)

- [ ] Serves goal #1 (beauty/wrapper) or #2 (agentic assistant) — name which.
- [ ] Wraps RetroArch / hands off — does NOT reimplement an RGUI concern.
- [ ] Has (or adds) an MCP tool behind it; UI/assistant consume the same tool.
- [ ] Templated/agnostic — no per-game/per-system special-casing.
- [ ] No fake/placeholder surface; honest empty states.
- [ ] Framework-first, SRP, illegal-states-unrepresentable (engineering-excellence).
- [ ] Visual work: headless verifies structure only; flagged for real-display confirm.

## Reference
North Star: /Users/wdaniero/workplace/openarcade/north_star.md (thesis of record).
Architecture: projects/openarcade/ARCHITECTURE.md. Loop: projects/openarcade/LOOP.md.
