"""Tests for gamelist_source: pure parser + selective IO loader."""

from pathlib import Path

from wall.gamelist_source import parse_gamelist, load_gamelist, _derive_video_url
from wall.models import GameTile


_FULL_GAME_XML = """\
<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Super Metroid (USA).sfc</path>
    <name>Super Metroid</name>
    <desc>Explore planet Zebes.</desc>
    <image>./boxart/Super Metroid (USA).png</image>
    <marquee>./marquee/Super Metroid.png</marquee>
    <video>./videos/Super Metroid.mp4</video>
    <rating>0.9</rating>
    <releasedate>19940319T000000</releasedate>
    <developer>Nintendo R&amp;D1</developer>
    <publisher>Nintendo</publisher>
    <genre>Action</genre>
    <players>1</players>
  </game>
</gameList>
"""

_EMPTY_FIELDS_XML = """\
<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Foo Bar.sfc</path>
    <name>Foo Bar</name>
    <desc/>
    <image/>
    <developer/>
    <releasedate/>
    <publisher/>
    <genre/>
    <players/>
  </game>
</gameList>
"""

_TWO_GAMES_XML = """\
<?xml version="1.0"?>
<gameList>
  <game>
    <path>./A.sfc</path>
    <name>Game A</name>
    <image>./boxart/A.png</image>
    <releasedate>19930713T000000</releasedate>
  </game>
  <game>
    <path>./B.sfc</path>
    <name>Game B</name>
    <image>./boxart/B.png</image>
    <releasedate>00000000T000000</releasedate>
  </game>
</gameList>
"""


def test_parse_full_game_maps_all_fields():
    tiles = parse_gamelist(_FULL_GAME_XML, system="snes")
    assert len(tiles) == 1
    t = tiles[0]
    assert t.id == "snes-super metroid (usa)"
    assert t.title == "Super Metroid"
    assert t.system == "SNES"
    assert t.art_url == "snes/boxart/Super Metroid (USA).png"
    assert t.description == "Explore planet Zebes."
    assert t.developer == "Nintendo R&D1"
    assert t.publisher == "Nintendo"
    assert t.genre == "Action"
    assert t.players == "1"
    assert t.rating == "0.9"
    assert t.release_date == "1994-03-19"
    assert t.playable is True
    assert t.rom_path == "./Super Metroid (USA).sfc"
    assert t.art_name is None


def test_parse_empty_fields_yield_none():
    tiles = parse_gamelist(_EMPTY_FIELDS_XML, system="snes")
    t = tiles[0]
    assert t.description is None
    assert t.developer is None
    assert t.rating is None
    assert t.release_date is None
    assert t.art_url == ""
    assert t.publisher == ""
    assert t.genre == ""
    assert t.players == ""


def test_parse_releasedate_formats():
    tiles = parse_gamelist(_TWO_GAMES_XML, system="snes")
    assert tiles[0].release_date == "1993-07-13"
    assert tiles[1].release_date is None  # 00000000 -> None


def test_art_url_derives_relative_path_with_system():
    tiles = parse_gamelist(_TWO_GAMES_XML, system="snes")
    assert tiles[0].art_url == "snes/boxart/A.png"
    assert tiles[1].art_url == "snes/boxart/B.png"


def test_load_gamelist_require_media_filters_to_existing_covers(tmp_path: Path):
    # Arrange: write gamelist + create cover for only Game A
    gl_dir = tmp_path / "gamelists" / "snes"
    gl_dir.mkdir(parents=True)
    gl_file = gl_dir / "gamelist.xml"
    gl_file.write_text(_TWO_GAMES_XML)

    media_root = tmp_path
    art_dir = media_root / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "A.png").write_bytes(b"\x89PNG")  # only A exists

    # Create roms so tiles stay playable
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "A.sfc").write_bytes(b"\x00")

    # Act
    tiles = load_gamelist(gl_file, system="snes", media_root=media_root, roms_root=roms_dir, require_media=True)

    # Assert: only Game A (has cover)
    assert len(tiles) == 1
    assert tiles[0].title == "Game A"


def test_load_gamelist_require_media_false_returns_all(tmp_path: Path):
    gl_file = tmp_path / "gamelist.xml"
    gl_file.write_text(_TWO_GAMES_XML)

    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "A.sfc").write_bytes(b"\x00")
    (roms_dir / "B.sfc").write_bytes(b"\x00")

    tiles = load_gamelist(gl_file, system="snes", media_root=tmp_path, roms_root=roms_dir, require_media=False)
    assert len(tiles) == 2


# --- Cycle 3: video-snap attract ---


def test_derive_video_url_strips_dot_slash_and_prepends_system():
    """_derive_video_url strips './' and prepends lowered system."""
    assert _derive_video_url("./snap/Foo.mp4", "SNES") == "snes/snap/Foo.mp4"


def test_derive_video_url_empty_and_none_return_empty():
    """Empty or None video_text -> empty string."""
    assert _derive_video_url("", "SNES") == ""
    assert _derive_video_url(None, "SNES") == ""


def test_parse_gamelist_captures_video_path():
    """parse_gamelist maps <video> element to video_url field."""
    tiles = parse_gamelist(_FULL_GAME_XML, system="snes")
    assert tiles[0].video_url == "snes/videos/Super Metroid.mp4"


def test_parse_gamelist_missing_video_yields_empty():
    """No <video> element -> video_url is empty string."""
    tiles = parse_gamelist(_EMPTY_FIELDS_XML, system="snes")
    assert tiles[0].video_url == ""


def test_load_gamelist_clears_video_url_when_snap_absent(tmp_path: Path):
    """video_url is cleared when the local snap file does not exist."""
    gl_file = tmp_path / "gamelist.xml"
    gl_file.write_text(_FULL_GAME_XML)

    media_root = tmp_path
    # Create cover so tile survives the cover filter
    art_dir = media_root / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "Super Metroid (USA).png").write_bytes(b"\x89PNG")
    # Do NOT create the snap file -> video_url should be cleared

    # Create ROM so tile stays playable
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "Super Metroid (USA).sfc").write_bytes(b"\x00")

    tiles = load_gamelist(gl_file, system="snes", media_root=media_root, roms_root=roms_dir, require_media=True)
    assert len(tiles) == 1
    assert tiles[0].video_url == ""


def test_load_gamelist_keeps_video_url_when_snap_present(tmp_path: Path):
    """video_url is kept when the local snap file exists."""
    gl_file = tmp_path / "gamelist.xml"
    gl_file.write_text(_FULL_GAME_XML)

    media_root = tmp_path
    # Create cover
    art_dir = media_root / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "Super Metroid (USA).png").write_bytes(b"\x89PNG")
    # Create the snap file
    snap_dir = media_root / "snes" / "videos"
    snap_dir.mkdir(parents=True)
    (snap_dir / "Super Metroid.mp4").write_bytes(b"\x00\x00\x00\x1cftyp")

    # Create ROM
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "Super Metroid (USA).sfc").write_bytes(b"\x00")

    tiles = load_gamelist(gl_file, system="snes", media_root=media_root, roms_root=roms_dir, require_media=True)
    assert len(tiles) == 1
    assert tiles[0].video_url == "snes/videos/Super Metroid.mp4"


# --- Bead 6z3gx: rom_path resolution tests ---


def test_load_gamelist_resolves_rom_path_to_absolute(tmp_path: Path):
    """load_gamelist resolves relative rom_path to absolute via roms_root."""
    gl_file = tmp_path / "gamelist.xml"
    gl_file.write_text(_FULL_GAME_XML)

    media_root = tmp_path
    art_dir = media_root / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "Super Metroid (USA).png").write_bytes(b"\x89PNG")

    # Create the actual ROM file in roms_root
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    rom_file = roms_dir / "Super Metroid (USA).sfc"
    rom_file.write_bytes(b"\x00" * 16)

    tiles = load_gamelist(gl_file, system="snes", media_root=media_root, roms_root=roms_dir)
    assert len(tiles) == 1
    assert tiles[0].rom_path == str(rom_file)
    assert tiles[0].playable is True


def test_load_gamelist_marks_unplayable_when_rom_missing(tmp_path: Path):
    """Tile is marked playable=False with empty rom_path when ROM file absent."""
    gl_file = tmp_path / "gamelist.xml"
    gl_file.write_text(_FULL_GAME_XML)

    media_root = tmp_path
    art_dir = media_root / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "Super Metroid (USA).png").write_bytes(b"\x89PNG")

    # roms_root exists but has no ROM file
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()

    tiles = load_gamelist(gl_file, system="snes", media_root=media_root, roms_root=roms_dir)
    assert len(tiles) == 1
    assert tiles[0].playable is False
    assert tiles[0].rom_path == ""


def test_load_gamelist_strips_dot_slash_from_rom_path(tmp_path: Path):
    """Path('./Foo.sfc').name correctly strips leading './' for resolution."""
    gl_file = tmp_path / "gamelist.xml"
    gl_file.write_text(_TWO_GAMES_XML)

    media_root = tmp_path
    art_dir = media_root / "snes" / "boxart"
    art_dir.mkdir(parents=True)
    (art_dir / "A.png").write_bytes(b"\x89PNG")
    (art_dir / "B.png").write_bytes(b"\x89PNG")

    # Create ROM files (gamelist has ./A.sfc and ./B.sfc)
    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "A.sfc").write_bytes(b"\x00")
    (roms_dir / "B.sfc").write_bytes(b"\x00")

    tiles = load_gamelist(gl_file, system="snes", media_root=media_root, roms_root=roms_dir)
    assert len(tiles) == 2
    assert tiles[0].rom_path == str(roms_dir / "A.sfc")
    assert tiles[1].rom_path == str(roms_dir / "B.sfc")
    assert all(t.playable for t in tiles)


def test_load_gamelist_require_media_false_still_resolves_roms(tmp_path: Path):
    """Even with require_media=False, rom resolution still runs."""
    gl_file = tmp_path / "gamelist.xml"
    gl_file.write_text(_TWO_GAMES_XML)

    roms_dir = tmp_path / "roms"
    roms_dir.mkdir()
    (roms_dir / "A.sfc").write_bytes(b"\x00")
    # B.sfc missing -> should be non-playable

    tiles = load_gamelist(
        gl_file, system="snes", media_root=tmp_path, roms_root=roms_dir, require_media=False
    )
    assert len(tiles) == 2
    assert tiles[0].playable is True
    assert tiles[0].rom_path == str(roms_dir / "A.sfc")
    assert tiles[1].playable is False
    assert tiles[1].rom_path == ""
