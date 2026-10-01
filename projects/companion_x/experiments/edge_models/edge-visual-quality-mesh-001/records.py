"""Typed, privacy-limited Ditto documents for the visual mesh experiment."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = 1
COLLECTION = "edge_visual_mesh"
RECORD_KINDS = {"round", "join", "task_claim", "result", "review_open", "review_decision"}
PRIVATE_FIELDS = {
    "image_bytes", "pixels", "embedding", "features", "label", "path",
    "relative_path", "source_path", "license", "license_token",
}
_FIELDS = {
    "round": {"peer_ids", "task_ids", "task_count", "assignment_sha256", "model_sha256"},
    "join": {"peer_id"},
    "task_claim": {"task_id", "owner_peer"},
    "result": {
        "task_id", "item_id", "image_id", "image_sha256", "source_peer",
        "model_sha256", "score", "decision", "write_started_at_utc",
    },
    "review_open": {"observation_id", "task_id", "status", "reason"},
    "review_decision": {"observation_id", "task_id", "reviewer_id", "decision", "revision"},
}
_COMMON_FIELDS = {"_id", "schema_version", "kind", "round_id", "subject_id"}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def record_id(kind: str, round_id: str, subject_id: str) -> str:
    if kind not in RECORD_KINDS or not round_id or not subject_id:
        raise ValueError("record identity is invalid")
    return f"{kind}:{round_id}:{subject_id}"


def make_record(kind: str, round_id: str, subject_id: str, **fields: Any) -> dict[str, Any]:
    if kind not in RECORD_KINDS:
        raise ValueError("unsupported record kind")
    value = {
        "_id": record_id(kind, round_id, subject_id),
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "round_id": round_id,
        "subject_id": subject_id,
        **fields,
    }
    validate_record(value)
    return value


def validate_record(value: dict[str, Any]) -> None:
    if type(value) is not dict or type(value.get("schema_version")) is not int:
        raise ValueError("record schema is invalid")
    if value["schema_version"] != SCHEMA_VERSION or value.get("kind") not in RECORD_KINDS:
        raise ValueError("record schema version or kind is unsupported")
    expected_id = record_id(value["kind"], value.get("round_id", ""), value.get("subject_id", ""))
    if value.get("_id") != expected_id:
        raise ValueError("record ID is not deterministic")
    keys = {key.lower() for key in value}
    if keys & PRIVATE_FIELDS:
        raise ValueError("private data cannot be stored in Ditto records")
    kind = value["kind"]
    if set(value) != _COMMON_FIELDS | _FIELDS[kind]:
        raise ValueError("record fields do not match the strict kind schema")
    if kind == "round":
        if not isinstance(value.get("peer_ids"), list) or len(value["peer_ids"]) != 2:
            raise ValueError("round requires two peers")
        if (
            any(not isinstance(item, str) or not item for item in value["peer_ids"])
            or len(set(value["peer_ids"])) != 2
            or not isinstance(value.get("task_ids"), list)
            or any(not isinstance(item, str) or not item for item in value["task_ids"])
            or len(set(value["task_ids"])) != len(value["task_ids"])
        ):
            raise ValueError("round peer or task roster is invalid")
        if type(value.get("task_count")) is not int or value["task_count"] != len(value["task_ids"]):
            raise ValueError("round task count is invalid")
        for field in ("model_sha256", "assignment_sha256"):
            _sha(value.get(field))
    elif kind == "join":
        if not isinstance(value.get("peer_id"), str) or not value["peer_id"]:
            raise ValueError("join peer is invalid")
    elif kind == "task_claim":
        if not isinstance(value.get("task_id"), str) or not value["task_id"]:
            raise ValueError("task claim ID is invalid")
        if not isinstance(value.get("owner_peer"), str) or not value["owner_peer"]:
            raise ValueError("task claim owner is invalid")
    elif kind == "result":
        _sha(value.get("image_sha256"))
        _sha(value.get("model_sha256"))
        if not isinstance(value.get("task_id"), str) or not value["task_id"]:
            raise ValueError("result task ID is invalid")
        if any(not isinstance(value.get(field), str) or not value[field] for field in ("item_id", "image_id")):
            raise ValueError("result item or image ID is invalid")
        if not isinstance(value.get("source_peer"), str) or not value["source_peer"]:
            raise ValueError("observation source peer is invalid")
        if type(value.get("score")) not in (int, float) or not math.isfinite(value["score"]):
            raise ValueError("observation score must be finite")
        if not 0 <= value["score"] <= 1 or type(value.get("decision")) is not int or value["decision"] not in (0, 1):
            raise ValueError("observation score or decision is invalid")
        _timestamp(value.get("write_started_at_utc"))
    elif kind == "review_open":
        if not isinstance(value.get("observation_id"), str) or not value["observation_id"]:
            raise ValueError("review must reference an observation")
        if value.get("status") != "open" or not isinstance(value.get("reason"), str):
            raise ValueError("review state is invalid")
    elif kind == "review_decision":
        if any(not isinstance(value.get(field), str) or not value[field] for field in (
            "observation_id", "task_id", "reviewer_id",
        )):
            raise ValueError("review decision identity is invalid")
        if value.get("decision") not in {"review", "dismiss"}:
            raise ValueError("review decision must be review or dismiss")
        if type(value.get("revision")) is not int or value["revision"] < 1:
            raise ValueError("review revision must be a positive integer")
        expected_subject = f"{value['task_id']}:r{value['revision']}:{value['reviewer_id']}"
        if value["subject_id"] != expected_subject:
            raise ValueError("review decision ID must pin task, revision, and reviewer")


def _sha(value: Any) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("digest must be lowercase SHA-256")


def _timestamp(value: Any) -> None:
    if not isinstance(value, str):
        raise ValueError("result write timestamp must be UTC ISO-8601")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError("result write timestamp must be UTC ISO-8601") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("result write timestamp must be UTC ISO-8601")


def assert_idempotent(existing: dict[str, Any] | None, proposed: dict[str, Any]) -> str:
    """Classify exact retries; reject same-ID writes with changed content."""
    validate_record(proposed)
    if existing is None:
        return "new"
    validate_record(existing)
    if existing.get("_id") != proposed["_id"]:
        raise ValueError("existing record ID differs")
    if canonical_bytes(existing) != canonical_bytes(proposed):
        raise ValueError("same-ID record has different immutable content")
    return "duplicate"


def validate_review_history(documents: list[dict[str, Any]]) -> None:
    """Reject revision gaps and competing decisions at the same task revision."""
    histories: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for document in documents:
        if document.get("kind") == "review_decision":
            validate_record(document)
            histories.setdefault((document["round_id"], document["task_id"]), []).append(document)
    for history in histories.values():
        revisions = [value["revision"] for value in history]
        if len(revisions) != len(set(revisions)):
            raise ValueError("conflicting review decisions share a revision")
        if sorted(revisions) != list(range(1, max(revisions) + 1)):
            raise ValueError("review decision revisions are not contiguous")


def validate_next_review(documents: list[dict[str, Any]], proposed: dict[str, Any]) -> str:
    """Allow an exact retry or the next revision; reject conflicting/stale writes."""
    validate_review_history(documents)
    existing = {value["_id"]: value for value in documents}.get(proposed["_id"])
    if existing is not None:
        return assert_idempotent(existing, proposed)
    history = [
        value for value in documents
        if value.get("kind") == "review_decision"
        and value.get("round_id") == proposed["round_id"]
        and value.get("task_id") == proposed["task_id"]
    ]
    next_revision = max((value["revision"] for value in history), default=0) + 1
    if proposed["revision"] != next_revision:
        raise ValueError("review decision revision must be the next revision")
    return "new"
