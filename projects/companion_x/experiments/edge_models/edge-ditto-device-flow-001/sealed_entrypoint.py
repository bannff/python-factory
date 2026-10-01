"""Fixed, argument-free boundary for the sealed N=2 SDK image."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path


ROOT = Path("/sealed")
LICENSE = Path("/run/secrets/ditto-offline-license")
SOURCE_FILES = frozenset({
    "run.py", "peer.py", "contracts.py", "protocol.md", "scenario-n2.json",
    "model.json", "cohort.json",
})
SHA256 = re.compile(r"[0-9a-f]{64}")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_pins(root: Path) -> dict:
    pins = json.loads((root / "pins.json").read_text(encoding="utf-8"))
    if (set(pins) != {"schema_version", "sdk_distribution_sha256", "entrypoint_sha256", "files"}
            or pins["schema_version"] != 1
            or set(pins["files"]) != SOURCE_FILES
            or not isinstance(pins["entrypoint_sha256"], str)
            or SHA256.fullmatch(pins["entrypoint_sha256"]) is None
            or SHA256.fullmatch(pins["sdk_distribution_sha256"]) is None
            or any(SHA256.fullmatch(value) is None for value in pins["files"].values())):
        raise ValueError("Sealed pin contract is invalid")
    return pins


def preflight(root: Path = ROOT) -> dict:
    pins = read_pins(root)
    entrypoint = root / "entrypoint.py"
    if (entrypoint.is_symlink() or not entrypoint.is_file()
            or digest(entrypoint) != pins["entrypoint_sha256"]):
        raise ValueError("Sealed entrypoint hash mismatch")
    for name, expected in pins["files"].items():
        path = root / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError("Sealed source hash mismatch")
    spec = importlib.util.spec_from_file_location("sealed_contracts", root / "contracts.py")
    if spec is None or spec.loader is None:
        raise ValueError("Sealed contracts cannot load")
    contracts = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contracts)
    scenario = contracts.validate_scenario(contracts.parse_json_bytes((root / "scenario-n2.json").read_bytes()))
    if scenario["sdk_distribution_sha256"] != pins["sdk_distribution_sha256"]:
        raise ValueError("Scenario SDK pin differs from sealed review pin")
    model, cohort = contracts.load_pinned_artifacts(scenario, root / "model.json", root / "cohort.json")
    scores = contracts.verify_parity(model, cohort)
    selected = scenario["cohort"]["engine_ids"]
    if len(scores) != 100 or len(selected) != 2:
        raise ValueError("Sealed cohort or N=2 assignment is invalid")
    observed_sdk = contracts.installed_ditto_digest()
    contracts.require_approved_sdk(scenario, observed_sdk)
    return {"status": "passed", "parity_rows": len(scores), "selected_engine_ids": selected,
            "sdk_distribution_sha256": observed_sdk, "license_used": False, "peers_launched": False}


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in {"preflight", "run"}:
        print(json.dumps({"status": "invalid_arguments"}, sort_keys=True))
        return 2
    try:
        result = preflight(root)
        if args[0] == "preflight":
            print(json.dumps(result, sort_keys=True))
            return 0
        if not LICENSE.is_file() or not stat.S_ISREG(LICENSE.stat().st_mode):
            raise ValueError("License mount is unavailable")
        output = Path("/evidence/run-001")
        output.parent.mkdir(exist_ok=True)
        os.execv(sys.executable, [sys.executable, str(root / "run.py"),
                                  "--scenario", str(root / "scenario-n2.json"),
                                  "--model", str(root / "model.json"),
                                  "--cohort", str(root / "cohort.json"),
                                  "--output", str(output)])
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "preflight_failed", "error_type": type(error).__name__}, sort_keys=True))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
