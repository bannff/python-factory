"""RetroArch configuration IO — reads and writes layered config for games.

Extracted from navigator.py (bead pacz8). Owns ALL RetroArch config
resolution and persistence. Depends inward only (uses arcade_config brick).
"""

from __future__ import annotations

from pathlib import Path

from .config_service import (
    save_game_overrides,
    load_game_overrides,
    save_core_option,
    load_core_options,
    save_input_remap,
    load_input_remaps,
)
from .controls_vm import ControlsVM, controls_from_settings
from .core_options_vm import CoreOptionsVM, core_options_vm_from_options
from .input_remap_vm import InputRemapVM, input_remap_vm_from_remaps
from .models import GameTile


class RetroArchConfig:
    """Encapsulates all RetroArch config IO (reads + writes).

    Injected with concrete paths at construction — no os.environ reads.
    """

    def __init__(self, *, media_root: Path, config_dir: Path) -> None:
        self._media_root = media_root
        self._config_dir = config_dir

    @property
    def media_root(self) -> Path:
        return self._media_root

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    # ------------------------------------------------------------------
    # Core resolution (single source of truth)
    # ------------------------------------------------------------------

    def resolve_core_for_game(self, game: GameTile) -> str:
        """Resolve core name from emulators.cfg for a game's system."""
        cfg_root = self._media_root / "retroarch_cfg"
        system = game.system.lower() if game.system else ""
        if not system:
            return ""
        emu_path = cfg_root / system / "emulators.cfg"
        if not emu_path.exists():
            return ""
        for line in emu_path.read_text(errors="replace").splitlines():
            if line.startswith("default"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"')
        return ""

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def resolve_controls_vm(self, game: GameTile) -> ControlsVM | None:
        """Resolve real RetroArch settings from layered configs on disk.

        Merges per-game overrides on top of base resolved settings so the VM
        reflects any toggles the user has set.
        """
        from factory.arcade_config.interface import parse_cfg, resolve_runtime_settings

        cfg_root = self._media_root / "retroarch_cfg"
        global_cfg_path = cfg_root / "all" / "retroarch.cfg"
        if not global_cfg_path.exists():
            return None

        global_cfg = parse_cfg(global_cfg_path.read_text(errors="replace"))

        system = game.system.lower() if game.system else ""
        system_cfg: dict[str, str] = {}
        if system:
            system_cfg_path = cfg_root / system / "retroarch.cfg"
            if system_cfg_path.exists():
                system_cfg = parse_cfg(system_cfg_path.read_text(errors="replace"))

        core = self.resolve_core_for_game(game)

        # Merge per-game overrides from retroarch_overrides/
        override_base = self._media_root / "retroarch_overrides"
        game_overrides = load_game_overrides(game.id, core, base_dir=override_base) if core else {}

        # Apply game overrides on top of system cfg (higher precedence)
        merged_system = {**system_cfg, **game_overrides}

        settings = resolve_runtime_settings(global_cfg, merged_system, core=core)
        return controls_from_settings(settings)

    def resolve_core_options_vm(self, game: GameTile) -> CoreOptionsVM | None:
        """Resolve core options from disk .opt file + schema registry."""
        from factory.arcade_config.interface import parse_cfg, build_core_options, CORE_OPTION_SCHEMAS

        core = self.resolve_core_for_game(game)
        if not core:
            return None

        # Load the .opt file (same key="value" format, reuses parse_cfg)
        opt_path = self._media_root / "retroarch_cfg" / game.system.lower() / f"{core}.opt"
        raw_opts: dict[str, str] = {}
        if opt_path.exists():
            raw_opts = parse_cfg(opt_path.read_text(errors="replace"))

        # Merge per-game .opt overrides written by us
        override_base = self._media_root / "retroarch_overrides"
        game_opt_overrides = load_core_options(game.id, core, base_dir=override_base)
        raw_opts = {**raw_opts, **game_opt_overrides}

        # Look up curated schema
        schema = CORE_OPTION_SCHEMAS.get(core, {})
        if not schema and not raw_opts:
            return None

        curated, uncurated = build_core_options(raw_opts, schema)
        return core_options_vm_from_options(curated, uncurated, schema=schema)

    def resolve_input_remap_vm(self, game: GameTile) -> InputRemapVM | None:
        """Resolve input remaps from disk .rmp file + per-game overrides."""
        from factory.arcade_config.interface import parse_cfg, build_input_remaps

        core = self.resolve_core_for_game(game)
        if not core:
            return None

        # Load base system .rmp (if any)
        cfg_root = self._media_root / "retroarch_cfg"
        system = game.system.lower() if game.system else ""
        rmp_path = cfg_root / system / f"{core}.rmp"
        raw_rmp: dict[str, str] = {}
        if rmp_path.exists():
            raw_rmp = parse_cfg(rmp_path.read_text(errors="replace"))

        # Merge per-game .rmp overrides written by us
        override_base = self._media_root / "retroarch_overrides"
        game_rmp_overrides = load_input_remaps(game.id, core, base_dir=override_base)
        raw_rmp = {**raw_rmp, **game_rmp_overrides}

        remaps = build_input_remaps(raw_rmp)
        return input_remap_vm_from_remaps(remaps)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def write_game_override(self, game: GameTile, key: str, value: str) -> None:
        """Write a single key into the per-game override file (merge-safe)."""
        override_base = self._media_root / "retroarch_overrides"
        core = self.resolve_core_for_game(game)
        if not core:
            return
        save_game_overrides(game.id, core, {key: value}, base_dir=override_base)

    def write_core_option(self, game: GameTile, key: str, value: str) -> None:
        """Write a single core option to the per-game .opt override file."""
        override_base = self._media_root / "retroarch_overrides"
        core = self.resolve_core_for_game(game)
        if not core:
            return
        save_core_option(game.id, core, key, value, base_dir=override_base)

    def write_input_remap(self, game: GameTile, button: str, target: str) -> None:
        """Write a single input remap to the per-game .rmp override file."""
        override_base = self._media_root / "retroarch_overrides"
        core = self.resolve_core_for_game(game)
        if not core:
            return
        save_input_remap(game.id, core, button, target, base_dir=override_base)
