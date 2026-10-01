"""Preflight artifacts, launch two isolated Ditto peers, and hash run evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
import socket
import sys
import tempfile
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from contracts import (
    digest_bytes,
    installed_ditto_digest,
    load_pinned_artifacts,
    observation_document,
    parse_json_bytes,
    peer_transport,
    require_approved_sdk,
    LATENCY_METRICS,
    validate_measurements,
    validate_scenario,
    verify_parity,
)

HERE = Path(__file__).resolve().parent
PEER_RUNNER = HERE / "peer.py"
CODE_SOURCES = (Path(__file__).resolve(), PEER_RUNNER, HERE / "contracts.py")
CODE_HASH_KEYS = ("runner_sha256", "peer_runner_sha256", "contracts_sha256")
STARTUP_SOURCE_SHA256 = tuple(digest_bytes(path.read_bytes()) for path in CODE_SOURCES)


class RunIntegrityError(ValueError):
    """Code changed while producing evidence for a run."""


def _free_ports() -> tuple[int, int]:
    with socket.socket() as first, socket.socket() as second:
        first.bind(("127.0.0.1", 0))
        second.bind(("127.0.0.1", 0))
        ports = (int(first.getsockname()[1]), int(second.getsockname()[1]))
    if ports[0] == ports[1]:
        return _free_ports()
    return ports


def _safe_worker_result(stdout: bytes) -> dict[str, Any] | None:
    # SDK output is captured and discarded; accept only the runner's JSON result.
    marked = [
        line.removeprefix("EDGE_DITTO_RESULT ")
        for line in stdout.decode("utf-8", errors="replace").splitlines()
        if line.startswith("EDGE_DITTO_RESULT ")
    ]
    if len(marked) != 1:
        return None
    try:
        value = parse_json_bytes(marked[0].encode())
    except (UnicodeError, ValueError, TypeError):
        return None
    return value if value.get("status") in {"passed", "failed"} else None


def _validated_result(
    value: dict[str, Any],
    peer_id: str,
    expected_topology: dict[str, str | int] | None = None,
    expected_predictions: dict[str, dict[str, Any]] | None = None,
    expected_sdk_digest: str | None = None,
    expected_device_digest: str | None = None,
) -> dict[str, Any] | None:
    if value.get("status") == "failed":
        if set(value) == {"status", "error_type", "write_failures"} and (
            isinstance(value["error_type"], str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,79}", value["error_type"])
        ) and type(value["write_failures"]) is int and value["write_failures"] in (0, 1):
            return {"status": "failed", "peer_id": peer_id,
                    "error_type": value["error_type"], "write_failures": value["write_failures"]}
        return None
    if value.get("status") != "passed":
        return None
    expected_fields = {
        "status",
        "peer_id",
        "device_id_sha256",
        "sdk_version",
        "sdk_distribution_sha256",
        "python_version",
        "platform",
        "topology",
        "local_persistence",
        "exact_replay",
        "synced_observation_count",
        "predictions",
        "elapsed_ms",
        "measurements",
    }
    if set(value) != expected_fields or value.get("peer_id") != peer_id:
        return None
    if (
        not isinstance(value["device_id_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["device_id_sha256"])
        or (
            expected_device_digest is not None
            and value["device_id_sha256"] != expected_device_digest
        )
        or not isinstance(value["sdk_distribution_sha256"], str)
        or not re.fullmatch(r"[0-9a-f]{64}", value["sdk_distribution_sha256"])
        or (
            expected_sdk_digest is not None
            and value["sdk_distribution_sha256"] != expected_sdk_digest
        )
        or any(
            not isinstance(value[key], str) or not value[key] or len(value[key]) > limit
            for key, limit in (("sdk_version", 64), ("python_version", 64), ("platform", 32))
        )
    ):
        return None
    if value["local_persistence"] != "passed" or value["exact_replay"] != "passed":
        return None
    topology = value["topology"]
    if not isinstance(topology, dict) or set(topology) != {
        "mode",
        "listen_interface",
        "listen_port",
        "neighbor_host",
        "neighbor_port",
    }:
        return None
    try:
        validated_topology = peer_transport(
            topology["mode"],
            topology["listen_interface"],
            topology["listen_port"],
            topology["neighbor_host"],
            topology["neighbor_port"],
        )
    except (TypeError, ValueError):
        return None
    if validated_topology != topology or (
        expected_topology is not None and topology != expected_topology
    ):
        return None
    if type(value["synced_observation_count"]) is not int or value["synced_observation_count"] != 2:
        return None
    predictions = value["predictions"]
    if not isinstance(predictions, list) or len(predictions) != 2:
        return None
    for prediction in predictions:
        if not isinstance(prediction, dict) or set(prediction) != {
            "observation_id_sha256",
            "input_id_sha256",
            "probability",
            "decision",
        }:
            return None
        if any(
            not isinstance(prediction[key], str)
            or not re.fullmatch(r"[0-9a-f]{64}", prediction[key])
            for key in ("observation_id_sha256", "input_id_sha256")
        ):
            return None
        if (
            type(prediction["probability"]) not in (float, int)
            or not math.isfinite(prediction["probability"])
            or not 0 <= prediction["probability"] <= 1
            or type(prediction["decision"]) is not int
            or prediction["decision"] not in (0, 1)
        ):
            return None
    if (
        len({item["observation_id_sha256"] for item in predictions}) != 2
        or len({item["input_id_sha256"] for item in predictions}) != 2
    ):
        return None
    if expected_predictions is not None:
        actual_predictions = {item["observation_id_sha256"]: item for item in predictions}
        if actual_predictions != expected_predictions:
            return None
    if (
        type(value["elapsed_ms"]) not in (float, int)
        or not math.isfinite(value["elapsed_ms"])
        or value["elapsed_ms"] < 0
    ):
        return None
    try:
        validate_measurements(value["measurements"])
    except (TypeError, ValueError):
        return None
    if value["measurements"]["write_failures"] != 0:
        return None
    return value


def _percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    return ordered[low] + (ordered[math.ceil(position)] - ordered[low]) * (position - low)


def summarize_performance(
    peer_results: list[dict[str, Any]], policy: dict[str, Any]
) -> dict[str, Any]:
    """Gate validated peer evidence; two selected rows cannot satisfy the sample floor."""
    passed = [item for item in peer_results if item["status"] == "passed"]
    latencies: dict[str, dict[str, float | int | None]] = {}
    for name in LATENCY_METRICS:
        samples = [sample for peer in passed for sample in peer["measurements"]["samples_ms"][name]]
        latencies[name] = {
            "sample_count": len(samples),
            "p50_ms": _percentile(samples, 0.50) if samples else None,
            "p95_ms": _percentile(samples, 0.95) if samples else None,
        }
    peer_resources = []
    unavailable = []
    for peer in peer_results:
        if peer["status"] != "passed":
            unavailable.append({"peer_id": peer["peer_id"], "reason": "peer_failed"})
            continue
        measurements = peer["measurements"]
        raw = measurements["sdk_raw_stream_bytes"]
        if raw["unavailable_reason"] is not None:
            unavailable.append({"peer_id": peer["peer_id"],
                                "reason": raw["unavailable_reason"]})
        db = measurements["db_bytes"]
        peer_resources.append({
            "peer_id": peer["peer_id"],
            "db_growth_bytes": db["after_sync"] - db["before_open"],
            "db_peak_growth_bytes": max(db.values()) - db["before_open"],
            "sdk_raw_stream_bytes_sent": raw["sent_delta"],
            "sdk_raw_stream_bytes_received": raw["received_delta"],
        })
    write_failures = sum(
        item["measurements"]["write_failures"] if item["status"] == "passed"
        else item["write_failures"] for item in peer_results
    )
    enough = all(
        metric["sample_count"] >= policy["min_samples_per_latency_metric"]
        for metric in latencies.values()
    )
    under_ceiling = all(
        latencies[name]["p95_ms"] is not None
        and latencies[name]["p95_ms"] <= ceiling
        for name, ceiling in policy["p95_ms_ceilings"].items()
    )
    resource_limits_met = write_failures <= policy["max_write_failures"] and all(
        0 <= peer["db_growth_bytes"]
        and peer["db_peak_growth_bytes"] <= policy["max_db_growth_bytes"]
        and (peer["sdk_raw_stream_bytes_sent"] is None or peer["sdk_raw_stream_bytes_sent"] <= policy["max_sdk_raw_stream_bytes_sent"])
        and (peer["sdk_raw_stream_bytes_received"] is None or peer["sdk_raw_stream_bytes_received"] <= policy["max_sdk_raw_stream_bytes_received"])
        for peer in peer_resources
    )
    latency_exceedances = [
        f"p95_{name}" for name, ceiling in policy["p95_ms_ceilings"].items()
        if latencies[name]["p95_ms"] is not None and latencies[name]["p95_ms"] > ceiling
    ]
    threshold_violations = []
    if write_failures > policy["max_write_failures"]:
        threshold_violations.append("write_failures")
    for peer in peer_resources:
        if peer["db_growth_bytes"] < 0 or peer["db_peak_growth_bytes"] > policy["max_db_growth_bytes"]:
            threshold_violations.append(f"{peer['peer_id']}:db_peak_growth_bytes")
        for field in ("sdk_raw_stream_bytes_sent", "sdk_raw_stream_bytes_received"):
            count = peer[field]
            if count is not None and count > policy[f"max_{field}"]:
                threshold_violations.append(f"{peer['peer_id']}:{field}")
    if threshold_violations:
        status = "failed"
    elif unavailable and policy["require_sdk_raw_stream_counters"]:
        status = "unavailable"
    elif not enough:
        status = "insufficient_samples"
    elif not under_ceiling or not resource_limits_met:
        status = "failed"
    else:
        status = "passed"
    return {
        "status": status,
        "closure_ready": status == "passed" and len(passed) == len(peer_results),
        "sample_sufficiency": "sufficient" if enough else "insufficient_samples",
        "latencies": latencies,
        "write_failures": write_failures,
        "peer_resources": peer_resources,
        "unavailable": unavailable,
        "threshold_violations": threshold_violations,
        "observed_latency_exceedances": latency_exceedances,
        "latency_exceedances_provisional": not enough,
        "basis": "provisional_linux_lab_ceiling",
        "latency_scope": "rehearsal_cycle_includes_reopen_replay_sync_start_and_polling",
    }


async def _launch_peer(
    peer_runner_path: Path,
    scenario_path: Path,
    model_path: Path,
    cohort_path: Path,
    store_root: Path,
    peer: dict[str, Any],
    topology: dict[str, str | int],
    expected_predictions: dict[str, dict[str, Any]],
    expected_sdk_digest: str,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(peer_runner_path),
        "--scenario",
        str(scenario_path),
        "--model",
        str(model_path),
        "--cohort",
        str(cohort_path),
        "--stores",
        str(store_root),
        "--peer-id",
        peer["peer_id"],
        "--mode",
        str(topology["mode"]),
        "--listen-interface",
        str(topology["listen_interface"]),
        "--listen-port",
        str(topology["listen_port"]),
        "--neighbor-host",
        str(topology["neighbor_host"]),
        "--neighbor-port",
        str(topology["neighbor_port"]),
    ]
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1"},
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=360)
    except TimeoutError:
        process.kill()
        await process.communicate()
        return {"status": "failed", "peer_id": peer["peer_id"], "error_type": "TimeoutError",
                "write_failures": 0}
    result = _safe_worker_result(stdout)
    if result is not None:
        result = _validated_result(
            result,
            peer["peer_id"],
            topology,
            expected_predictions,
            expected_sdk_digest,
            hashlib.sha256(peer["device_id"].encode()).hexdigest(),
        )
    if process.returncode != 0 or result is None:
        return {
            "status": "failed",
            "peer_id": peer["peer_id"],
            "error_type": result.get("error_type", "WorkerProtocolError")
            if result
            else "WorkerProtocolError",
            "write_failures": result.get("write_failures", 0) if result else 0,
        }
    return result


def _store_digest(store: Path) -> str:
    entries = {
        path.relative_to(store).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(store.rglob("*"))
        if path.is_file()
    }
    return digest_bytes(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())


def _stage_inputs(root: Path, scenario: Path, model: Path, cohort: Path) -> tuple[Path, Path, Path]:
    """Freeze source bytes before validation and before either peer is launched."""
    root.mkdir()
    destinations = tuple(root / name for name in ("scenario.json", "model.json", "cohort.json"))
    for source, destination in zip((scenario, model, cohort), destinations, strict=True):
        destination.write_bytes(source.read_bytes())
        destination.chmod(0o444)
    return destinations


def _stage_code(
    root: Path, runner: Path, peer: Path, contracts: Path
) -> tuple[Path, dict[str, str]]:
    """Run children from read-only copies and retain pre-launch source hashes."""
    root.mkdir()
    hashes: dict[str, str] = {}
    for key, source in zip(CODE_HASH_KEYS, (runner, peer, contracts), strict=True):
        content = source.read_bytes()
        destination = root / source.name
        destination.write_bytes(content)
        destination.chmod(0o444)
        hashes[key] = digest_bytes(content)
    return root / peer.name, hashes


def _verify_code_unchanged(
    sources: Sequence[Path], staged_root: Path, hashes: dict[str, str]
) -> None:
    for key, source in zip(CODE_HASH_KEYS, sources, strict=True):
        expected = hashes[key]
        if (
            digest_bytes(source.read_bytes()) != expected
            or digest_bytes((staged_root / source.name).read_bytes()) != expected
        ):
            raise RunIntegrityError("runner or peer code changed during the run")


def _verify_startup_source(sources: Sequence[Path], startup_hashes: Sequence[str]) -> None:
    if len(sources) != len(startup_hashes) or any(
        digest_bytes(source.read_bytes()) != expected
        for source, expected in zip(sources, startup_hashes, strict=True)
    ):
        raise RunIntegrityError("source changed after parent module import")


async def run(options: argparse.Namespace) -> dict[str, Any]:
    _verify_startup_source(CODE_SOURCES, STARTUP_SOURCE_SHA256)
    with tempfile.TemporaryDirectory(prefix="edge-ditto-run-") as temporary_root:
        temporary = Path(temporary_root)
        staged_peer, code_hashes = _stage_code(temporary / "code", *CODE_SOURCES)
        if tuple(code_hashes[key] for key in CODE_HASH_KEYS) != STARTUP_SOURCE_SHA256:
            raise RunIntegrityError("staged code differs from parent startup code")
        scenario_path, model_path, cohort_path = _stage_inputs(
            temporary / "inputs", options.scenario, options.model, options.cohort
        )
        scenario_bytes = scenario_path.read_bytes()
        scenario = validate_scenario(parse_json_bytes(scenario_bytes))
        model, cohort = load_pinned_artifacts(scenario, model_path, cohort_path)
        scores = verify_parity(model, cohort)
        selected = [cohort["rows"][engine_id - 1] for engine_id in scenario["cohort"]["engine_ids"]]
        if len(scores) != 100 or len(selected) != 2:
            raise ValueError("preflight did not validate all 100 rows and the two-peer assignment")
        sdk_distribution_sha256 = installed_ditto_digest()
        require_approved_sdk(scenario, sdk_distribution_sha256)

        options.output.mkdir(parents=True, exist_ok=False)
        ports = _free_ports()
        topologies = [
            peer_transport("loopback", None, ports[index], None, ports[1 - index])
            for index in range(2)
        ]
        expected_predictions = {
            hashlib.sha256(document["_id"].encode()).hexdigest(): {
                "observation_id_sha256": hashlib.sha256(document["_id"].encode()).hexdigest(),
                "input_id_sha256": document["input_id_sha256"],
                "probability": document["probability"],
                "decision": document["decision"],
            }
            for peer in scenario["peers"]
            for document in (
                observation_document(scenario, peer, model, cohort, scores[peer["engine_id"]]),
            )
        }
        store_root = temporary / "stores"
        store_root.mkdir()
        for peer in scenario["peers"]:
            (store_root / peer["peer_id"]).mkdir()
        launches = [
            _launch_peer(
                staged_peer,
                scenario_path,
                model_path,
                cohort_path,
                store_root,
                scenario["peers"][index],
                topologies[index],
                expected_predictions,
                sdk_distribution_sha256,
            )
            for index in range(2)
        ]
        peer_results = await asyncio.gather(*launches)
        store_hashes = {
            peer["peer_id"]: _store_digest(store_root / peer["peer_id"])
            for peer in scenario["peers"]
        }
        _verify_code_unchanged(CODE_SOURCES, staged_peer.parent, code_hashes)
    status = "passed" if all(item.get("status") == "passed" for item in peer_results) else "failed"
    performance = summarize_performance(peer_results, scenario["metrics_policy"])
    for item in peer_results:
        safe_path = options.output / "peer-results" / f"{item['peer_id']}.json"
        safe_path.parent.mkdir(exist_ok=True)
        safe_path.write_text(
            json.dumps(item, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )

    files = {}
    for path in sorted(options.output.rglob("*")):
        if path.is_file():
            files[path.relative_to(options.output).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    evidence = {
        "schema_version": 1,
        "run_id": str(uuid.uuid4()),
        "scenario_id": scenario["scenario_id"],
        "scenario_sha256": digest_bytes(scenario_bytes),
        "artifact_hashes": {
            "model_file_sha256": scenario["model"]["file_sha256"],
            "model_payload_sha256": model["sha256"],
            "cohort_file_sha256": scenario["cohort"]["file_sha256"],
            "cohort_payload_sha256": cohort["sha256"],
            "sdk_distribution_sha256": sdk_distribution_sha256,
        },
        "preflight": {
            "status": "passed",
            "parity_rows": len(scores),
            "selected_engine_ids": [row["engine_id"] for row in selected],
        },
        "topology": {
            "transport": "static_tcp",
            "mode": "loopback",
            "peer_count": 2,
            "peers": topologies,
        },
        "source_timestamps_available": False,
        "source_timestamp_note": "The frozen FD001 endpoint cohort contains no event timestamp; none was inferred.",
        "sdk_integration_verified": status == "passed",
        "metrics_policy": scenario["metrics_policy"],
        "performance": performance,
        "eng184_closure_ready": status == "passed" and performance["closure_ready"],
        "status": status,
        "performance_status": performance["status"],
        "peers": peer_results,
        "ephemeral_store_sha256": store_hashes,
        "files_sha256": files,
        "finished_at_utc": datetime.now(UTC).isoformat(),
    }
    manifest = options.output / "run-manifest.json"
    manifest.write_text(
        json.dumps(evidence, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    index = {
        "schema_version": 1,
        "run_id": evidence["run_id"],
        "status": status,
        "run_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "performance_status": performance["status"],
        "scenario_sha256": evidence["scenario_sha256"],
        **code_hashes,
        "protocol_sha256": hashlib.sha256((HERE / "protocol.md").read_bytes()).hexdigest(),
    }
    (options.output / "run-index.json").write_text(
        json.dumps(index, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"run_id": evidence["run_id"], "status": status, "artifact_count": len(files) + 1},
            sort_keys=True,
        )
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    try:
        evidence = asyncio.run(run(options))
    except RunIntegrityError:
        print(json.dumps({"status": "integrity_failed", "error_type": "RunIntegrityError"}))
        return 2
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(
            json.dumps(
                {"status": "preflight_failed", "error_type": type(error).__name__}, sort_keys=True
            )
        )
        return 2
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
