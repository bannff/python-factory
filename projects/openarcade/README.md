# OpenArcade

A free, beautiful, agent-native UI for retro and arcade games. Renders a game-wall
frontend via the python-factory `ui` brick (Flet/Flutter adapter), wrapping
RetroArch/MAME through the Network Control Interface. The AI assistant handles
library curation, compatibility scanning, and natural-language game discovery —
management-plane only, never in the gameplay hot loop.

## Status — Phase 1 scaffold complete

A sibling Polylith project inside `python-factory`, consuming generic bricks
(`ui`+Flet adapter, `evals`) and adding arcade-specific control-plane bricks.
The launch path is proven against a mock NCI socket; real-hardware launch QA is
the human's, on the laptop.

## Architecture

Control-plane bricks live in `python-factory/components/` (namespace `factory.*`);
app-level code lives here in `projects/openarcade/`.

| Brick / module | Responsibility |
|---|---|
| `factory.launch` | NCI transport seam (`NciTransport` protocol, UDP + mock + loopback) and the launch handoff state machine. NCI is fire-and-forget UDP (no ack), so readiness is modeled via an injectable probe. |
| `factory.library` | Game/ROM catalog model (`Game`) and scanner interface. |
| `factory.arcade_config` | Arcade configuration (named `arcade_config`, not `config`, to avoid the `factory.config` namespace collision). |
| `factory.state` | Immutable session state + pure menu↔game transitions. |
| `factory.curator` | AI-assistant control plane (management-plane only): ROM/CHD ingest (`scan_rom_directory` → `RomCandidate`) + compatibility scan (`check_compatibility` → `CompatReport`). `assess_playability` is an explicit Phase-3 stub. |
| `wall/` (app module) | Game-wall view-model → `UIView` mapper, rendered to an `ft.GridView` through the `ui` brick's `FletAdapter`. |
| `spike/` (app module) | Instrumented NCI handoff spike — drives the launch sequence against a mock UDP socket and timestamps every transition (for the human's black-frame/audio-pop/focus-fight observation). |

## Running tests

Tests run in the lean venv with the brick `src` dirs on `PYTHONPATH`:

```bash
# from the python-factory worktree root
VIRTUAL_ENV= PYTHONPATH="components/curator/src:components/launch/src:components/library/src:components/arcade_config/src:components/state/src:components/ui/src" \
  .venv/bin/python -m pytest \
  components/{launch,library,arcade_config,state,curator}/test -q
```

The Flet wall tests live alongside the app module:

```bash
cd projects/openarcade && \
  VIRTUAL_ENV= PYTHONPATH="$(pwd):$(pwd)/../../components/ui/src" \
  .venv/bin/python -m pytest wall -q
```

## Running the NCI handoff spike

```bash
./spike/run.sh                  # mock UDP loopback (no hardware)
./spike/run.sh --real HOST:PORT # live RetroArch — the human go/no-go
```

## Lean-env note

OpenArcade runs on lean deps (`flet`, `pydantic`, `structlog`, `typer`, `pyyaml`).
Import bricks via their concrete runtime modules
(e.g. `factory.ui.runtime.adapters.flet_adapter`), **not** `factory.ui.interface`
— the MCP-surface modules pull `fastmcp`, which is not in the lean dependency set.

## Parked (human / hardware)

- Real-hardware NCI handoff go/no-go (laptop + RetroArch).
- Brook Neo-Arcade player-order udev validation (needs the board).
