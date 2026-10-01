"""Strict contracts and deterministic inference for the N=2 Ditto pilot."""

from __future__ import annotations

import hashlib
import importlib.metadata
import ipaddress
import json
import math
import re
import struct
import uuid
from pathlib import Path
from typing import Any

HASH = re.compile(r"^[0-9a-f]{64}$")
PEER_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
# Independent of the supplied scenario and its artifact pins. This is the
# reviewed canonical content of scenario-n2.json, including both artifact hashes.
FROZEN_SDK_DISTRIBUTION_SHA256 = "d7dfdea1ba6c0a02fd772e923a5cc46362b036e49d4c05371622d63a21bb3990"
FROZEN_N2_SCENARIO_SHA256 = "5e7dc164c1f4625b27b75ef32a42fe34187f30a18134926f21ee37ea4d95bbd3"
LATENCY_METRICS = (
    "selected_row_inference", "first_local_write_query", "peer_delivery", "end_to_end"
)
RAW_COUNTER_UNAVAILABLE_REASONS = {
    "query_failed", "counter_missing", "schema_unexpected", "counter_reset", "series_changed"
}
RAW_STREAM_KEYS = {
    "ditto.stream.raw_bytes_sent": "sent",
    "ditto.stream.raw_bytes_received": "received",
}
DNS_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))*$"
)
WINDOW = 20
CHANNELS = 24
FEATURES = WINDOW * CHANNELS
MODEL_KIND = "fd001_scaled_logistic"
COHORT_KIND = "fd001_official_test_endpoints"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def payload_digest(payload: dict[str, Any]) -> str:
    return digest_bytes(
        canonical_bytes({key: value for key, value in payload.items() if key != "sha256"})
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON object contains a duplicate key")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    return parse_json_bytes(path.read_bytes())


def parse_json_bytes(data: bytes) -> dict[str, Any]:
    value = json.loads(
        data.decode("utf-8"),
        parse_constant=lambda item: (_ for _ in ()).throw(ValueError(item)),
        object_pairs_hook=_unique_object,
    )
    if not isinstance(value, dict):
        raise TypeError("JSON root must be an object")
    return value


def validate_scenario(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "scenario_id",
        "database_id",
        "sdk_distribution_sha256",
        "model",
        "cohort",
        "peers",
        "topology",
        "sync_timeout_seconds",
        "metrics_policy",
    }
    if (
        set(value) != expected
        or type(value.get("schema_version")) is not int
        or value["schema_version"] != 2
    ):
        raise ValueError("scenario fields or version are invalid")
    if not isinstance(value["scenario_id"], str) or not value["scenario_id"]:
        raise ValueError("scenario_id must be a nonempty string")
    try:
        uuid.UUID(value["database_id"])
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("database_id must be a UUID") from error
    if value["sdk_distribution_sha256"] != FROZEN_SDK_DISTRIBUTION_SHA256:
        raise ValueError("SDK distribution digest differs from the approved edge-lab fixture")
    model = value["model"]
    cohort = value["cohort"]
    if not isinstance(model, dict) or set(model) != {"kind", "file_sha256", "payload_sha256"}:
        raise ValueError("model pin is invalid")
    if not isinstance(cohort, dict) or set(cohort) != {
        "kind",
        "file_sha256",
        "payload_sha256",
        "engine_ids",
    }:
        raise ValueError("cohort pin is invalid")
    if model["kind"] != MODEL_KIND or cohort["kind"] != COHORT_KIND:
        raise ValueError("scenario model or cohort kind is unsupported")
    if any(
        not isinstance(model[key], str) or not HASH.fullmatch(model[key])
        for key in ("file_sha256", "payload_sha256")
    ):
        raise ValueError("model hashes are invalid")
    if any(
        not isinstance(cohort[key], str) or not HASH.fullmatch(cohort[key])
        for key in ("file_sha256", "payload_sha256")
    ):
        raise ValueError("cohort hashes are invalid")
    engine_ids = cohort["engine_ids"]
    if (
        not isinstance(engine_ids, list)
        or any(type(item) is not int for item in engine_ids)
        or engine_ids != [1, 2]
    ):
        raise ValueError("N=2 scenario must assign the first two frozen cohort rows")
    peers = value["peers"]
    if not isinstance(peers, list) or len(peers) != 2:
        raise ValueError("exactly two peers are required")
    if any(
        set(peer) != {"peer_id", "device_id", "engine_id"}
        for peer in peers
        if isinstance(peer, dict)
    ) or any(not isinstance(peer, dict) for peer in peers):
        raise ValueError("peer fields are invalid")
    if (
        any(type(peer["engine_id"]) is not int for peer in peers)
        or [peer["engine_id"] for peer in peers] != engine_ids
    ):
        raise ValueError("each peer must receive one declared cohort row")
    for field in ("peer_id", "device_id"):
        values = [peer[field] for peer in peers]
        if any(not isinstance(item, str) or not item for item in values) or len(set(values)) != 2:
            raise ValueError(f"peer {field} values must be distinct strings")
    if any(PEER_ID.fullmatch(peer["peer_id"]) is None for peer in peers):
        raise ValueError("peer_id must be a safe lowercase path component")
    topology = value["topology"]
    if topology != {
        "transport": "static_tcp",
        "edges": [[peers[0]["peer_id"], peers[1]["peer_id"]]],
    }:
        raise ValueError("N=2 topology must declare one static TCP edge")
    timeout = value["sync_timeout_seconds"]
    if type(timeout) is not int or not 1 <= timeout <= 300:
        raise ValueError("sync_timeout_seconds must be an integer in [1, 300]")
    validate_metrics_policy(value["metrics_policy"])
    if digest_bytes(canonical_bytes(value)) != FROZEN_N2_SCENARIO_SHA256:
        raise ValueError("scenario differs from the frozen N=2 scenario")
    return value


def validate_metrics_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "min_samples_per_latency_metric", "p95_ms_ceilings",
        "max_write_failures", "max_db_growth_bytes", "max_sdk_raw_stream_bytes_sent",
        "max_sdk_raw_stream_bytes_received", "require_sdk_raw_stream_counters",
    }:
        raise ValueError("metrics policy fields are invalid")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("metrics policy version is invalid")
    minimum = value["min_samples_per_latency_metric"]
    if type(minimum) is not int or not 3 <= minimum <= 10000:
        raise ValueError("metrics policy minimum sample count is invalid")
    ceilings = value["p95_ms_ceilings"]
    if not isinstance(ceilings, dict) or set(ceilings) != set(LATENCY_METRICS):
        raise ValueError("metrics policy latency ceilings are invalid")
    if any(type(item) is not int or not 1 <= item <= 360000 for item in ceilings.values()):
        raise ValueError("metrics policy latency ceilings are invalid")
    for key in ("max_write_failures", "max_db_growth_bytes", "max_sdk_raw_stream_bytes_sent",
                "max_sdk_raw_stream_bytes_received"):
        item = value[key]
        if type(item) is not int or not 0 <= item <= 1 << 40:
            raise ValueError(f"metrics policy {key} is invalid")
    if type(value["require_sdk_raw_stream_counters"]) is not bool:
        raise ValueError("metrics policy counter requirement is invalid")
    return value


def validate_measurements(value: Any) -> dict[str, Any]:
    """Validate bounded, per-peer raw evidence before aggregation or gating."""
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "samples_ms", "write_failures", "db_bytes", "sdk_raw_stream_bytes"
    } or type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("peer measurements fields or version are invalid")
    samples = value["samples_ms"]
    if not isinstance(samples, dict) or set(samples) != set(LATENCY_METRICS):
        raise ValueError("peer latency samples are invalid")
    for name in LATENCY_METRICS:
        values = samples[name]
        # The frozen N=2 scenario scores exactly one selected row on each peer.
        if (not isinstance(values, list) or len(values) != 1 or
                any(type(item) not in (int, float) or not math.isfinite(item)
                    or not 0 <= item <= 360000 for item in values)):
            raise ValueError(f"peer {name} samples are invalid")
    failures = value["write_failures"]
    if type(failures) is not int or not 0 <= failures <= 100:
        raise ValueError("peer write failure count is invalid")
    sizes = value["db_bytes"]
    if not isinstance(sizes, dict) or set(sizes) != {
        "before_open", "after_first_local_query", "after_reopen", "after_sync"
    } or any(type(item) is not int or not 0 <= item <= 1 << 50 for item in sizes.values()):
        raise ValueError("peer database byte checkpoints are invalid")
    counters = value["sdk_raw_stream_bytes"]
    if not isinstance(counters, dict) or set(counters) != {
        "sent_delta", "received_delta", "unavailable_reason"
    }:
        raise ValueError("peer raw stream byte counters are invalid")
    reason = counters["unavailable_reason"]
    if reason is None:
        if any(type(counters[key]) is not int or not 0 <= counters[key] <= 1 << 50
               for key in ("sent_delta", "received_delta")):
            raise ValueError("peer raw stream byte counters are invalid")
    elif (type(reason) is not str or reason not in RAW_COUNTER_UNAVAILABLE_REASONS
          or counters["sent_delta"] is not None or counters["received_delta"] is not None):
        raise ValueError("peer raw stream byte unavailable reason is invalid")
    return value


def raw_stream_series(rows: Any, *, allow_missing: bool) -> dict[str, dict[str, int]]:
    """Retain bounded label series so a reset cannot hide behind another series."""
    if not isinstance(rows, list) or len(rows) > 512:
        raise ValueError("schema_unexpected")
    series_by_direction: dict[str, dict[str, int]] = {"sent": {}, "received": {}}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not {"key", "labels", "current"} <= set(row) or (
            set(row) - {"key", "labels", "current", "_id"}
        ):
            raise ValueError("schema_unexpected")
        key = row["key"]
        labels = row["labels"]
        count = row["current"]
        if not isinstance(key, str) or key not in RAW_STREAM_KEYS or not isinstance(labels, dict) or len(labels) > 16 or any(
            not isinstance(label, str) or len(label) > 64
            or not isinstance(value, str) or len(value) > 128
            for label, value in labels.items()
        ) or type(count) is not int or not 0 <= count <= 1 << 50:
            raise ValueError("schema_unexpected")
        name = RAW_STREAM_KEYS[key]
        identity = json.dumps(labels, sort_keys=True, separators=(",", ":"))
        if identity in series_by_direction[name]:
            raise ValueError("schema_unexpected")
        series_by_direction[name][identity] = count
        if sum(series_by_direction[name].values()) > 1 << 50:
            raise ValueError("schema_unexpected")
        seen.add(name)
    if not allow_missing and seen != {"sent", "received"}:
        raise ValueError("counter_missing")
    return series_by_direction


def aggregate_raw_stream_counters(rows: Any, *, allow_missing: bool) -> dict[str, int]:
    """Summarize validated series for diagnostics; deltas use raw_stream_series."""
    series = raw_stream_series(rows, allow_missing=allow_missing)
    return {name: sum(counts.values()) for name, counts in series.items()}


def peer_transport(
    mode: str,
    listen_interface: str | None,
    listen_port: int,
    neighbor_host: str | None,
    neighbor_port: int,
) -> dict[str, str | int]:
    """Validate and normalize the endpoint settings a peer will expose/use."""
    if mode not in {"loopback", "distributed"}:
        raise ValueError("peer mode must be loopback or distributed")
    for name, value in (("listen_port", listen_port), ("neighbor_port", neighbor_port)):
        if type(value) is not int or not 1 <= value <= 65535:
            raise ValueError(f"{name} must be an integer in [1, 65535]")

    if mode == "loopback":
        interface = listen_interface or "127.0.0.1"
        host = neighbor_host or "127.0.0.1"
        if interface != "127.0.0.1" or host != "127.0.0.1":
            raise ValueError("loopback peers must use 127.0.0.1 endpoints")
    else:
        if listen_interface != "0.0.0.0":
            raise ValueError("distributed peers must listen on 0.0.0.0")
        if not isinstance(neighbor_host, str) or not DNS_HOST.fullmatch(neighbor_host):
            raise ValueError("distributed neighbor_host must be a lowercase DNS hostname")
        try:
            ipaddress.ip_address(neighbor_host)
        except ValueError:
            pass
        else:
            raise ValueError("distributed neighbor_host must use a DNS alias, not an IP address")
        interface = listen_interface
        host = neighbor_host

    return {
        "mode": mode,
        "listen_interface": interface,
        "listen_port": listen_port,
        "neighbor_host": host,
        "neighbor_port": neighbor_port,
    }


def load_pinned_artifacts(
    scenario: dict[str, Any], model_path: Path, cohort_path: Path
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_bytes, cohort_bytes = model_path.read_bytes(), cohort_path.read_bytes()
    model, cohort = parse_json_bytes(model_bytes), parse_json_bytes(cohort_bytes)
    if (
        digest_bytes(model_bytes) != scenario["model"]["file_sha256"]
        or digest_bytes(cohort_bytes) != scenario["cohort"]["file_sha256"]
    ):
        raise ValueError("artifact file digest does not match scenario pin")
    if (
        model.get("sha256") != payload_digest(model)
        or model.get("sha256") != scenario["model"]["payload_sha256"]
    ):
        raise ValueError("model payload digest does not match scenario pin")
    if (
        cohort.get("sha256") != payload_digest(cohort)
        or cohort.get("sha256") != scenario["cohort"]["payload_sha256"]
    ):
        raise ValueError("cohort payload digest does not match scenario pin")
    validate_artifacts(model, cohort)
    return model, cohort


def distribution_digest(distribution: importlib.metadata.Distribution) -> str:
    """Hash the installed Ditto distribution file contents, independent of mtimes."""
    if not distribution.files:
        raise ValueError("Ditto distribution file inventory is unavailable")
    entries: dict[str, str] = {}
    for relative in sorted(distribution.files, key=str):
        name = relative.as_posix()
        if "__pycache__" in relative.parts or name.endswith(".pyc"):
            continue
        path = Path(distribution.locate_file(relative))
        if not path.is_file():
            raise ValueError("Ditto distribution file is missing")
        entries[name] = digest_bytes(path.read_bytes())
    if not entries or not any(name.startswith("ditto/") for name in entries):
        raise ValueError("Ditto distribution package files are unavailable")
    return digest_bytes(canonical_bytes(entries))


def installed_ditto_digest() -> str:
    candidates = importlib.metadata.packages_distributions().get("ditto", [])
    if len(candidates) != 1:
        raise ValueError("Ditto distribution identity is ambiguous")
    return distribution_digest(importlib.metadata.distribution(candidates[0]))


def require_approved_sdk(scenario: dict[str, Any], observed_sha256: str) -> None:
    if observed_sha256 != scenario["sdk_distribution_sha256"]:
        raise ValueError("installed Ditto SDK differs from the approved scenario fixture")


def validate_artifacts(model: dict[str, Any], cohort: dict[str, Any]) -> None:
    if (
        model.get("schema_version") != 2
        or model.get("kind") != MODEL_KIND
        or model.get("window_cycles") != WINDOW
        or model.get("channels_per_cycle") != CHANNELS
        or model.get("feature_count") != FEATURES
    ):
        raise ValueError("model schema is unsupported")
    if (
        cohort.get("schema_version") != 2
        or cohort.get("kind") != COHORT_KIND
        or cohort.get("model_sha256") != model["sha256"]
    ):
        raise ValueError("cohort schema or model linkage is invalid")
    for key, count in (
        ("scaler_mean", FEATURES),
        ("scaler_scale", FEATURES),
        ("coefficients", FEATURES),
    ):
        values = model.get(key)
        if (
            not isinstance(values, list)
            or len(values) != count
            or any(not finite(x) for x in values)
        ):
            raise ValueError(f"model {key} is invalid")
    if any(value <= 0 for value in model["scaler_scale"]) or not finite(model.get("intercept")):
        raise ValueError("model scaler or intercept is invalid")
    threshold = model.get("threshold")
    if not finite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("model threshold is invalid")
    rows = cohort.get("rows")
    if not isinstance(rows, list) or len(rows) != 100:
        raise ValueError("expected the frozen 100-row FD001 cohort")
    for engine_id, row in enumerate(rows, 1):
        if not isinstance(row, dict) or row.get("engine_id") != engine_id:
            raise ValueError("cohort engine IDs must be ordered 1..100")
        features = row.get("features")
        if (
            not isinstance(features, list)
            or len(features) != FEATURES
            or any(not finite(x) for x in features)
        ):
            raise ValueError(f"cohort features are invalid for engine {engine_id}")
        expected = row.get("expected_probability")
        if (
            not finite(expected)
            or not 0 <= expected <= 1
            or type(row.get("expected_decision")) is not int
            or row["expected_decision"] not in (0, 1)
            or type(row.get("rul_label")) is not int
            or row["rul_label"] not in (0, 1)
        ):
            raise ValueError(f"cohort parity target is invalid for engine {engine_id}")


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def float32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def infer(model: dict[str, Any], row: dict[str, Any]) -> float:
    transformed = (
        float32(float32(value - float32(mean)) / scale)
        for value, mean, scale in zip(
            row["features"], model["scaler_mean"], model["scaler_scale"], strict=True
        )
    )
    score = math.fsum(
        (
            model["intercept"],
            *(
                weight * value
                for weight, value in zip(model["coefficients"], transformed, strict=True)
            ),
        )
    )
    if score >= 0:
        return 1.0 / (1.0 + math.exp(-score))
    exp_score = math.exp(score)
    return exp_score / (1.0 + exp_score)


def verify_parity(
    model: dict[str, Any], cohort: dict[str, Any], tolerance: float = 1e-6
) -> dict[int, float]:
    scores: dict[int, float] = {}
    for row in cohort["rows"]:
        score = infer(model, row)
        if (
            abs(score - row["expected_probability"]) > tolerance
            or int(score >= model["threshold"]) != row["expected_decision"]
        ):
            raise ValueError(f"prediction parity failed for engine {row['engine_id']}")
        scores[row["engine_id"]] = score
    return scores


def observation_id(device_id: str, input_id_sha256: str, model_sha256: str) -> str:
    return digest_bytes(
        canonical_bytes(
            {
                "device_id": device_id,
                "input_id_sha256": input_id_sha256,
                "model_sha256": model_sha256,
            }
        )
    )


def observation_document(
    scenario: dict[str, Any],
    peer: dict[str, Any],
    model: dict[str, Any],
    cohort: dict[str, Any],
    score: float,
) -> dict[str, Any]:
    engine_id = peer["engine_id"]
    input_id_sha256 = digest_bytes(f"{cohort['sha256']}:engine:{engine_id}".encode())
    return {
        "_id": observation_id(peer["device_id"], input_id_sha256, model["sha256"]),
        "schema_version": 1,
        "scenario_id": scenario["scenario_id"],
        "device_id": peer["device_id"],
        "input_id_sha256": input_id_sha256,
        "model_kind": model["kind"],
        "model_sha256": model["sha256"],
        "cohort_sha256": cohort["sha256"],
        "engine_id": engine_id,
        "probability": score,
        "decision": int(score >= model["threshold"]),
    }


def assert_same_immutable_content(existing: dict[str, Any], proposed: dict[str, Any]) -> None:
    if existing != proposed:
        raise ValueError("same-ID observation content conflict")
