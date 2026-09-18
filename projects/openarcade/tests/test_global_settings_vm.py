"""Tests for global_settings_vm — behavior-named, AAA."""

from __future__ import annotations

import pytest

from wall.global_settings_vm import (
    build_global_settings_vm,
    GlobalSettingsVM,
    VIDEO_ASPECT_RATIO_CFG_KEY,
    AUDIO_VOLUME_CHOICES,
    AUDIO_LATENCY_CHOICES,
    RUN_AHEAD_FRAMES_CHOICES,
    VIDEO_FRAME_DELAY_CHOICES,
)


class TestBuildGlobalSettingsVmDefaults:
    """All three sections render at defaults when no override cfg exists."""

    def test_empty_cfg_produces_all_sections(self) -> None:
        vm = build_global_settings_vm({})

        assert vm.video.title == "Video"
        assert vm.audio.title == "Audio"
        assert vm.latency.title == "Latency"

    def test_video_defaults(self) -> None:
        vm = build_global_settings_vm({})

        rows = {r.key: r for r in vm.video.rows}
        assert rows[VIDEO_ASPECT_RATIO_CFG_KEY].current == "Auto"
        assert rows["video_scale_integer"].current == "false"
        assert rows["video_vsync"].current == "true"
        assert rows["video_smooth"].current == "false"

    def test_audio_defaults(self) -> None:
        vm = build_global_settings_vm({})

        rows = {r.key: r for r in vm.audio.rows}
        assert rows["audio_mute_enable"].current == "false"
        assert rows["audio_volume"].current == "0"
        assert rows["audio_latency"].current == "64"

    def test_latency_defaults(self) -> None:
        vm = build_global_settings_vm({})

        rows = {r.key: r for r in vm.latency.rows}
        assert rows["run_ahead_frames"].current == "0"
        assert rows["video_frame_delay"].current == "0"


class TestBuildGlobalSettingsVmOverrides:
    """Live global override value wins over default."""

    def test_aspect_ratio_override(self) -> None:
        vm = build_global_settings_vm({VIDEO_ASPECT_RATIO_CFG_KEY: "16:9"})

        rows = {r.key: r for r in vm.video.rows}
        assert rows[VIDEO_ASPECT_RATIO_CFG_KEY].current == "16:9"

    def test_video_vsync_false_override(self) -> None:
        vm = build_global_settings_vm({"video_vsync": "false"})

        rows = {r.key: r for r in vm.video.rows}
        assert rows["video_vsync"].current == "false"

    def test_audio_volume_override(self) -> None:
        vm = build_global_settings_vm({"audio_volume": "5"})

        rows = {r.key: r for r in vm.audio.rows}
        assert rows["audio_volume"].current == "5"

    def test_run_ahead_frames_override(self) -> None:
        vm = build_global_settings_vm({"run_ahead_frames": "3"})

        rows = {r.key: r for r in vm.latency.rows}
        assert rows["run_ahead_frames"].current == "3"

    def test_video_frame_delay_override(self) -> None:
        vm = build_global_settings_vm({"video_frame_delay": "8"})

        rows = {r.key: r for r in vm.latency.rows}
        assert rows["video_frame_delay"].current == "8"

    def test_invalid_choice_falls_back_to_default(self) -> None:
        vm = build_global_settings_vm({"audio_latency": "9999"})

        rows = {r.key: r for r in vm.audio.rows}
        assert rows["audio_latency"].current == "64"  # default

    def test_audio_volume_strips_decimal_suffix(self) -> None:
        """RetroArch stores volume as '5.000000'; VM normalizes to '5'."""
        vm = build_global_settings_vm({"audio_volume": "5.000000"})

        rows = {r.key: r for r in vm.audio.rows}
        assert rows["audio_volume"].current == "5"


class TestBuildGlobalSettingsVmControlTypes:
    """Each control type maps correctly (bool -> toggle, enum -> dropdown)."""

    def test_toggles_have_is_toggle_true(self) -> None:
        vm = build_global_settings_vm({})

        toggle_keys = {"video_scale_integer", "video_vsync", "video_smooth", "audio_mute_enable"}
        for section in (vm.video, vm.audio, vm.latency):
            for row in section.rows:
                if row.key in toggle_keys:
                    assert row.is_toggle is True, f"{row.key} should be toggle"
                else:
                    assert row.is_toggle is False, f"{row.key} should be dropdown"

    def test_dropdown_choices_populated(self) -> None:
        vm = build_global_settings_vm({})

        rows = {r.key: r for section in (vm.video, vm.audio, vm.latency) for r in section.rows}
        assert len(rows["run_ahead_frames"].choices) == 7  # "0".."6"
        assert len(rows["video_frame_delay"].choices) == 16  # "0".."15"
        assert len(rows["audio_latency"].choices) == 4


class TestGlobalSettingsRoundTrip:
    """run_ahead_frames '0' vs '3' round-trips through VM."""

    def test_frames_zero_means_off(self) -> None:
        vm = build_global_settings_vm({"run_ahead_frames": "0"})
        rows = {r.key: r for r in vm.latency.rows}
        assert rows["run_ahead_frames"].current == "0"

    def test_frames_three(self) -> None:
        vm = build_global_settings_vm({"run_ahead_frames": "3"})
        rows = {r.key: r for r in vm.latency.rows}
        assert rows["run_ahead_frames"].current == "3"


class TestSaveGlobalOverridesMerge:
    """save_global_overrides merges without clobbering existing keys."""

    def test_merge_preserves_existing(self, tmp_path: Path) -> None:
        from wall.config_service import save_global_overrides, _load_existing
        from factory.arcade_config.runtime.resolver import override_path
        from factory.arcade_config.runtime.models import Scope

        # Seed an existing global override
        save_global_overrides({"video_smooth": "true"}, base_dir=tmp_path)

        # Write a new key
        save_global_overrides({"audio_volume": "5"}, base_dir=tmp_path)

        # Both keys preserved
        path = override_path(tmp_path, Scope.GLOBAL, kind="cfg")
        content = _load_existing(path)
        assert content["video_smooth"] == "true"
        assert content["audio_volume"] == "5"


# Need Path for tmp_path fixture
from pathlib import Path
