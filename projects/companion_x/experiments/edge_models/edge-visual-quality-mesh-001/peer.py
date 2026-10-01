"""Run one image-owning peer; every prediction is computed from local bytes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from records import (
    COLLECTION,
    assert_idempotent,
    make_record,
    validate_next_review,
    validate_record,
    validate_review_history,
)

LICENSE_FILE = Path("/run/secrets/ditto-offline-license")
DNS_NAME = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")


class SyncGateError(TimeoutError):
    """The 60-second remote visibility gate was not evidenced or was exceeded."""


def _read_license() -> str:
    try:
        token = LICENSE_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError("offline license unavailable") from error
    if not token:
        raise RuntimeError("offline license unavailable")
    return token


def validate_options(options: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    if options.peer_id not in {"inspection-a", "inspection-b"}:
        raise ValueError("peer ID is outside the frozen roster")
    if options.listen_interface != "0.0.0.0":
        raise ValueError("mesh peer must listen on 0.0.0.0")
    if type(options.port) is not int or not 1 <= options.port <= 65535:
        raise ValueError("listen port is invalid")
    if type(options.neighbor_port) is not int or not 1 <= options.neighbor_port <= 65535:
        raise ValueError("neighbor port is invalid")
    if options.neighbor_host is None or not DNS_NAME.fullmatch(options.neighbor_host):
        raise ValueError("neighbor host must be a lowercase Sandbox DNS alias")
    try:
        ipaddress.ip_address(options.neighbor_host)
    except ValueError:
        pass
    else:
        raise ValueError("neighbor host must be a DNS alias, not an IP address")
    try:
        UUID(options.database_id)
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("database ID must be a UUID") from error
    data_root = options.images.resolve(strict=True)
    if not data_root.is_dir():
        raise ValueError("image root is not a directory")
    manifest = json.loads(options.manifest.read_text(encoding="utf-8"))
    expected = {"schema_version", "round_id", "assignment_sha256", "model_sha256", "peer_id", "tasks"}
    if type(manifest) is not dict or set(manifest) != expected or manifest.get("schema_version") != 1:
        raise ValueError("peer assignment manifest has an invalid schema")
    if manifest["peer_id"] != options.peer_id or not isinstance(manifest["tasks"], list) or not manifest["tasks"]:
        raise ValueError("peer assignment manifest does not match this peer")
    ids: set[str] = set()
    for task in manifest["tasks"]:
        if type(task) is not dict or set(task) != {
            "task_id", "item_id", "image_id", "owner_peer", "relative_path", "image_sha256"
        }:
            raise ValueError("assigned task schema is invalid")
        if task["owner_peer"] != options.peer_id or not all(
            isinstance(task[key], str) and task[key]
            for key in ("task_id", "item_id", "image_id", "relative_path")
        ):
            raise ValueError("peer received an unowned or malformed task")
        if task["task_id"] in ids:
            raise ValueError("assignment contains duplicate task IDs")
        ids.add(task["task_id"])
        relative = Path(task["relative_path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("task path escapes the local image root")
        path = (data_root / relative).resolve(strict=True)
        if not path.is_relative_to(data_root) or not path.is_file():
            raise ValueError("task source is not a file under the local image root")
        if not re.fullmatch(r"[0-9a-f]{64}", task["image_sha256"]):
            raise ValueError("task image digest is invalid")
    return manifest, {"image_root": data_root}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _query_values(result: Any) -> list[dict[str, Any]]:
    try:
        return [dict(item.value) for item in result]
    finally:
        result.close()


async def _documents(peer: Any) -> dict[str, dict[str, Any]]:
    values = _query_values(await peer.store.execute(f"SELECT * FROM {COLLECTION}"))
    for value in values:
        validate_record(value)
    validate_review_history(values)
    return {str(value["_id"]): value for value in values}


def snapshot_from_documents(
    docs: dict[str, dict[str, Any]], *, round_id: str, peer_id: str,
    inference_count: int, state: str, sdk_device_identity_sha256: str | None = None,
) -> dict[str, Any]:
    """Project only records observed in a live Ditto store read."""
    if state not in {"waiting", "converged", "failed"}:
        raise ValueError("snapshot state is invalid")
    for value in docs.values():
        validate_record(value)
    validate_review_history(list(docs.values()))
    current = {key: value for key, value in docs.items() if value.get("round_id") == round_id}
    joins = {
        peer: ("replicated_record_present" if f"join:{round_id}:{peer}" in current else "waiting")
        for peer in ("inspection-a", "inspection-b")
    }
    results = [value for value in current.values() if value.get("kind") == "result"]
    projection = sorted(
        ({key: value[key] for key in ("_id", "task_id", "image_id", "source_peer", "score", "decision")}
         for value in results),
        key=lambda value: value["_id"],
    )
    review_history = sorted(
        ({key: value[key] for key in ("_id", "task_id", "reviewer_id", "decision", "revision")}
         for value in current.values() if value.get("kind") == "review_decision"),
        key=lambda value: (value["task_id"], value["revision"], value["reviewer_id"]),
    )
    convergence_projection = {"results": projection, "review_decisions": review_history}
    resolved_tasks = {
        value["task_id"] for value in current.values()
        if value.get("kind") == "review_decision"
    }
    review_records = sorted(
        value["_id"] for value in current.values()
        if value.get("kind") == "review_open" and value.get("task_id") not in resolved_tasks
    )
    return {
        "schema_version": 1,
        "type": "edge_visual_mesh_snapshot",
        "round_id": round_id,
        "peer_id": peer_id,
        "sdk_device_identity_sha256": sdk_device_identity_sha256,
        "sdk_device_identity_source": "presence.graph.local_peer.peer_key" if sdk_device_identity_sha256 else "unknown",
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "stale_after_seconds": 5,
        "state": state,
        "evidence": "ditto_store_read" if state != "failed" else "unknown",
        "local_inference_count": inference_count,
        "replicated_result_count": sum(value.get("source_peer") != peer_id for value in results),
        "synced_result_count": len(results),
        "join_record_state": joins,
        "sdk_connection_state": "unknown",
        "review_queue_count": len(review_records),
        "review_queue_sha256": _sha(json.dumps(review_records, separators=(",", ":")).encode()),
        "result_projection_sha256": _sha(json.dumps(convergence_projection, sort_keys=True, separators=(",", ":")).encode()),
        "review_decision_count": len(review_history),
        "review_history": review_history,
    }


def append_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n")
        output.flush()


def require_replay_ready(expected_result_ids: set[str], prior_result_ids: set[str]) -> None:
    if not expected_result_ids.issubset(prior_result_ids):
        raise ValueError("restart replay requires all frozen results in the persistent store")


def require_fresh_sync_round(prior_result_ids: set[str]) -> None:
    if prior_result_ids:
        raise ValueError("first-run sync gate requires no persisted results for this round")


def verify_replay_result(
    expected_result_ids: set[str], prior_result_ids: set[str],
    final_result_ids: set[str], write_counts: dict[str, int],
) -> int:
    """Prove a restart added no record and no logical result."""
    require_replay_ready(expected_result_ids, prior_result_ids)
    if not expected_result_ids.issubset(final_result_ids):
        raise ValueError("restart replay lost a frozen result")
    new_results = len(final_result_ids - prior_result_ids)
    if write_counts.get("new") != 0 or new_results != 0:
        raise ValueError("restart replay produced a new write or logical result")
    if write_counts.get("duplicate", 0) == 0:
        raise ValueError("restart replay did not observe duplicate writes")
    return new_results


def validate_round_sets(
    current: dict[str, dict[str, Any]], *, round_id: str,
    expected_task_ids: set[str], expected_result_ids: set[str],
    expected_claim_ids: set[str], expected_join_ids: set[str],
) -> bool:
    """Require exact non-review event sets; permit only contiguous typed review history."""
    expected_round_ids = {f"round:{round_id}:{round_id}"}
    by_kind = {
        kind: {key for key, value in current.items() if value.get("kind") == kind}
        for kind in ("round", "join", "task_claim", "result", "review_open", "review_decision")
    }
    if by_kind["round"] - expected_round_ids:
        raise ValueError("unexpected round record in this round")
    round_record = current.get(f"round:{round_id}:{round_id}")
    if round_record is not None and (
        set(round_record.get("task_ids", [])) != expected_task_ids
        or round_record.get("task_count") != len(expected_task_ids)
        or round_record.get("peer_ids") != ["inspection-a", "inspection-b"]
    ):
        raise ValueError("round record differs from frozen task or peer roster")
    if by_kind["join"] - expected_join_ids:
        raise ValueError("unexpected join record in this round")
    if by_kind["task_claim"] - expected_claim_ids:
        raise ValueError("unexpected task claim in this round")
    if by_kind["result"] - expected_result_ids:
        raise ValueError("unexpected result in this round")
    expected_review_ids = {
        f"review_open:{round_id}:{value['task_id']}"
        for value in current.values()
        if value.get("kind") == "result" and value.get("decision") == 1
    }
    if by_kind["review_open"] != expected_review_ids:
        if by_kind["review_open"] - expected_review_ids:
            raise ValueError("unexpected review-open record in this round")
        return False
    known_ids = (
        expected_round_ids | expected_join_ids | expected_claim_ids |
        expected_result_ids | expected_review_ids | by_kind["review_decision"]
    )
    if set(current) - known_ids:
        raise ValueError("unexpected typed record in this round")
    return (
        by_kind["round"] == expected_round_ids
        and by_kind["join"] == expected_join_ids
        and by_kind["task_claim"] == expected_claim_ids
        and by_kind["result"] == expected_result_ids
    )


def validate_round_links(
    current: dict[str, dict[str, Any]], *, round_id: str,
    tasks: dict[str, dict[str, Any]], model_sha: str, assignment_sha: str,
) -> None:
    """Bind converged documents to the assignment and each other."""
    roster = {"inspection-a", "inspection-b"}
    round_record = current[f"round:{round_id}:{round_id}"]
    if (
        round_record["model_sha256"] != model_sha
        or round_record["assignment_sha256"] != assignment_sha
    ):
        raise ValueError("round hashes differ from frozen assignment or model")
    for peer_id in roster:
        join = current[f"join:{round_id}:{peer_id}"]
        if join["peer_id"] != peer_id:
            raise ValueError("join peer differs from frozen roster")
    for task_id, task in tasks.items():
        claim = current[f"task_claim:{round_id}:{task_id}"]
        result = current[f"result:{round_id}:{task_id}"]
        if claim["task_id"] != task_id or claim["owner_peer"] != task["owner_peer"]:
            raise ValueError("task claim differs from frozen assignment")
        expected = {
            "task_id": task_id, "item_id": task["item_id"],
            "image_id": task["image_id"], "image_sha256": task["image_sha256"],
            "source_peer": task["owner_peer"], "model_sha256": model_sha,
        }
        if any(result[key] != value for key, value in expected.items()):
            raise ValueError("result differs from frozen assignment")
        review_id = f"review_open:{round_id}:{task_id}"
        if result["decision"] == 1:
            opening = current[review_id]
            if opening["task_id"] != task_id or opening["observation_id"] != result["_id"]:
                raise ValueError("review observation differs from flagged result")
        elif review_id in current:
            raise ValueError("unflagged result has review opening")
    for record in current.values():
        if record["kind"] != "review_decision":
            continue
        task_id = record["task_id"]
        result_id = f"result:{round_id}:{task_id}"
        if (
            task_id not in tasks or record["reviewer_id"] not in roster
            or record["observation_id"] != result_id
            or result_id not in current or current[result_id]["decision"] != 1
            or f"review_open:{round_id}:{task_id}" not in current
        ):
            raise ValueError("review decision does not reference a flagged result")


def sync_latency_seconds(write_started_at_utc: str, remote_seen_at_utc: str) -> float:
    written = datetime.fromisoformat(write_started_at_utc)
    seen = datetime.fromisoformat(remote_seen_at_utc)
    if written.tzinfo is None or seen.tzinfo is None:
        raise ValueError("sync timestamps must include timezone")
    delay = (seen - written).total_seconds()
    if delay < 0:
        raise ValueError("remote result was observed before its write timestamp")
    return delay


def remote_sync_evidence(
    results: dict[str, dict[str, Any]], remote_seen_at: dict[str, str], *,
    peer_id: str, restart_replay: bool,
) -> tuple[str, list[dict[str, Any]]]:
    """Measure first-run visibility only; replay tests persistence and idempotence."""
    if restart_replay:
        return "not_measured_replay", []
    evidence = []
    for result_id, result_doc in sorted(results.items()):
        if result_doc["source_peer"] == peer_id:
            continue
        seen = remote_seen_at.get(result_id)
        if seen is None:
            raise SyncGateError("remote result visibility was not observed locally")
        latency = sync_latency_seconds(result_doc["write_started_at_utc"], seen)
        evidence.append({
            "result_id": result_id,
            "source_peer": result_doc["source_peer"],
            "write_started_at_utc": result_doc["write_started_at_utc"],
            "remote_seen_at_utc": seen,
            "latency_seconds": latency,
            "within_60_seconds": latency <= 60,
        })
    if not evidence or any(not item["within_60_seconds"] for item in evidence):
        raise SyncGateError("remote result visibility exceeded the 60-second sync gate")
    return "passed", evidence


async def _put(peer: Any, proposed: dict[str, Any], tally: dict[str, int] | None = None) -> str:
    current = await _documents(peer)
    result = assert_idempotent(current.get(proposed["_id"]), proposed)
    if proposed.get("kind") == "review_decision":
        history = [value for value in current.values() if value.get("kind") == "review_decision"]
        result = validate_next_review(history, proposed)
    if result == "new":
        write_result = await peer.store.execute(
            f"INSERT INTO {COLLECTION} DOCUMENTS (:document) ON ID CONFLICT DO NOTHING",
            {"document": proposed},
        )
        write_result.close()
        confirmed = await _documents(peer)
        if assert_idempotent(confirmed.get(proposed["_id"]), proposed) != "duplicate":
            raise RuntimeError("Ditto did not confirm the inserted record")
    if tally is not None:
        tally[result] = tally.get(result, 0) + 1
    return result


async def _process_task(
    peer: Any, task: dict[str, Any], *, image_root: Path, round_id: str,
    owner_peer: str, model: dict[str, Any], model_sha: str, infer: Any,
    write_tally: dict[str, int],
) -> dict[str, Any]:
    """Verify local bytes, confirm the claim in Ditto, then infer and persist result."""
    relative = Path(task["relative_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("task path escapes the local image root")
    source = (image_root / relative).resolve(strict=True)
    root = image_root.resolve(strict=True)
    if not source.is_relative_to(root) or not source.is_file():
        raise ValueError("task source is not a file under the local image root")
    image_bytes = source.read_bytes()
    if _sha(image_bytes) != task["image_sha256"]:
        raise ValueError("local image bytes differ from frozen assignment")

    claim = make_record(
        "task_claim", round_id, task["task_id"],
        task_id=task["task_id"], owner_peer=owner_peer,
    )
    await _put(peer, claim, write_tally)

    prediction = infer(image_bytes, model)
    result_id = f"result:{round_id}:{task['task_id']}"
    existing_result = (await _documents(peer)).get(result_id)
    result = make_record(
        "result", round_id, task["task_id"],
        task_id=task["task_id"], item_id=task["item_id"],
        image_id=task["image_id"], image_sha256=task["image_sha256"],
        source_peer=owner_peer, model_sha256=model_sha,
        score=prediction["probability"], decision=prediction["decision"],
        write_started_at_utc=(
            existing_result["write_started_at_utc"]
            if existing_result is not None else datetime.now(UTC).isoformat()
        ),
    )
    await _put(peer, result, write_tally)
    return result


async def run_peer(options: argparse.Namespace) -> dict[str, Any]:
    manifest, paths = validate_options(options)
    try:
        from model import load_artifact, predict_image
    except ImportError as error:
        raise RuntimeError("edge vision runtime unavailable") from error
    model = load_artifact(options.model)
    model_bytes = options.model.read_bytes()
    model_sha = _sha(model_bytes)
    if model_sha != manifest["model_sha256"]:
        raise ValueError("model artifact differs from the frozen assignment")
    all_tasks = _all_tasks(manifest, options.all_assignments)
    assigned = [task for task in all_tasks if task["owner_peer"] == options.peer_id]
    local_assignment = [
        {key: value for key, value in task.items() if key != "relative_path"}
        for task in manifest["tasks"]
    ]
    if assigned != local_assignment:
        raise ValueError("peer manifest differs from its frozen task assignment")
    expected_result_ids = set(options.expected_result_ids)
    expected_task_ids = set(options.expected_task_ids)
    if expected_task_ids != {task["task_id"] for task in all_tasks} or expected_result_ids != {
        f"result:{manifest['round_id']}:{task_id}" for task_id in expected_task_ids
    }:
        raise ValueError("CLI task IDs differ from the frozen assignment")
    token = _read_license()
    try:
        from ditto import Ditto, DittoConfig, DittoConfigConnect, DittoTransportConfig, __version__
    except ImportError as error:
        raise RuntimeError("Ditto SDK unavailable") from error

    store_path = options.stores / options.peer_id
    store_path.mkdir(parents=True, exist_ok=True)
    config = DittoConfig(
        database_id=options.database_id,
        connect=DittoConfigConnect.small_peers_only(),
        persistence_directory=str(store_path),
    )
    peer = await Ditto.open(config)
    started = time.monotonic_ns()
    inferred = 0
    write_tally = {"new": 0, "duplicate": 0}
    try:
        local_peer_key = peer.presence.graph.local_peer.peer_key
        if not isinstance(local_peer_key, str) or not local_peer_key:
            raise RuntimeError("Ditto SDK did not expose local device identity")
        device_identity_sha256 = _sha(local_peer_key.encode("utf-8"))
        peer.set_offline_only_license_token(token)
        transport = DittoTransportConfig()
        transport.listen.tcp.enabled = True
        transport.listen.tcp.interface_ip = options.listen_interface
        transport.listen.tcp.port = options.port
        transport.connect.tcp_servers.add(f"{options.neighbor_host}:{options.neighbor_port}")
        peer.transport_config = transport
        subscription = peer.sync.register_subscription(f"SELECT * FROM {COLLECTION}")
        try:
            peer.sync.start()
            before_docs = await _documents(peer)
            prior_result_ids = {
                key for key, value in before_docs.items()
                if value.get("round_id") == manifest["round_id"] and value.get("kind") == "result"
            }
            if options.restart_replay:
                require_replay_ready(expected_result_ids, prior_result_ids)
            else:
                require_fresh_sync_round(prior_result_ids)
            round_record = make_record(
                "round", manifest["round_id"], manifest["round_id"],
                peer_ids=["inspection-a", "inspection-b"],
                task_ids=sorted(task["task_id"] for task in all_tasks),
                task_count=options.task_count,
                assignment_sha256=manifest["assignment_sha256"],
                model_sha256=model_sha,
            )
            await _put(peer, round_record, write_tally)
            join = make_record("join", manifest["round_id"], options.peer_id, peer_id=options.peer_id)
            await _put(peer, join, write_tally)
            docs = await _documents(peer)
            append_snapshot(options.events_file, snapshot_from_documents(
                docs, round_id=manifest["round_id"], peer_id=options.peer_id,
                inference_count=inferred, state="waiting",
                sdk_device_identity_sha256=device_identity_sha256,
            ))

            local_results: list[dict[str, Any]] = []
            for task in manifest["tasks"]:
                result = await _process_task(
                    peer, task, image_root=paths["image_root"],
                    round_id=manifest["round_id"], owner_peer=options.peer_id,
                    model=model, model_sha=model_sha, infer=predict_image,
                    write_tally=write_tally,
                )
                local_results.append(result)
                inferred += 1
                if result["decision"] == 1:
                    review = make_record(
                        "review_open", manifest["round_id"], task["task_id"],
                        observation_id=result["_id"], task_id=task["task_id"],
                        status="open", reason="model_flagged_for_human_review",
                    )
                    await _put(peer, review, write_tally)
                docs = await _documents(peer)
                append_snapshot(options.events_file, snapshot_from_documents(
                    docs, round_id=manifest["round_id"], peer_id=options.peer_id,
                    inference_count=inferred, state="waiting",
                    sdk_device_identity_sha256=device_identity_sha256,
                ))

            deadline = time.monotonic() + min(options.sync_timeout, 60)
            remote_seen_at: dict[str, str] = {}
            expected_claim_ids = {
                f"task_claim:{manifest['round_id']}:{task_id}"
                for task_id in expected_task_ids
            }
            expected_join_ids = {
                f"join:{manifest['round_id']}:inspection-a",
                f"join:{manifest['round_id']}:inspection-b",
            }
            while time.monotonic() < deadline:
                docs = await _documents(peer)
                current = {key: doc for key, doc in docs.items() if doc.get("round_id") == manifest["round_id"]}
                results = {key: doc for key, doc in current.items() if doc.get("kind") == "result"}
                for result_id, result_doc in results.items():
                    if result_doc.get("source_peer") != options.peer_id and result_id not in remote_seen_at:
                        remote_seen_at[result_id] = datetime.now(UTC).isoformat()
                if validate_round_sets(
                    current, round_id=manifest["round_id"],
                    expected_task_ids=expected_task_ids,
                    expected_result_ids=expected_result_ids,
                    expected_claim_ids=expected_claim_ids,
                    expected_join_ids=expected_join_ids,
                ):
                    break
                append_snapshot(options.events_file, snapshot_from_documents(
                    docs, round_id=manifest["round_id"], peer_id=options.peer_id,
                    inference_count=inferred, state="waiting",
                    sdk_device_identity_sha256=device_identity_sha256,
                ))
                await asyncio.sleep(0.2)
            else:
                raise TimeoutError("peer Ditto state did not converge")
            if any(_contains_private(value) for value in docs.values()):
                raise ValueError("private field detected in synchronized state")
            validate_round_links(
                current, round_id=manifest["round_id"],
                tasks={task["task_id"]: task for task in all_tasks}, model_sha=model_sha,
                assignment_sha=manifest["assignment_sha256"],
            )
            final_snapshot = snapshot_from_documents(
                docs, round_id=manifest["round_id"], peer_id=options.peer_id,
                inference_count=inferred, state="converged",
                sdk_device_identity_sha256=device_identity_sha256,
            )
            review_history = sorted(
                ({key: value[key] for key in ("_id", "task_id", "reviewer_id", "decision", "revision")}
                 for value in current.values() if value.get("kind") == "review_decision"),
                key=lambda value: (value["task_id"], value["revision"], value["reviewer_id"]),
            )
            projection = {"results": sorted(
                ({key: value[key] for key in ("_id", "kind", "round_id", "task_id", "item_id", "image_id", "image_sha256", "source_peer", "model_sha256", "score", "decision", "write_started_at_utc")}
                 for value in results.values()),
                key=lambda value: value["_id"],
            ), "review_decisions": review_history}
            sync_gate, sync_evidence = remote_sync_evidence(
                results, remote_seen_at, peer_id=options.peer_id,
                restart_replay=options.restart_replay,
            )
            append_snapshot(options.events_file, final_snapshot)
            review_count = final_snapshot["review_queue_count"]
            final_result_ids = set(results)
            new_logical_result_count = len(final_result_ids - prior_result_ids)
            if options.restart_replay:
                new_logical_result_count = verify_replay_result(
                    expected_result_ids, prior_result_ids, final_result_ids, write_tally,
                )
            return {
                "status": "passed",
                "peer_id": options.peer_id,
                "round_id": manifest["round_id"],
                "local_task_count": len(local_results),
                "synced_result_count": len(results),
                "review_queue_count": review_count,
                "restart_replay": "verified" if options.restart_replay else "not_requested",
                "write_counts": write_tally,
                "prior_logical_result_count": len(prior_result_ids),
                "logical_result_count": len(final_result_ids),
                "new_logical_result_count": new_logical_result_count,
                "projection_sha256": _sha(json.dumps(projection, sort_keys=True, separators=(",", ":")).encode()),
                "review_decision_count": len(review_history),
                "sync_gate": sync_gate,
                "remote_result_sync_evidence": sync_evidence,
                "sdk_device_identity_sha256": device_identity_sha256,
                "sdk_device_identity_source": "presence.graph.local_peer.peer_key",
                "sdk_version": __version__,
                "elapsed_ms": (time.monotonic_ns() - started) / 1_000_000,
            }
        finally:
            subscription.cancel()
            subscription.close()
    finally:
        await peer.close()


def _all_tasks(local: dict[str, Any], full_path: Path | None) -> list[dict[str, Any]]:
    if full_path is None:
        raise ValueError("host-only full assignment is required for shared round metadata")
    full = json.loads(full_path.read_text(encoding="utf-8"))
    if set(full) != {
        "schema_version", "round_id", "dataset", "fold", "model_sha256",
        "source_sha256", "split_sha256", "peer_ids", "task_count",
        "peer_task_counts", "tasks", "assignment_sha256",
    } or full.get("schema_version") != 1:
        raise ValueError("full assignment schema is invalid")
    if full.get("assignment_sha256") != local["assignment_sha256"]:
        raise ValueError("full assignment digest differs from peer manifest")
    tasks = full.get("tasks")
    if not isinstance(tasks, list) or not tasks or any(type(task) is not dict or set(task) != {
        "task_id", "item_id", "image_id", "owner_peer", "image_sha256",
    } for task in tasks):
        raise ValueError("full assignment task list or schema is invalid")
    if len(tasks) != len({task["task_id"] for task in tasks}):
        raise ValueError("full assignment has duplicate task IDs")
    for task in tasks:
        if (
            not all(isinstance(task[field], str) and task[field] for field in ("task_id", "item_id", "image_id"))
            or task["owner_peer"] not in {"inspection-a", "inspection-b"}
            or task["task_id"] != f"{full['round_id']}:{task['image_id']}"
            or not re.fullmatch(r"[0-9a-f]{64}", task["image_id"])
            or not re.fullmatch(r"[0-9a-f]{64}", task["image_sha256"])
        ):
            raise ValueError("shared assignment task fields are invalid")
    for task in tasks:
        if (
            not all(isinstance(task[field], str) and task[field] for field in ("task_id", "item_id", "image_id"))
            or task["owner_peer"] not in {"inspection-a", "inspection-b"}
            or task["task_id"] != f"{full['round_id']}:{task['image_id']}"
            or not re.fullmatch(r"[0-9a-f]{64}", task["image_id"])
            or not re.fullmatch(r"[0-9a-f]{64}", task["image_sha256"])
        ):
            raise ValueError("shared assignment task fields are invalid")
    if full.get("peer_ids") != ["inspection-a", "inspection-b"] or set(
        task["owner_peer"] for task in tasks
    ) != set(full["peer_ids"]):
        raise ValueError("shared assignment peer roster is invalid")
    if full.get("task_count") != len(tasks) or full.get("peer_task_counts") != {
        peer_id: sum(task["owner_peer"] == peer_id for task in tasks)
        for peer_id in full["peer_ids"]
    }:
        raise ValueError("shared assignment task counts are invalid")
    if any(type(task) is not dict or set(task) != {
        "task_id", "item_id", "image_id", "owner_peer", "image_sha256",
    } for task in tasks):
        raise ValueError("shared assignment task schema is invalid")
    if full.get("peer_ids") != ["inspection-a", "inspection-b"] or set(
        task["owner_peer"] for task in tasks
    ) != set(full["peer_ids"]):
        raise ValueError("shared assignment peer roster is invalid")
    if full.get("task_count") != len(tasks) or full.get("peer_task_counts") != {
        peer_id: sum(task["owner_peer"] == peer_id for task in tasks)
        for peer_id in full["peer_ids"]
    }:
        raise ValueError("shared assignment task counts are invalid")
    unsigned = {key: value for key, value in full.items() if key != "assignment_sha256"}
    if _sha(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()) != full["assignment_sha256"]:
        raise ValueError("full assignment manifest digest is invalid")
    if any("relative_path" in task or "path" in task for task in tasks):
        raise ValueError("shared assignment must not disclose image paths")
    if local["assignment_sha256"] != full["assignment_sha256"]:
        raise ValueError("peer manifest and shared assignment digest differ")
    return tasks


def _contains_private(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key.lower() in {
            "image_bytes", "pixels", "embedding", "features", "label", "path",
            "relative_path", "source_path", "license", "license_token",
        } or _contains_private(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_private(item) for item in value)
    return False


def _expected_result_ids(full: dict[str, Any]) -> list[str]:
    return [f"result:{full['round_id']}:{task['task_id']}" for task in full["tasks"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="this peer's redacted assignment manifest")
    parser.add_argument("--all-assignments", type=Path, required=True, help="host assignment manifest; contains no labels")
    parser.add_argument("--images", type=Path, required=True, help="local source-image root; images stay here")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--stores", type=Path, required=True)
    parser.add_argument("--events-file", type=Path, required=True,
                        help="append-only JSONL snapshots from live Ditto store reads")
    parser.add_argument("--database-id", required=True)
    parser.add_argument("--peer-id", required=True)
    parser.add_argument("--listen-interface", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--neighbor-host", required=True)
    parser.add_argument("--neighbor-port", type=int, required=True)
    parser.add_argument("--task-count", type=int, required=True)
    parser.add_argument("--sync-timeout", type=int, default=60)
    parser.add_argument("--restart-replay", action="store_true",
                        help="require persistent results and verify this fresh process adds no records")
    args = parser.parse_args()
    if args.task_count <= 0 or not 1 <= args.sync_timeout <= 300:
        parser.error("task-count must be positive and sync-timeout in [1,300]")
    try:
        # Carry only task IDs across the process boundary; labels are not accepted.
        full = json.loads(args.all_assignments.read_text(encoding="utf-8"))
        args.expected_result_ids = _expected_result_ids(full)
        args.expected_task_ids = [task["task_id"] for task in full["tasks"]]
        if len(args.expected_task_ids) != args.task_count or full.get("task_count") != args.task_count:
            raise ValueError("declared task count differs from frozen assignment")
        result = asyncio.run(run_peer(args))
        print("EDGE_VISUAL_MESH_RESULT " + json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 - suppress SDK/config detail at CLI boundary.
        blocked_reason = {
            "offline license unavailable": "offline_license_unavailable",
            "Ditto SDK unavailable": "ditto_sdk_unavailable",
            "edge vision runtime unavailable": "edge_vision_runtime_unavailable",
        }.get(str(error)) if isinstance(error, RuntimeError) else None
        status = "blocked" if blocked_reason else "failed"
        payload = {"status": status, "error_type": type(error).__name__}
        if isinstance(error, SyncGateError):
            payload.update({"sync_gate": "failed", "sync_evidence": "incomplete_or_over_60_seconds"})
        if status == "blocked":
            payload["blocker"] = blocked_reason
        if args.events_file:
            append_snapshot(args.events_file, {
                "schema_version": 1,
                "type": "edge_visual_mesh_snapshot",
                "peer_id": args.peer_id,
                "observed_at_utc": datetime.now(UTC).isoformat(),
                "stale_after_seconds": 5,
                "state": "failed" if status == "failed" else "waiting",
                "evidence": "unknown",
                "local_inference_count": None,
                "replicated_result_count": None,
                "synced_result_count": None,
                "join_record_state": {"inspection-a": "unknown", "inspection-b": "unknown"},
                "review_queue_count": None,
                "review_queue_sha256": None,
                "result_projection_sha256": None,
                "blocker": payload.get("blocker", type(error).__name__),
            })
        print("EDGE_VISUAL_MESH_RESULT " + json.dumps(payload, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
