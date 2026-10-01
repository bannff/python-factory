"""Single-process real Ditto peer; invoked only by the N=2 parent runner."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

from contracts import (
    raw_stream_series,
    assert_same_immutable_content,
    infer,
    installed_ditto_digest,
    load_pinned_artifacts,
    observation_document,
    peer_transport,
    read_json,
    require_approved_sdk,
    validate_scenario,
    verify_parity,
)

LICENSE_FILE = Path("/run/secrets/ditto-offline-license")
COLLECTION = "edge_observations"
RAW_COUNTER_QUERY = (
    "SELECT key, labels, current FROM system:metrics WHERE key IN "
    "('ditto.stream.raw_bytes_sent', 'ditto.stream.raw_bytes_received')"
)


class LocalWriteFailure(RuntimeError):
    """Sanitized signal that an SDK insert failed."""


def _store_bytes(root: Path) -> int:
    total = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("SDK store contains a symlink")
        if path.is_file():
            total += path.stat().st_size
    return total


async def _raw_counters(peer: Any, *, allow_missing: bool) -> tuple[dict[str, dict[str, int]] | None, str | None]:
    try:
        rows = _query_values(await peer.store.execute(RAW_COUNTER_QUERY))
    except Exception:  # noqa: BLE001 - only a bounded unavailability reason crosses the worker boundary.
        return None, "query_failed"
    try:
        return raw_stream_series(rows, allow_missing=allow_missing), None
    except (TypeError, ValueError) as error:
        reason = str(error)
        return None, reason if reason in {"counter_missing", "schema_unexpected"} else "schema_unexpected"


def _raw_delta(before: dict[str, dict[str, int]] | None,
               after: dict[str, dict[str, int]] | None,
               reason: str | None) -> dict[str, int | str | None]:
    if reason is None and before is not None and after is not None:
        deltas = {}
        for name in ("sent", "received"):
            if set(before[name]) - set(after[name]):
                reason = "series_changed"
                break
            if any(after[name][series] < count for series, count in before[name].items()):
                reason = "counter_reset"
                break
            deltas[name] = sum(count - before[name].get(series, 0)
                               for series, count in after[name].items())
        if reason is None:
            return {"sent_delta": deltas["sent"], "received_delta": deltas["received"],
                    "unavailable_reason": None}
    return {"sent_delta": None, "received_delta": None,
            "unavailable_reason": reason or "schema_unexpected"}


def _offline_license() -> str:
    try:
        token = LICENSE_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError("offline license unavailable") from error
    if not token:
        raise RuntimeError("offline license unavailable")
    return token


def _query_values(result: Any) -> list[dict[str, Any]]:
    try:
        return [dict(item.value) for item in result]
    finally:
        result.close()


async def _documents(peer: Any) -> dict[str, dict[str, Any]]:
    return {
        str(value["_id"]): value
        for value in _query_values(await peer.store.execute(f"SELECT * FROM {COLLECTION}"))
    }


async def _insert(peer: Any, document: dict[str, Any]) -> None:
    try:
        result = await peer.store.execute(
            f"INSERT INTO {COLLECTION} DOCUMENTS (:document) ON ID CONFLICT DO NOTHING",
            {"document": document},
        )
        result.close()
    except Exception as error:  # noqa: BLE001 - redact SDK details at the process boundary.
        raise LocalWriteFailure("local observation insert failed") from error


def _verify_document(value: dict[str, Any], expected: dict[str, Any]) -> None:
    assert_same_immutable_content(value, expected)
    if (
        type(value.get("schema_version")) is not int
        or type(value.get("engine_id")) is not int
        or type(value.get("decision")) is not int
        or type(value.get("probability")) not in (int, float)
    ):
        raise ValueError("stored observation types are invalid")


async def run_peer(options: argparse.Namespace) -> dict[str, Any]:
    transport_config = peer_transport(
        options.mode,
        options.listen_interface,
        options.port,
        options.neighbor_host,
        options.neighbor_port,
    )
    scenario = validate_scenario(read_json(options.scenario))
    model, cohort = load_pinned_artifacts(scenario, options.model, options.cohort)
    scores = verify_parity(model, cohort)
    peer_spec = next(item for item in scenario["peers"] if item["peer_id"] == options.peer_id)
    counterpart = next(item for item in scenario["peers"] if item["peer_id"] != options.peer_id)
    neighbor_document = observation_document(
        scenario, counterpart, model, cohort, scores[counterpart["engine_id"]]
    )
    license_token = _offline_license()
    sdk_distribution_sha256 = installed_ditto_digest()
    require_approved_sdk(scenario, sdk_distribution_sha256)

    from ditto import Ditto, DittoConfig, DittoConfigConnect, DittoTransportConfig, __version__

    store_path = options.stores / peer_spec["peer_id"]
    store_path.mkdir(parents=True, exist_ok=True)
    db_before_open = _store_bytes(store_path)
    config = DittoConfig(
        database_id=scenario["database_id"],
        connect=DittoConfigConnect.small_peers_only(),
        persistence_directory=str(store_path),
        system_parameters={
            "metrics_exporter_virtual_collection_enabled": True,
            "metrics_exporter_virtual_collection_level": "info",
        },
    )
    peer = await Ditto.open(config)
    started_ns = time.monotonic_ns()
    try:
        peer.set_offline_only_license_token(license_token)
        inference_started_ns = time.monotonic_ns()
        score = infer(model, cohort["rows"][peer_spec["engine_id"] - 1])
        inference_finished_ns = time.monotonic_ns()
        if score != scores[peer_spec["engine_id"]]:
            raise ValueError("selected-row inference differs from validated cohort parity")
        document = observation_document(scenario, peer_spec, model, cohort, score)
        local_write_started_ns = time.monotonic_ns()
        await _insert(peer, document)
        first = await _documents(peer)
        _verify_document(first.get(document["_id"], {}), document)
        first_local_query_finished_ns = time.monotonic_ns()
        db_after_first_local_query = _store_bytes(store_path)
        closing_peer, peer = peer, None
        await closing_peer.close()

        peer = await Ditto.open(config)
        peer.set_offline_only_license_token(license_token)
        reopened = await _documents(peer)
        if len(reopened) != 1:
            raise ValueError("observation did not persist across reopen")
        _verify_document(reopened[document["_id"]], document)
        db_after_reopen = _store_bytes(store_path)
        await _insert(peer, document)
        replayed = await _documents(peer)
        if len(replayed) != 1:
            raise ValueError("post-reopen replay produced duplicate observations")
        _verify_document(replayed[document["_id"]], document)

        transport = DittoTransportConfig()
        transport.listen.tcp.enabled = True
        transport.listen.tcp.interface_ip = transport_config["listen_interface"]
        transport.listen.tcp.port = transport_config["listen_port"]
        transport.connect.tcp_servers.add(
            f"{transport_config['neighbor_host']}:{transport_config['neighbor_port']}"
        )
        peer.transport_config = transport
        subscription = peer.sync.register_subscription(f"SELECT * FROM {COLLECTION}")
        counters_before, counter_reason = await _raw_counters(peer, allow_missing=True)
        try:
            delivery_started_ns = time.monotonic_ns()
            peer.sync.start()
            deadline = time.monotonic() + scenario["sync_timeout_seconds"]
            expected_documents = {
                document["_id"]: document,
                neighbor_document["_id"]: neighbor_document,
            }
            expected_ids = set(expected_documents)
            while time.monotonic() < deadline:
                synced = await _documents(peer)
                if set(synced) == expected_ids:
                    break
                await asyncio.sleep(0.1)
            else:
                raise TimeoutError("peer sync did not converge before timeout")
            for observation_id, expected in expected_documents.items():
                _verify_document(synced[observation_id], expected)
            delivery_finished_ns = time.monotonic_ns()
        finally:
            subscription.cancel()
            subscription.close()

        counters_after = None
        if counter_reason is None:
            counters_after, counter_reason = await _raw_counters(peer, allow_missing=False)
        raw_bytes = _raw_delta(counters_before, counters_after, counter_reason)
        db_after_sync = _store_bytes(store_path)

        return {
            "peer_id": peer_spec["peer_id"],
            "device_id_sha256": hashlib.sha256(peer_spec["device_id"].encode()).hexdigest(),
            "sdk_version": __version__,
            "sdk_distribution_sha256": sdk_distribution_sha256,
            "python_version": platform.python_version(),
            "platform": sys.platform,
            "topology": transport_config,
            "local_persistence": "passed",
            "exact_replay": "passed",
            "synced_observation_count": len(synced),
            "predictions": [
                {
                    "observation_id_sha256": hashlib.sha256(value["_id"].encode()).hexdigest(),
                    "input_id_sha256": value["input_id_sha256"],
                    "probability": value["probability"],
                    "decision": value["decision"],
                }
                for value in sorted(synced.values(), key=lambda item: item["_id"])
            ],
            "elapsed_ms": (time.monotonic_ns() - started_ns) / 1_000_000,
            "measurements": {
                "schema_version": 1,
                "samples_ms": {
                    "selected_row_inference": [(inference_finished_ns - inference_started_ns) / 1_000_000],
                    "first_local_write_query": [(first_local_query_finished_ns - local_write_started_ns) / 1_000_000],
                    "peer_delivery": [(delivery_finished_ns - delivery_started_ns) / 1_000_000],
                    "end_to_end": [(delivery_finished_ns - inference_started_ns) / 1_000_000],
                },
                "write_failures": 0,
                "db_bytes": {
                    "before_open": db_before_open,
                    "after_first_local_query": db_after_first_local_query,
                    "after_reopen": db_after_reopen,
                    "after_sync": db_after_sync,
                },
                "sdk_raw_stream_bytes": raw_bytes,
            },
        }
    finally:
        if peer is not None:
            await peer.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--stores", type=Path, required=True)
    parser.add_argument("--peer-id", required=True)
    parser.add_argument("--mode", choices=("loopback", "distributed"), default="loopback")
    parser.add_argument("--listen-interface")
    parser.add_argument("--port", "--listen-port", dest="port", type=int, required=True)
    parser.add_argument("--neighbor-host")
    parser.add_argument("--neighbor-port", type=int, required=True)
    options = parser.parse_args()
    try:
        result = asyncio.run(run_peer(options))
        print("EDGE_DITTO_RESULT " + json.dumps({"status": "passed", **result}, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 - redact all SDK and input errors at this process boundary.
        # Do not include exception messages: SDK errors may expose config values.
        print(
            "EDGE_DITTO_RESULT "
            + json.dumps({"status": "failed", "error_type": type(error).__name__,
                          "write_failures": int(isinstance(error, LocalWriteFailure))}, sort_keys=True)
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
