"""Build a reviewed, immutable N=2 image and a host-local Sandbox profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml


HERE = Path(__file__).resolve().parent
SOURCE_FILES = frozenset({
    "run.py", "peer.py", "contracts.py", "protocol.md", "scenario-n2.json",
    "model.json", "cohort.json",
})
CONTEXT_FILES = SOURCE_FILES | {"entrypoint.py", "pins.json", "Dockerfile"}
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
HASH = re.compile(r"[0-9a-f]{64}")
BASE_REF = re.compile(r"[a-z0-9][a-z0-9._/-]*:[a-z0-9][a-z0-9._-]*")
BASE_TAG = "python-factory/edge-lab:local"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load_pins(path: Path) -> dict:
    pins = json.loads(path.read_text(encoding="utf-8"))
    if (set(pins) != {"schema_version", "sdk_distribution_sha256", "entrypoint_sha256", "files"}
            or pins["schema_version"] != 1 or set(pins["files"]) != SOURCE_FILES
            or not isinstance(pins["sdk_distribution_sha256"], str)
            or HASH.fullmatch(pins["sdk_distribution_sha256"]) is None
            or not isinstance(pins["entrypoint_sha256"], str)
            or HASH.fullmatch(pins["entrypoint_sha256"]) is None
            or any(not isinstance(value, str) or HASH.fullmatch(value) is None
                   for value in pins["files"].values())):
        raise ValueError("Reviewed source pin contract is invalid")
    return pins


def validate_source_hashes(paths: dict[str, Path], pins: dict) -> dict[str, str]:
    if set(paths) != SOURCE_FILES or set(pins["files"]) != SOURCE_FILES:
        raise ValueError("Source allowlist differs from reviewed pins")
    observed = {}
    for name in SOURCE_FILES:
        path = paths[name]
        if path.is_symlink():
            raise ValueError("Source symlink is forbidden")
        if not path.is_file():
            raise ValueError("Reviewed source file is missing")
        observed[name] = sha256(path)
        if observed[name] != pins["files"][name]:
            raise ValueError(f"Reviewed source hash mismatch: {name}")
    return observed


def validate_entrypoint_hash(path: Path, pins: dict) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Entrypoint must be a regular reviewed source")
    observed = sha256(path)
    if observed != pins["entrypoint_sha256"]:
        raise ValueError("Entrypoint hash mismatch")
    return observed


def validate_scenario_inputs(paths: dict[str, Path], pins: dict) -> dict:
    # Use the reviewed contract itself, including its independent scenario
    # digest and model/cohort payload checks, before building any image.
    import importlib.util

    spec = importlib.util.spec_from_file_location("sealed_reviewed_contracts", paths["contracts.py"])
    if spec is None or spec.loader is None:
        raise ValueError("Reviewed contracts cannot load")
    contracts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contracts)
    scenario = contracts.validate_scenario(contracts.parse_json_bytes(paths["scenario-n2.json"].read_bytes()))
    if scenario["sdk_distribution_sha256"] != pins["sdk_distribution_sha256"]:
        raise ValueError("Scenario SDK digest differs from review pin")
    model, cohort = contracts.load_pinned_artifacts(scenario, paths["model.json"], paths["cohort.json"])
    scores = contracts.verify_parity(model, cohort)
    if len(scores) != 100 or len(scenario["cohort"]["engine_ids"]) != 2:
        raise ValueError("Frozen N=2 parity cohort is incomplete")
    return {"scenario_id": scenario["scenario_id"], "parity_rows": len(scores),
            "selected_engine_ids": scenario["cohort"]["engine_ids"]}


def dockerfile(base_ref: str) -> str:
    # BuildKit treats a raw local image ID in FROM as a remote repository name.
    # Resolve the local tag to an ID before and after build instead.
    if BASE_REF.fullmatch(base_ref) is None:
        raise ValueError("Base image reference must be a local tagged image")
    copied = " ".join(sorted(SOURCE_FILES | {"entrypoint.py", "pins.json"}))
    return (f"FROM {base_ref}\nWORKDIR /sealed\nCOPY {copied} /sealed/\n"
            'ENTRYPOINT ["/usr/local/bin/python", "/sealed/entrypoint.py"]\nCMD ["preflight"]\n')


def assemble_context(context: Path, paths: dict[str, Path], pins: dict,
                     entrypoint: Path, base_ref: str) -> None:
    validate_source_hashes(paths, pins)
    validate_entrypoint_hash(entrypoint, pins)
    if context.exists():
        raise ValueError("Docker context must be new")
    context.mkdir()
    for name, source in paths.items():
        (context / name).write_bytes(source.read_bytes())
    (context / "entrypoint.py").write_bytes(entrypoint.read_bytes())
    (context / "pins.json").write_text(json.dumps(pins, sort_keys=True, indent=2) + "\n")
    (context / "Dockerfile").write_text(dockerfile(base_ref))
    validate_context(context)


def validate_context(context: Path) -> dict[str, str]:
    found = {path.name for path in context.iterdir()}
    if found != CONTEXT_FILES:
        raise ValueError("Docker context has missing or extra files")
    hashes = {}
    for path in context.iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError("Docker context contains a nonregular file")
        hashes[path.name] = sha256(path)
    return hashes


def write_profile(path: Path, final_id: str) -> dict:
    if IMAGE_ID.fullmatch(final_id) is None:
        raise ValueError("Final image ID must be immutable")
    profile = {
        "name": "edge-n2-sdk", "image": final_id, "container_name": "edge-n2-sdk",
        "replace_existing": False, "platform": "linux/arm64", "cpus": 1.0,
        "memory_mb": 512, "shell": "/bin/sh", "entrypoint": ["run"],
        "secret_refs": ["ditto-offline-license"], "setup_commands": [],
        "peer_network": {"network_id": "edge-n2-sdk-lab", "alias": "edge-n2-sdk",
                         "port": 17331, "internal": True},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".edge-n2-sdk-", delete=False) as stream:
        yaml.safe_dump(profile, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
        temporary = Path(stream.name)
    os.replace(temporary, path)
    return profile


def docker(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(["docker", *args], input=input_text, text=True,
                            capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Docker {args[0]} failed: {result.stderr.strip()[:2000]}")
    return result.stdout.strip()


def inspect_base(tag: str) -> tuple[str, str]:
    output = docker("image", "inspect", tag, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}")
    image_id, platform = output.split()
    if IMAGE_ID.fullmatch(image_id) is None or platform != "linux/arm64":
        raise ValueError("Base image is not the expected ARM64 image")
    return image_id, platform


def installed_sdk_digest(base_id: str, contracts_path: Path) -> str:
    script = contracts_path.read_text(encoding="utf-8") + "\nprint(installed_ditto_digest())\n"
    observed = docker("run", "--rm", "-i", "--network", "none", "--entrypoint", "python", base_id,
                      "-", input_text=script).strip()
    if HASH.fullmatch(observed) is None:
        raise ValueError("Base image SDK digest output is invalid")
    return observed


def build(model: Path, cohort: Path, output: Path, profile_output: Path,
          base_tag: str = BASE_TAG) -> dict:
    if output.exists():
        raise ValueError("Build evidence directory must be new")
    pins = load_pins(HERE / "sealed_pins.json")
    paths = {name: (model if name == "model.json" else cohort if name == "cohort.json" else HERE / name)
             for name in SOURCE_FILES}
    observed = validate_source_hashes(paths, pins)
    entrypoint_sha256 = validate_entrypoint_hash(HERE / "sealed_entrypoint.py", pins)
    scenario_check = validate_scenario_inputs(paths, pins)
    base_id, platform = inspect_base(base_tag)
    sdk_digest = installed_sdk_digest(base_id, paths["contracts.py"])
    if sdk_digest != pins["sdk_distribution_sha256"]:
        raise ValueError("Base image SDK digest differs from the reviewed pin")
    output.mkdir(parents=True)
    with tempfile.TemporaryDirectory(prefix="sealed-context-", dir=output) as temporary_root:
        context = Path(temporary_root) / "context"
        assemble_context(context, paths, pins, HERE / "sealed_entrypoint.py", base_tag)
        context_hashes = validate_context(context)
        iidfile = output / "image.iid"
        docker("build", "--pull=false", "--network=none", "--iidfile", str(iidfile),
               str(context))
    final_id = iidfile.read_text().strip()
    if IMAGE_ID.fullmatch(final_id) is None:
        raise ValueError("Docker did not return an immutable final image ID")
    observed_final, final_platform = inspect_base(final_id)
    if observed_final != final_id or final_platform != platform:
        raise ValueError("Built image identity or platform changed")
    if inspect_base(base_tag) != (base_id, platform):
        raise ValueError("Base image tag changed during build")
    preflight = json.loads(docker("run", "--rm", "--network", "none", "--read-only",
                                  "--tmpfs", "/tmp:rw,size=64m", final_id))
    if (preflight.get("status") != "passed" or preflight.get("parity_rows") != 100
            or preflight.get("sdk_distribution_sha256") != sdk_digest
            or preflight.get("license_used") is not False
            or preflight.get("peers_launched") is not False):
        raise ValueError("License-free sealed-image preflight failed")
    profile = write_profile(profile_output, final_id)
    evidence = {"schema_version": 1, "status": "license_free_preflight_passed",
                "created_at_utc": datetime.now(UTC).isoformat(),
                "base_image_ref": base_tag, "base_image_id": base_id,
                "final_image_id": final_id, "platform": platform,
                "sdk_distribution_sha256": sdk_digest, "source_sha256": observed,
                "entrypoint_sha256": entrypoint_sha256,
                "context_sha256": context_hashes, "scenario_check": scenario_check,
                "preflight": preflight, "profile_path": str(profile_output),
                "profile_sha256": sha256(profile_output), "profile": profile,
                "build_network": "none", "preflight_network": "none", "license_mounted": False}
    (output / "build-evidence.json").write_text(json.dumps(evidence, sort_keys=True, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile-output", type=Path, required=True)
    parser.add_argument("--base-image", default=BASE_TAG)
    args = parser.parse_args()
    result = build(args.model, args.cohort, args.output, args.profile_output, args.base_image)
    print(json.dumps({"status": result["status"], "base_image_id": result["base_image_id"],
                      "final_image_id": result["final_image_id"],
                      "profile_sha256": result["profile_sha256"]}, sort_keys=True))
