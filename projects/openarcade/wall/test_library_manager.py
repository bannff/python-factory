"""Tests for wall.library_scan and wall.library_import — behavior-named AAA."""

from pathlib import Path

import pytest

from wall.library_scan import (
    classify_files,
    build_gamelist_entries,
    scan_directory,
    RomCandidate,
    ScanResult,
    SYSTEM_EXTENSIONS,
)
from wall.library_import import write_gamelist


# ===== classify_files =====


class TestClassifyFiles:
    """classify_files: PURE extension-based ROM classification."""

    def test_snes_extensions_matched(self):
        """classify_files returns candidates for all valid SNES extensions."""
        files = ["game.sfc", "game2.smc", "game3.zip", "readme.txt"]
        result = classify_files(files, system="snes")
        assert len(result) == 3
        assert all(c.system == "snes" for c in result)

    def test_unknown_extensions_excluded(self):
        """classify_files ignores files with non-ROM extensions."""
        files = ["readme.txt", "cover.png", "save.srm"]
        result = classify_files(files, system="snes")
        assert result == []

    def test_case_insensitive_extension(self):
        """classify_files matches extensions case-insensitively."""
        files = ["GAME.SFC", "other.Smc"]
        result = classify_files(files, system="snes")
        assert len(result) == 2

    def test_relative_path_convention(self):
        """classify_files produces relative ./filename paths."""
        files = ["zelda.sfc"]
        result = classify_files(files, system="snes")
        assert result[0].rom_path == "./zelda.sfc"

    def test_id_derivation(self):
        """classify_files derives id as {system}-{stem} lowercase."""
        files = ["Super Mario World.sfc"]
        result = classify_files(files, system="SNES")
        assert result[0].id == "snes-super mario world"

    def test_dedupes_by_rom_path(self):
        """classify_files deduplicates by rom_path (first wins)."""
        files = ["game.sfc", "game.sfc"]
        result = classify_files(files, system="snes")
        assert len(result) == 1

    def test_unknown_system_returns_empty(self):
        """classify_files returns [] for unknown system."""
        files = ["game.xyz"]
        result = classify_files(files, system="unknownsystem")
        assert result == []

    def test_title_is_stem(self):
        """classify_files uses filename stem as title."""
        files = ["Chrono Trigger.sfc"]
        result = classify_files(files, system="snes")
        assert result[0].title == "Chrono Trigger"

    def test_n64_extensions(self):
        """classify_files handles N64 multi-extension variants."""
        files = ["mario.z64", "zelda.n64", "star.v64", "other.zip"]
        result = classify_files(files, system="n64")
        assert len(result) == 4

    def test_arcade_extensions(self):
        """classify_files handles arcade .zip and .chd."""
        files = ["kinst.zip", "kinst2.chd", "readme.txt"]
        result = classify_files(files, system="arcade")
        assert len(result) == 2


# ===== build_gamelist_entries =====


class TestBuildGamelistEntries:
    """build_gamelist_entries: classifies against existing library."""

    def _candidate(self, id: str) -> RomCandidate:
        return RomCandidate(
            id=id, title=id, system="snes", rom_path=f"./{id}.sfc", status="unmatched",
        )

    def test_matched_when_in_ids_and_art(self):
        """Candidate is 'matched' when in both existing_ids and existing_art_ids."""
        c = self._candidate("snes-zelda")
        result = build_gamelist_entries(
            [c],
            existing_ids=frozenset({"snes-zelda"}),
            existing_art_ids=frozenset({"snes-zelda"}),
        )
        assert result[0].status == "matched"

    def test_metadata_only_when_in_ids_no_art(self):
        """Candidate is 'metadata_only' when in existing_ids but NOT art_ids."""
        c = self._candidate("snes-zelda")
        result = build_gamelist_entries(
            [c],
            existing_ids=frozenset({"snes-zelda"}),
            existing_art_ids=frozenset(),
        )
        assert result[0].status == "metadata_only"

    def test_unmatched_when_not_in_ids(self):
        """Candidate stays 'unmatched' when not in existing_ids."""
        c = self._candidate("snes-newgame")
        result = build_gamelist_entries(
            [c],
            existing_ids=frozenset({"snes-zelda"}),
            existing_art_ids=frozenset({"snes-zelda"}),
        )
        assert result[0].status == "unmatched"

    def test_none_sets_treated_as_empty(self):
        """None existing sets = everything unmatched."""
        c = self._candidate("snes-game")
        result = build_gamelist_entries([c], existing_ids=None, existing_art_ids=None)
        assert result[0].status == "unmatched"


# ===== scan_directory =====


class TestScanDirectory:
    """scan_directory: IO edge scanning a real tmp directory."""

    def test_scan_real_directory(self, tmp_path):
        """scan_directory counts matched/metadata_only/unmatched correctly."""
        (tmp_path / "zelda.sfc").write_bytes(b"")
        (tmp_path / "mario.sfc").write_bytes(b"")
        (tmp_path / "readme.txt").write_bytes(b"")

        result = scan_directory(
            tmp_path,
            system="snes",
            existing_ids=frozenset({"snes-zelda"}),
            existing_art_ids=frozenset({"snes-zelda"}),
        )
        assert result.matched == 1  # zelda
        assert result.unmatched == 1  # mario (new)
        assert result.metadata_only == 0
        assert len(result.candidates) == 2

    def test_scan_nonexistent_dir_returns_empty(self):
        """scan_directory returns empty ScanResult for missing dir."""
        result = scan_directory(Path("/nonexistent"), system="snes")
        assert result.candidates == []
        assert result.matched == 0

    def test_scan_preserves_relative_paths(self, tmp_path):
        """scan_directory candidates use ./filename convention."""
        (tmp_path / "game.sfc").write_bytes(b"")
        result = scan_directory(tmp_path, system="snes")
        assert result.candidates[0].rom_path == "./game.sfc"


# ===== write_gamelist (NO-CLOBBER MERGE) =====


class TestWriteGamelist:
    """write_gamelist: IO edge XML writer with no-clobber merge."""

    def test_write_new_gamelist(self, tmp_path):
        """write_gamelist creates a new gamelist.xml when none exists."""
        gl_path = tmp_path / "gamelist.xml"
        candidates = [
            RomCandidate(id="snes-zelda", title="Zelda", system="snes",
                         rom_path="./zelda.sfc", status="unmatched"),
        ]
        count = write_gamelist(candidates, gl_path, merge=True)
        assert count == 1
        assert gl_path.exists()
        text = gl_path.read_text()
        assert "<path>./zelda.sfc</path>" in text
        assert "<name>Zelda</name>" in text

    def test_merge_does_not_overwrite_existing_metadata(self, tmp_path):
        """write_gamelist merge preserves existing entry metadata (no-clobber)."""
        gl_path = tmp_path / "gamelist.xml"
        # Pre-existing gamelist with hand-edited desc
        gl_path.write_text(
            '<?xml version="1.0"?>\n'
            '<gameList>\n'
            '  <game>\n'
            '    <path>./zelda.sfc</path>\n'
            '    <name>The Legend of Zelda</name>\n'
            '    <desc>A custom description</desc>\n'
            '  </game>\n'
            '</gameList>\n'
        )
        # Try to import zelda again + a new game
        candidates = [
            RomCandidate(id="snes-zelda", title="Zelda", system="snes",
                         rom_path="./zelda.sfc", status="unmatched"),
            RomCandidate(id="snes-mario", title="Mario", system="snes",
                         rom_path="./mario.sfc", status="unmatched"),
        ]
        count = write_gamelist(candidates, gl_path, merge=True)
        assert count == 1  # only mario is new
        text = gl_path.read_text()
        # Original metadata preserved
        assert "A custom description" in text
        assert "The Legend of Zelda" in text
        # New entry added
        assert "<path>./mario.sfc</path>" in text

    def test_merge_false_overwrites(self, tmp_path):
        """write_gamelist with merge=False creates fresh XML."""
        gl_path = tmp_path / "gamelist.xml"
        gl_path.write_text(
            '<?xml version="1.0"?>\n<gameList><game><path>./old.sfc</path>'
            '<name>Old</name></game></gameList>\n'
        )
        candidates = [
            RomCandidate(id="snes-new", title="New", system="snes",
                         rom_path="./new.sfc", status="unmatched"),
        ]
        count = write_gamelist(candidates, gl_path, merge=False)
        assert count == 1
        text = gl_path.read_text()
        assert "./new.sfc" in text
        assert "./old.sfc" not in text  # old entry gone

    def test_write_creates_parent_dirs(self, tmp_path):
        """write_gamelist creates parent directories if missing."""
        gl_path = tmp_path / "gamelists" / "snes" / "gamelist.xml"
        candidates = [
            RomCandidate(id="snes-game", title="Game", system="snes",
                         rom_path="./game.sfc", status="unmatched"),
        ]
        count = write_gamelist(candidates, gl_path, merge=True)
        assert count == 1
        assert gl_path.exists()

    def test_write_zero_candidates_no_file_change(self, tmp_path):
        """write_gamelist with empty candidates does not write."""
        gl_path = tmp_path / "gamelist.xml"
        count = write_gamelist([], gl_path, merge=True)
        assert count == 0
        assert not gl_path.exists()

    def test_import_games_returns_correct_count(self, tmp_path):
        """Integration: scan + write produces correct imported count."""
        (tmp_path / "roms").mkdir()
        (tmp_path / "roms" / "zelda.sfc").write_bytes(b"")
        (tmp_path / "roms" / "mario.sfc").write_bytes(b"")

        result = scan_directory(
            tmp_path / "roms",
            system="snes",
            existing_ids=frozenset({"snes-zelda"}),
            existing_art_ids=frozenset(),
        )
        new_candidates = [c for c in result.candidates if c.status == "unmatched"]
        gl_path = tmp_path / "gamelists" / "snes" / "gamelist.xml"
        count = write_gamelist(new_candidates, gl_path, merge=True)
        assert count == 1  # only mario is unmatched
