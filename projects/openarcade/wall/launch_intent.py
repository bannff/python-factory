"""Pure extraction of launch arguments from a GameTile. No I/O."""

import os
from .models import GameTile


def launch_args(game: GameTile) -> tuple[str, str | None]:
    """(content_path, core) for the launch orchestrator. Pure.

    Invariant: rom_path must be absolute and non-empty for playable tiles.
    Raises ValueError if the invariant is violated.
    """
    if not game.playable or not game.rom_path:
        raise ValueError(f"Cannot launch non-playable tile: {game.id}")
    if not os.path.isabs(game.rom_path):
        raise ValueError(
            f"rom_path must be absolute for playable tile {game.id}: {game.rom_path!r}"
        )
    return (game.rom_path, game.core)
