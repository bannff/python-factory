"""Boundary checks for the sealed ENG-202 image and profile."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


EXPERIMENT = Path(__file__).parents[1] / "experiments/edge_models/edge-ditto-device-flow-001"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_sources(tmp_path: Path, builder) -> tuple[dict[str, Path], dict]:
    paths = {}
    for name in builder.SOURCE_FILES:
        path = tmp_path / "sources" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((name + " reviewed bytes\n").encode())
        paths[name] = path
    pins = {"schema_version": 1, "sdk_distribution_sha256": "a" * 64,
            "entrypoint_sha256": hashlib.sha256((EXPERIMENT / "sealed_entrypoint.py").read_bytes()).hexdigest(),
            "files": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}}
    return paths, pins


def test_source_drift_and_symlink_fail_closed(tmp_path: Path) -> None:
    builder = load_module(EXPERIMENT / "sealed_image.py", "sealed_builder_drift")
    paths, pins = fixture_sources(tmp_path, builder)
    builder.validate_source_hashes(paths, pins)
    paths["scenario-n2.json"].write_text("modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        builder.validate_source_hashes(paths, pins)
    paths["scenario-n2.json"].write_text("scenario-n2.json reviewed bytes\n")
    target = paths["model.json"]
    target.unlink()
    target.symlink_to(paths["cohort.json"])
    with pytest.raises(ValueError, match="symlink"):
        builder.validate_source_hashes(paths, pins)


def test_context_is_exact_allowlist_and_excludes_host_secrets(tmp_path: Path) -> None:
    builder = load_module(EXPERIMENT / "sealed_image.py", "sealed_builder_context")
    paths, pins = fixture_sources(tmp_path, builder)
    entrypoint = EXPERIMENT / "sealed_entrypoint.py"
    context = tmp_path / "context"
    builder.assemble_context(context, paths, pins, entrypoint, "python-factory/edge-lab:local")
    builder.validate_context(context)
    assert {item.name for item in context.iterdir()} == builder.CONTEXT_FILES
    dockerfile = (context / "Dockerfile").read_text()
    assert dockerfile.startswith("FROM python-factory/edge-lab:local\n")
    assert "COPY ." not in dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/python", "/sealed/entrypoint.py"]' in dockerfile
    assert 'CMD ["preflight"]' in dockerfile
    assert b"ditto-offline-license" not in (context / "pins.json").read_bytes()
    (context / "license.txt").write_text("host secret")
    with pytest.raises(ValueError, match="extra"):
        builder.validate_context(context)


def test_entrypoint_drift_stops_context_creation(tmp_path: Path) -> None:
    builder = load_module(EXPERIMENT / "sealed_image.py", "sealed_builder_entrypoint")
    paths, pins = fixture_sources(tmp_path, builder)
    entrypoint = tmp_path / "unreviewed_entrypoint.py"
    entrypoint.write_text("print('unreviewed')\n")
    context = tmp_path / "context"
    with pytest.raises(ValueError, match="Entrypoint hash mismatch"):
        builder.assemble_context(context, paths, pins, entrypoint, "python-factory/edge-lab:local")
    assert not context.exists()


def test_build_stops_before_docker_and_profile_on_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = load_module(EXPERIMENT / "sealed_image.py", "sealed_builder_fail_closed")
    paths, pins = fixture_sources(tmp_path, builder)
    root = tmp_path / "sources"
    (root / "sealed_pins.json").write_text(json.dumps(pins))
    paths["peer.py"].write_text("unreviewed edit")
    monkeypatch.setattr(builder, "HERE", root)
    monkeypatch.setattr(builder, "docker", lambda *args, **kwargs: pytest.fail("Docker was invoked"))
    output = tmp_path / "build"
    profile = tmp_path / "profile.yaml"
    with pytest.raises(ValueError, match="hash mismatch"):
        builder.build(paths["model.json"], paths["cohort.json"], output, profile)
    assert not output.exists()
    assert not profile.exists()


def test_base_tag_drift_after_build_blocks_profile_and_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    builder = load_module(EXPERIMENT / "sealed_image.py", "sealed_builder_base_drift")
    paths, pins = fixture_sources(tmp_path, builder)
    root = tmp_path / "sources"
    (root / "sealed_pins.json").write_text(json.dumps(pins))
    (root / "sealed_entrypoint.py").write_bytes((EXPERIMENT / "sealed_entrypoint.py").read_bytes())
    monkeypatch.setattr(builder, "HERE", root)
    monkeypatch.setattr(
        builder, "validate_scenario_inputs",
        lambda *_: {"scenario_id": "test", "parity_rows": 100, "selected_engine_ids": [1, 2]},
    )
    monkeypatch.setattr(builder, "installed_sdk_digest", lambda *_: pins["sdk_distribution_sha256"])
    base_id, changed_id, final_id = ("sha256:" + char * 64 for char in "bcd")
    observed_tags = []

    def inspect(tag: str) -> tuple[str, str]:
        if tag == final_id:
            return final_id, "linux/arm64"
        observed_tags.append(tag)
        return (base_id if len(observed_tags) == 1 else changed_id), "linux/arm64"

    def docker(*args: str, **kwargs) -> str:
        assert args[0] == "build", "preflight must not run after base drift"
        Path(args[args.index("--iidfile") + 1]).write_text(final_id)
        return ""

    monkeypatch.setattr(builder, "inspect_base", inspect)
    monkeypatch.setattr(builder, "docker", docker)
    output = tmp_path / "build"
    profile = tmp_path / "profile.yaml"
    with pytest.raises(ValueError, match="Base image tag changed during build"):
        builder.build(paths["model.json"], paths["cohort.json"], output, profile)
    assert observed_tags == [builder.BASE_TAG, builder.BASE_TAG]
    assert not profile.exists()
    assert not (output / "build-evidence.json").exists()
    assert not list(output.glob("sealed-context-*"))


def test_profile_is_pinned_and_secret_safe(tmp_path: Path) -> None:
    builder = load_module(EXPERIMENT / "sealed_image.py", "sealed_builder_profile")
    path = tmp_path / "edge-n2-sdk.yaml"
    image_id = "sha256:" + "c" * 64
    builder.write_profile(path, image_id)
    profile = yaml.safe_load(path.read_text())
    assert profile["image"] == image_id
    assert profile["entrypoint"] == ["run"]
    assert profile["secret_refs"] == ["ditto-offline-license"]
    assert profile["peer_network"]["internal"] is True
    assert profile["replace_existing"] is False
    assert profile.get("setup_commands", []) == []
    assert "license_file" not in path.read_text()
    assert "source=" not in path.read_text()
    from factory.sandbox.runtime.profiles import SandboxProfile

    assert SandboxProfile.model_validate(profile).image == image_id


def test_entrypoint_rejects_other_args_without_starting_runner() -> None:
    entrypoint = load_module(EXPERIMENT / "sealed_entrypoint.py", "sealed_entrypoint_args")
    assert entrypoint.main(["--model", "other.json"]) == 2
    assert entrypoint.main([]) == 2
    assert entrypoint.main(["run", "extra"]) == 2
    assert entrypoint.main(["preflight", "extra"]) == 2


def test_image_preflight_rejects_entrypoint_drift_before_loading_contracts(tmp_path: Path) -> None:
    builder = load_module(EXPERIMENT / "sealed_image.py", "sealed_builder_runtime_fixture")
    entrypoint = load_module(EXPERIMENT / "sealed_entrypoint.py", "sealed_entrypoint_runtime_drift")
    _, pins = fixture_sources(tmp_path, builder)
    (tmp_path / "pins.json").write_text(json.dumps(pins))
    (tmp_path / "entrypoint.py").write_text("print('unreviewed')\n")
    with pytest.raises(ValueError, match="entrypoint hash mismatch"):
        entrypoint.preflight(tmp_path)
