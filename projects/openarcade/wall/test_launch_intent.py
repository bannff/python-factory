"""Tests for wall.launch_intent — pure argument extraction."""

import pytest

from wall.launch_intent import launch_args
from wall.models import GameTile


def _tile(*, playable=True, rom_path="/roms/sf2.sfc", core="snes9x"):
    return GameTile(id="snes-sf2", title="SF2", system="SNES", art_url="",
                    playable=playable, rom_path=rom_path, core=core)


def test_launch_args_returns_path_and_core():
    path, core = launch_args(_tile())
    assert path == "/roms/sf2.sfc"
    assert core == "snes9x"


def test_launch_args_core_none_when_absent():
    path, core = launch_args(_tile(core=None))
    assert path == "/roms/sf2.sfc"
    assert core is None


def test_launch_args_raises_for_non_playable():
    with pytest.raises(ValueError, match="non-playable"):
        launch_args(_tile(playable=False))


def test_launch_args_raises_for_empty_rom_path():
    with pytest.raises(ValueError, match="non-playable"):
        launch_args(_tile(rom_path=""))


def test_launch_args_raises_for_relative_rom_path():
    """Invariant: rom_path must be absolute for playable tiles."""
    with pytest.raises(ValueError, match="must be absolute"):
        launch_args(_tile(rom_path="./Foo.sfc"))
