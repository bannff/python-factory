"""Write one revisioned human review or dismiss decision through Ditto."""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import re
import time
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from peer import LICENSE_FILE, _documents, _put
from records import make_record, validate_next_review

DNS_NAME = re.compile(r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$")


def replication_status(expected: dict[str, Any], observed_by_peer: dict[str, dict[str, Any]]) -> str:
    """A review passes only after both frozen peers expose the exact immutable record."""
    if set(observed_by_peer) != {"inspection-a", "inspection-b"}:
        return "incomplete"
    if any(value != expected for value in observed_by_peer.values()):
        return "failed"
    return "passed"


def review_record(
    *, round_id: str, task_id: str, observation_id: str, reviewer_id: str,
    decision: str, revision: int,
) -> dict[str, Any]:
    subject = f"{task_id}:r{revision}:{reviewer_id}"
    return make_record(
        "review_decision", round_id, subject,
        observation_id=observation_id, task_id=task_id, reviewer_id=reviewer_id,
        decision=decision, revision=revision,
    )


def _token() -> str:
    try:
        value = LICENSE_FILE.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError("offline license unavailable") from error
    if not value:
        raise RuntimeError("offline license unavailable")
    return value


async def write_review(options: argparse.Namespace) -> dict[str, Any]:
    token = _token()
    try:
        from ditto import Ditto, DittoConfig, DittoConfigConnect, DittoTransportConfig, __version__
    except ImportError as error:
        raise RuntimeError("Ditto SDK unavailable") from error
    config = DittoConfig(
        database_id=options.database_id,
        connect=DittoConfigConnect.small_peers_only(),
        persistence_directory=str(options.stores / options.peer_id),
    )
    peer = await Ditto.open(config)
    try:
        sdk_peer_key = peer.presence.graph.local_peer.peer_key
        if not isinstance(sdk_peer_key, str) or not sdk_peer_key:
            raise RuntimeError("Ditto SDK did not expose local device identity")
        peer.set_offline_only_license_token(token)
        transport = DittoTransportConfig()
        transport.listen.tcp.enabled = True
        transport.listen.tcp.interface_ip = "0.0.0.0"
        transport.listen.tcp.port = options.port
        transport.connect.tcp_servers.add(f"{options.neighbor_host}:{options.neighbor_port}")
        peer.transport_config = transport
        subscription = peer.sync.register_subscription("SELECT * FROM edge_visual_mesh")
        try:
            peer.sync.start()
            deadline = time.monotonic() + options.timeout
            while time.monotonic() < deadline:
                docs = await _documents(peer)
                observation = docs.get(options.observation_id)
                opening_id = f"review_open:{options.round_id}:{options.task_id}"
                opening = docs.get(opening_id)
                if (
                    observation is not None and observation.get("kind") == "result"
                    and observation.get("round_id") == options.round_id
                    and observation.get("task_id") == options.task_id
                    and observation.get("decision") == 1
                    and opening is not None and opening.get("observation_id") == options.observation_id
                ):
                    break
                await asyncio.sleep(0.2)
            else:
                raise TimeoutError("review item is not available in synchronized Ditto state")

            review = review_record(
                round_id=options.round_id, task_id=options.task_id,
                observation_id=options.observation_id, reviewer_id=options.peer_id,
                decision=options.decision, revision=options.revision,
            )
            history = [
                value for value in docs.values()
                if value.get("kind") == "review_decision"
                and value.get("round_id") == options.round_id
                and value.get("task_id") == options.task_id
            ]
            replay_status = validate_next_review(history, review)
            write_status = await _put(peer, review)
            if replay_status == "duplicate" and write_status != "duplicate":
                raise RuntimeError("review replay confirmation disagrees")
            return {
                "status": "incomplete",
                "local_write": "confirmed",
                "replication": "unverified",
                "required_follow_on": "observe this review record in both persistent peer stores",
                "peer_id": options.peer_id,
                "round_id": options.round_id,
                "task_id": options.task_id,
                "decision": options.decision,
                "revision": options.revision,
                "write": write_status,
                "sdk_version": __version__,
                "sdk_device_identity_sha256": hashlib.sha256(sdk_peer_key.encode("utf-8")).hexdigest(),
                "sdk_device_identity_source": "presence.graph.local_peer.peer_key",
            }
        finally:
            subscription.cancel()
            subscription.close()
    finally:
        await peer.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-id", required=True)
    parser.add_argument("--stores", type=Path, required=True)
    parser.add_argument("--peer-id", choices=("inspection-a", "inspection-b"), required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--neighbor-host", required=True)
    parser.add_argument("--neighbor-port", type=int, required=True)
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--observation-id", required=True)
    parser.add_argument("--decision", choices=("review", "dismiss"), required=True)
    parser.add_argument("--revision", type=int, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    options = parser.parse_args()
    if not 1 <= options.port <= 65535 or not 1 <= options.neighbor_port <= 65535:
        parser.error("ports must be in [1,65535]")
    if options.revision < 1 or not 1 <= options.timeout <= 300:
        parser.error("revision must be positive and timeout in [1,300]")
    try:
        UUID(options.database_id)
    except (ValueError, TypeError, AttributeError):
        parser.error("database-id must be a UUID")
    if not DNS_NAME.fullmatch(options.neighbor_host):
        parser.error("neighbor-host must be a lowercase DNS alias")
    try:
        ipaddress.ip_address(options.neighbor_host)
    except ValueError:
        pass
    else:
        parser.error("neighbor-host must be a DNS alias, not an IP address")
    try:
        result = asyncio.run(write_review(options))
        print("EDGE_VISUAL_MESH_REVIEW " + json.dumps(result, sort_keys=True))
        return 2 if result["status"] == "incomplete" else 0
    except Exception as error:  # noqa: BLE001 - suppress SDK/config details.
        blocker = {
            "offline license unavailable": "offline_license_unavailable",
            "Ditto SDK unavailable": "ditto_sdk_unavailable",
        }.get(str(error)) if isinstance(error, RuntimeError) else None
        print("EDGE_VISUAL_MESH_REVIEW " + json.dumps({
            "status": "blocked" if blocker else "failed",
            "blocker": blocker,
            "error_type": type(error).__name__,
        }, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
