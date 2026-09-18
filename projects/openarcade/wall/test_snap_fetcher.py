"""Tests for on-demand snap fetch (bead 7ymw2).

Behavior-named AAA tests. Mocks only at the SnapFetcher boundary — no internals.
"""

from __future__ import annotations

import asyncio
import shlex
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wall.models import GameTile, WallViewModel
from wall.gamelist_source import parse_gamelist, load_gamelist
from wall.snap_fetcher import ScpSnapFetcher, FakeSnapFetcher, SnapFetcher
from wall.navigator import Navigator, WallState


# --- Helpers ---

def _tile(
    title="Test",
    system="SNES",
    video_url="",
    expected_snap_path="",
    rom_path="./test.sfc",
):
    return GameTile(
        id=f"{system.lower()}-{title.lower()}",
        title=title,
        system=system,
        art_url="snes/boxart/test.png",
        video_url=video_url,
        expected_snap_path=expected_snap_path,
        rom_path=rom_path,
    )


# --- gamelist_source: expected_snap_path ---

_XML_WITH_VIDEO = """\
<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Super Metroid (USA).sfc</path>
    <name>Super Metroid</name>
    <image>./boxart/Super Metroid (USA).png</image>
    <video>./snap/Super Metroid.mp4</video>
  </game>
</gameList>
"""

_XML_NO_VIDEO = """\
<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Foo.sfc</path>
    <name>Foo</name>
    <image>./boxart/Foo.png</image>
  </game>
</gameList>
"""


def test_load_gamelist_sets_expected_snap_path_even_when_snap_absent(tmp_path: Path):
    """expected_snap_path is set from XML <video> even when local file doesn't exist."""
    gl = tmp_path / "gamelist.xml"
    gl.write_text(_XML_WITH_VIDEO)
    art_dir = tmp_path / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "Super Metroid (USA).png").write_bytes(b"\x89PNG")
    # Do NOT create snap file

    # Create roms_root with the ROM file
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "Super Metroid (USA).sfc").write_bytes(b"\x00")

    tiles = load_gamelist(gl, system="snes", media_root=tmp_path, roms_root=roms_dir, require_media=True)
    assert len(tiles) == 1
    assert tiles[0].video_url == ""  # cleared (file absent)
    assert tiles[0].expected_snap_path == "snes/snap/Super Metroid.mp4"  # always set


def test_expected_snap_path_empty_when_xml_has_no_video():
    """No <video> element -> expected_snap_path is empty."""
    tiles = parse_gamelist(_XML_NO_VIDEO, system="snes")
    assert tiles[0].expected_snap_path == ""


def test_expected_snap_path_set_when_snap_present(tmp_path: Path):
    """expected_snap_path matches video_url when snap file exists locally."""
    gl = tmp_path / "gamelist.xml"
    gl.write_text(_XML_WITH_VIDEO)
    art_dir = tmp_path / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "Super Metroid (USA).png").write_bytes(b"\x89PNG")
    snap_dir = tmp_path / "snes" / "snap"
    snap_dir.mkdir(parents=True)
    (snap_dir / "Super Metroid.mp4").write_bytes(b"\x00\x00\x00\x1cftyp")

    # Create roms_root with the ROM file
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "Super Metroid (USA).sfc").write_bytes(b"\x00")

    tiles = load_gamelist(gl, system="snes", media_root=tmp_path, roms_root=roms_dir, require_media=True)
    assert tiles[0].video_url == "snes/snap/Super Metroid.mp4"
    assert tiles[0].expected_snap_path == "snes/snap/Super Metroid.mp4"


# --- ScpSnapFetcher: correct argv ---

@pytest.mark.asyncio
async def test_scp_fetcher_builds_correct_argv(tmp_path: Path):
    """ScpSnapFetcher invokes scp with the right remote path and local dest."""
    fetcher = ScpSnapFetcher(host="10.0.0.1", remote_base="/roms", user="testuser")
    dest = tmp_path / "snes" / "snap" / "game.mp4"

    captured_args: list[tuple] = []

    async def _fake_exec(*args, **kwargs):
        captured_args.append(args)
        proc = MagicMock()
        proc.returncode = 0
        proc.wait = AsyncMock(return_value=0)
        # Simulate file creation (scp would do this)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"data")
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = await fetcher.fetch("snes/snap/game.mp4", dest)

    assert result is True
    assert len(captured_args) == 1
    argv = captured_args[0]
    assert argv[0] == "scp"
    assert "testuser@10.0.0.1:/roms/snes/snap/game.mp4" in argv
    assert str(dest) in argv


@pytest.mark.asyncio
async def test_scp_fetcher_shell_quotes_remote_path_with_spaces(tmp_path: Path):
    """Remote paths with spaces/parens (No-Intro names) must be shell-quoted so
    the Pi's shell does not split them. Regression for the 28/29-games-fail bug."""
    fetcher = ScpSnapFetcher(host="10.0.0.1", remote_base="~/roms", user="pi")
    dest = tmp_path / "out.mp4"
    rel = "snes/snap/90 Minutes - European Prime Goal (Europe).mp4"

    captured_args: list[tuple] = []

    async def _fake_exec(*args, **kwargs):
        captured_args.append(args)
        proc = MagicMock()
        proc.returncode = 0
        proc.wait = AsyncMock(return_value=0)
        dest.write_bytes(b"data")
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        result = await fetcher.fetch(rel, dest)

    assert result is True
    argv = captured_args[0]
    remote_arg = next(a for a in argv if isinstance(a, str) and a.startswith("pi@10.0.0.1:"))
    # remote_base ~ stays outside quotes (so it expands); the spaced path is quoted as ONE token
    assert remote_arg == "pi@10.0.0.1:~/roms/" + shlex.quote(rel)
    # the whole relative path (with spaces/parens) is a single shell-quoted token
    assert remote_arg.endswith("'snes/snap/90 Minutes - European Prime Goal (Europe).mp4'")


@pytest.mark.asyncio
async def test_scp_fetcher_returns_false_on_nonzero_exit(tmp_path: Path):
    """ScpSnapFetcher returns False when scp exits non-zero."""
    fetcher = ScpSnapFetcher()
    dest = tmp_path / "out.mp4"

    async def _fail_exec(*args, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.wait = AsyncMock(return_value=1)
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fail_exec):
        result = await fetcher.fetch("snes/snap/x.mp4", dest)

    assert result is False
    assert not dest.exists()


# --- Navigator: detail-open triggers fetch ---

@pytest.mark.asyncio
async def test_detail_open_triggers_fetch_when_no_video_but_snap_path(tmp_path: Path):
    """Opening detail for a game without local video triggers snap fetch."""
    game = _tile(expected_snap_path="snes/snap/test.mp4")
    vm = WallViewModel(tiles=[game], columns=2)
    fetcher = FakeSnapFetcher(succeed=True)

    page = MagicMock(spec=["on_keyboard_event", "run_task"])
    tasks: list = []
    page.run_task = lambda coro, *a: tasks.append((coro, a))

    nav = Navigator(vm, page, snap_fetcher=fetcher, media_root=tmp_path)
    nav.select(game)

    # run_task should have been called with _do_snap_fetch
    fetch_tasks = [(c, a) for c, a in tasks if c == nav._do_snap_fetch]
    assert len(fetch_tasks) == 1
    assert fetch_tasks[0][1] == (game,)


@pytest.mark.asyncio
async def test_detail_open_does_not_fetch_when_video_already_present():
    """No fetch triggered when game already has video_url set."""
    game = _tile(video_url="snes/snap/test.mp4", expected_snap_path="snes/snap/test.mp4")
    vm = WallViewModel(tiles=[game], columns=2)
    fetcher = FakeSnapFetcher(succeed=True)

    page = MagicMock(spec=["on_keyboard_event", "run_task"])
    tasks: list = []
    page.run_task = lambda coro, *a: tasks.append((coro, a))

    nav = Navigator(vm, page, snap_fetcher=fetcher, media_root=Path("/tmp"))
    nav.select(game)

    fetch_tasks = [(c, a) for c, a in tasks if c == nav._do_snap_fetch]
    assert len(fetch_tasks) == 0


@pytest.mark.asyncio
async def test_detail_open_does_not_fetch_when_no_expected_snap_path():
    """No fetch triggered when game has no expected_snap_path (no remote snap)."""
    game = _tile(expected_snap_path="")
    vm = WallViewModel(tiles=[game], columns=2)
    fetcher = FakeSnapFetcher(succeed=True)

    page = MagicMock(spec=["on_keyboard_event", "run_task"])
    tasks: list = []
    page.run_task = lambda coro, *a: tasks.append((coro, a))

    nav = Navigator(vm, page, snap_fetcher=fetcher, media_root=Path("/tmp"))
    nav.select(game)

    fetch_tasks = [(c, a) for c, a in tasks if c == nav._do_snap_fetch]
    assert len(fetch_tasks) == 0


# --- RACE CONDITION: game A fetch completes while game B is selected ---

@pytest.mark.asyncio
async def test_race_fetch_for_game_a_does_not_apply_to_game_b(tmp_path: Path):
    """Fetch for game A completing while game B is selected does NOT set B's video."""
    game_a = _tile("GameA", expected_snap_path="snes/snap/a.mp4")
    game_b = _tile("GameB", expected_snap_path="snes/snap/b.mp4")
    vm = WallViewModel(tiles=[game_a, game_b], columns=2)
    fetcher = FakeSnapFetcher(succeed=True)

    nav = Navigator(vm, snap_fetcher=fetcher, media_root=tmp_path)

    # Simulate: user selected game_a, fetch starts, then user backs and selects game_b
    nav._state.selected = game_b  # current detail = B

    # Run the fetch as if it was started for game_a
    await nav._do_snap_fetch(game_a)

    # File should be cached on disk
    assert (tmp_path / "snes" / "snap" / "a.mp4").is_file()
    # But B's state should NOT be touched
    assert nav._state.selected is game_b
    assert nav._state.selected.video_url == ""  # B untouched


@pytest.mark.asyncio
async def test_race_fetch_applies_when_same_game_still_selected(tmp_path: Path):
    """Fetch for game A applying correctly when A is still selected."""
    game_a = _tile("GameA", expected_snap_path="snes/snap/a.mp4")
    vm = WallViewModel(tiles=[game_a], columns=2)
    fetcher = FakeSnapFetcher(succeed=True)

    nav = Navigator(vm, snap_fetcher=fetcher, media_root=tmp_path)
    nav._state.selected = game_a

    await nav._do_snap_fetch(game_a)

    # File cached
    assert (tmp_path / "snes" / "snap" / "a.mp4").is_file()
    # video_url updated on selected tile
    assert nav._state.selected.video_url == "snes/snap/a.mp4"
    # VM tile also updated for future visits
    assert vm.tiles[0].video_url == "snes/snap/a.mp4"


# --- Failure: fetch returns False ---

@pytest.mark.asyncio
async def test_fetch_failure_leaves_static_art_no_exception(tmp_path: Path):
    """When fetch fails (Pi unreachable), game stays on static art, no crash."""
    game = _tile("GameA", expected_snap_path="snes/snap/a.mp4")
    vm = WallViewModel(tiles=[game], columns=2)
    fetcher = FakeSnapFetcher(succeed=False)

    nav = Navigator(vm, snap_fetcher=fetcher, media_root=tmp_path)
    nav._state.selected = game

    # Should not raise
    await nav._do_snap_fetch(game)

    # No video set
    assert nav._state.selected.video_url == ""
    assert not (tmp_path / "snes" / "snap" / "a.mp4").is_file()
