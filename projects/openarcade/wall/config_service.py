"""App-level config persistence — composes arcade_config brick parts.

Generic seam: save_game_overrides / save_global_overrides accept arbitrary key-value
overrides and MERGE with existing file content (never clobbers sibling keys).
Existing save_runahead / load_runahead delegate to the generic seam.
"""

from __future__ import annotations

from pathlib import Path

from factory.arcade_config.runtime.models import RunAheadConfig, Scope
from factory.arcade_config.runtime.serializers import parse_cfg, serialize_cfg
from factory.arcade_config.runtime.resolver import override_path
from factory.arcade_config.runtime.writer import write_config


# ---------------------------------------------------------------------------
# Generic seam (meta-architect mandated refactor)
# ---------------------------------------------------------------------------


def _load_existing(path: Path) -> dict[str, str]:
    """Load existing cfg keys from a file, or empty dict if absent/unparseable."""
    try:
        text = path.read_text()
    except OSError:
        return {}
    return parse_cfg(text)


def save_game_overrides(
    game_id: str,
    core: str,
    overrides: dict[str, str],
    *,
    base_dir: Path,
) -> Path:
    """Persist arbitrary per-GAME RetroArch overrides, merging with existing keys.

    Reads the existing override file (if any), merges the new keys on top,
    and writes back. Never clobbers keys not mentioned in `overrides`.
    """
    path = override_path(base_dir, Scope.GAME, core=core, game=game_id, kind="cfg")
    existing = _load_existing(path)
    merged = {**existing, **overrides}
    content = serialize_cfg(merged)
    write_config(path, content)
    return path


def save_global_overrides(
    overrides: dict[str, str],
    *,
    base_dir: Path,
) -> Path:
    """Persist arbitrary GLOBAL RetroArch overrides, merging with existing keys."""
    path = override_path(base_dir, Scope.GLOBAL, kind="cfg")
    existing = _load_existing(path)
    merged = {**existing, **overrides}
    content = serialize_cfg(merged)
    write_config(path, content)
    return path


def load_game_overrides(
    game_id: str,
    core: str,
    *,
    base_dir: Path,
) -> dict[str, str]:
    """Load all persisted per-game override keys, or empty dict if absent."""
    path = override_path(base_dir, Scope.GAME, core=core, game=game_id, kind="cfg")
    return _load_existing(path)


# ---------------------------------------------------------------------------
# Specialised runahead API (delegates to generic seam — preserves MCP callers)
# ---------------------------------------------------------------------------


def save_runahead(game_id: str, core: str, enabled: bool, *, base_dir: Path) -> Path:
    """Persist runahead on/off as a per-GAME RetroArch override .cfg."""
    cfg = RunAheadConfig(enabled=enabled, frames=1)
    overrides = {
        "run_ahead_enabled": "true" if cfg.enabled else "false",
        "run_ahead_frames": str(cfg.frames),
    }
    return save_game_overrides(game_id, core, overrides, base_dir=base_dir)


def load_runahead(game_id: str, core: str, *, base_dir: Path) -> RunAheadConfig | None:
    """Load persisted runahead config. None = no persisted setting."""
    path = override_path(base_dir, Scope.GAME, core=core, game=game_id, kind="cfg")
    try:
        text = path.read_text()
    except OSError:
        return None
    pairs = parse_cfg(text)
    enabled = pairs.get("run_ahead_enabled", "false") == "true"
    try:
        frames = int(pairs.get("run_ahead_frames", "1"))
    except (ValueError, TypeError):
        frames = 1
    return RunAheadConfig(enabled=enabled, frames=frames)


# --- Global scope (settings screen) ---


def save_global_runahead(enabled: bool, *, base_dir: Path) -> Path:
    """Persist runahead on/off as a GLOBAL RetroArch override .cfg."""
    cfg = RunAheadConfig(enabled=enabled, frames=1)
    overrides = {
        "run_ahead_enabled": "true" if cfg.enabled else "false",
        "run_ahead_frames": str(cfg.frames),
    }
    return save_global_overrides(overrides, base_dir=base_dir)


def load_global_runahead(*, base_dir: Path) -> RunAheadConfig | None:
    """Load global runahead config. None = no persisted setting."""
    path = override_path(base_dir, Scope.GLOBAL, kind="cfg")
    try:
        text = path.read_text()
    except OSError:
        return None
    pairs = parse_cfg(text)
    enabled = pairs.get("run_ahead_enabled", "false") == "true"
    try:
        frames = int(pairs.get("run_ahead_frames", "1"))
    except (ValueError, TypeError):
        frames = 1
    return RunAheadConfig(enabled=enabled, frames=frames)


# ---------------------------------------------------------------------------
# Core Options persistence (dge52)
# ---------------------------------------------------------------------------


def save_core_option(
    game_id: str,
    core: str,
    key: str,
    value: str,
    *,
    base_dir: Path,
) -> Path:
    """Persist a single core option override to a per-GAME .opt file.

    Uses read-merge-write: loads existing .opt (if any), sets the key, writes back.
    Never clobbers sibling keys.
    """
    path = override_path(base_dir, Scope.GAME, core=core, game=game_id, kind="opt")
    existing = _load_existing(path)
    merged = {**existing, key: value}
    content = serialize_cfg(merged)
    write_config(path, content)
    return path


def load_core_options(
    game_id: str,
    core: str,
    *,
    base_dir: Path,
) -> dict[str, str]:
    """Load all persisted per-game core option overrides, or empty dict."""
    path = override_path(base_dir, Scope.GAME, core=core, game=game_id, kind="opt")
    return _load_existing(path)


# ---------------------------------------------------------------------------
# Input Remap persistence (febou)
# ---------------------------------------------------------------------------


def save_input_remap(
    game_id: str,
    core: str,
    button: str,
    target: str,
    *,
    base_dir: Path,
) -> Path:
    """Persist a single input remap to a per-GAME .rmp override file.

    SPARSE: if target == button (identity mapping), REMOVE that key from the file
    (identity is the natural default — never write it). Otherwise write
    ``input_player1_<button> = "<target>"``.

    Uses read-merge-write: loads existing .rmp, applies the change, writes back.
    Never clobbers sibling remap keys.
    """
    path = override_path(base_dir, Scope.GAME, core=core, game=game_id, kind="rmp")
    existing = _load_existing(path)

    rmp_key = f"input_player1_{button}"

    if target == button:
        # Identity — remove the key if present (sparse)
        existing.pop(rmp_key, None)
    else:
        existing[rmp_key] = target

    if existing:
        content = serialize_cfg(existing)
        write_config(path, content)
    else:
        # All keys removed — delete file if it exists
        try:
            path.unlink()
        except OSError:
            pass
    return path


def load_input_remaps(
    game_id: str,
    core: str,
    *,
    base_dir: Path,
) -> dict[str, str]:
    """Load all persisted per-game .rmp override keys, or empty dict."""
    path = override_path(base_dir, Scope.GAME, core=core, game=game_id, kind="rmp")
    return _load_existing(path)
