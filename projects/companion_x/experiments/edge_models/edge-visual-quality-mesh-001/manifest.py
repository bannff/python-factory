"""Freeze whole-item visual tasks and keep fold labels in a host-only file."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from records import canonical_bytes

PEERS = ("inspection-a", "inspection-b")
HEX = re.compile(r"^[0-9a-f]{64}$")


def _sha(value: str) -> bool:
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def _safe_relative_path(value: Any) -> str:
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("image path must be a POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError("image path must remain below the source image root")
    return path.as_posix()


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def freeze_manifest(
    rows: Iterable[dict[str, Any]], *, round_id: str, model_sha256: str,
    source_sha256: str, split_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build deterministic item-level peer assignments plus a host-only label map.

    Rows contain source-relative JPEG paths, item IDs, image hashes, and labels.
    The returned public manifest intentionally excludes labels; the second return
    value is host-only and must never be copied to a peer.
    """
    if not round_id or any(not _sha(item) for item in (model_sha256, source_sha256, split_sha256)):
        raise ValueError("round ID and pinned artifact hashes are required")
    normalized = []
    ids: set[str] = set()
    for row in rows:
        if type(row) is not dict or set(row) != {"path", "item_id", "image_sha256", "label"}:
            raise ValueError("source rows must contain path, item_id, image_sha256, and label")
        path = _safe_relative_path(row["path"])
        if not path.lower().endswith(".jpg"):
            raise ValueError("only source JPEGs are accepted")
        item_id = row["item_id"]
        if not isinstance(item_id, str) or not item_id or "/" in item_id or item_id in (".", ".."):
            raise ValueError("item ID is invalid")
        if path.split("/", 1)[0] != item_id:
            raise ValueError("source path must be grouped beneath its item ID")
        if not _sha(row["image_sha256"]) or type(row["label"]) is not int or row["label"] not in (0, 1):
            raise ValueError("image hash or host label is invalid")
        if path in ids:
            raise ValueError("duplicate source image path")
        ids.add(path)
        image_id = hashlib.sha256(path.encode()).hexdigest()
        normalized.append({
            "path": path,
            "item_id": item_id,
            "image_id": image_id,
            "image_sha256": row["image_sha256"],
            "label": row["label"],
        })
    if not normalized:
        raise ValueError("cannot freeze an empty image cohort")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in normalized:
        grouped.setdefault(row["item_id"], []).append(row)
    counts = {peer: 0 for peer in PEERS}
    owner_by_item: dict[str, str] = {}
    for item_id in sorted(grouped, key=lambda item: (-len(grouped[item]), item)):
        owner = min(PEERS, key=lambda peer: (counts[peer], PEERS.index(peer)))
        owner_by_item[item_id] = owner
        counts[owner] += len(grouped[item_id])

    tasks = []
    host_labels = {}
    host_paths = {}
    for row in sorted(normalized, key=lambda item: item["path"]):
        task_id = f"{round_id}:{row['image_id']}"
        tasks.append({
            "task_id": task_id,
            "item_id": row["item_id"],
            "image_id": row["image_id"],
            "owner_peer": owner_by_item[row["item_id"]],
            "image_sha256": row["image_sha256"],
        })
        host_labels[row["image_id"]] = row["label"]
        host_paths[task_id] = row["path"]
    public = {
        "schema_version": 1,
        "round_id": round_id,
        "dataset": "KolektorSDD",
        "fold": 0,
        "model_sha256": model_sha256,
        "source_sha256": source_sha256,
        "split_sha256": split_sha256,
        "peer_ids": list(PEERS),
        "task_count": len(tasks),
        "peer_task_counts": counts,
        "tasks": tasks,
    }
    public["assignment_sha256"] = _digest(public)
    host_only = {
        "schema_version": 1,
        "round_id": round_id,
        "assignment_sha256": public["assignment_sha256"],
        "labels": host_labels,
        "relative_paths": host_paths,
    }
    return public, host_only


def peer_manifest(
    public: dict[str, Any], peer_id: str, relative_paths: dict[str, str],
) -> dict[str, Any]:
    if peer_id not in PEERS:
        raise ValueError("peer ID is not in the frozen roster")
    tasks = [
        {**task, "relative_path": relative_paths[task["task_id"]]}
        for task in public["tasks"] if task["owner_peer"] == peer_id
    ]
    if not tasks:
        raise ValueError("peer has no assigned tasks")
    return {
        "schema_version": 1,
        "round_id": public["round_id"],
        "assignment_sha256": public["assignment_sha256"],
        "model_sha256": public["model_sha256"],
        "peer_id": peer_id,
        "tasks": tasks,
    }


def write_outputs(public: dict[str, Any], host_only: dict[str, Any], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "assignment-manifest.json").write_bytes(canonical_bytes(public) + b"\n")
    (out / "host-labels.json").write_bytes(canonical_bytes(host_only) + b"\n")
    relative_paths = host_only["relative_paths"]
    for peer_id in PEERS:
        (out / f"{peer_id}-manifest.json").write_bytes(
            canonical_bytes(peer_manifest(public, peer_id, relative_paths)) + b"\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True,
                        help="host-only JSON array with path,item_id,image_sha256,label")
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--model-sha256", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--split-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        rows = json.loads(args.inventory.read_text(encoding="utf-8"))
        public, host_only = freeze_manifest(
            rows, round_id=args.round_id, model_sha256=args.model_sha256,
            source_sha256=args.source_sha256, split_sha256=args.split_sha256,
        )
        write_outputs(public, host_only, args.out)
        print(json.dumps({
            "status": "frozen",
            "assignment_sha256": public["assignment_sha256"],
            "task_count": public["task_count"],
            "peer_task_counts": public["peer_task_counts"],
            "host_labels_file": "host-labels.json",
        }, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 - do not disclose source paths or row details.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
