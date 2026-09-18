"""Locked JSON adapter for graph checkpoints and terminal result caching."""
from __future__ import annotations

import fcntl
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, IO

from ..graph_run_ledger import GraphRunConflict
from ..graph_run_models import GraphNodeOutput, GraphRunRecord

_SAFE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,255}$")


@dataclass
class JsonGraphRunClaim:
    record: GraphRunRecord
    cached: bool
    _ledger: "JsonGraphRunLedger"
    _lock: IO[str] | None

    def close(self) -> None:
        if self._lock is not None:
            fcntl.flock(self._lock.fileno(), fcntl.LOCK_UN)
            self._lock.close()
            self._lock = None


class JsonGraphRunLedger:
    """One durable file and OS lock per graph/run identity."""

    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or os.getenv("COMPANION_X_GRAPH_RUN_DIR")
        self.root = Path(configured or ".storage/graph-runs")
        self.root.mkdir(parents=True, exist_ok=True)

    def _key(self, graph_id: str, run_id: str) -> str:
        if not _SAFE_ID.fullmatch(graph_id) or not _SAFE_ID.fullmatch(run_id):
            raise ValueError("graph_id and run_id must be path-safe identifiers")
        return f"{graph_id}--{run_id}"

    def claim(self, graph_id: str, run_id: str, session_id: str,
              task_digest: str, config_digest: str) -> JsonGraphRunClaim:
        key = self._key(graph_id, run_id)
        lock = open(self.root / f"{key}.lock", "a+")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            lock.close()
            raise GraphRunConflict(f"graph run {key!r} is already active") from exc
        path = self.root / f"{key}.json"
        record = self._read(path)
        if record is not None:
            if (record.task_digest, record.config_digest) != (task_digest, config_digest):
                lock.close()
                raise GraphRunConflict(f"run_id {run_id!r} has different inputs")
            cached = record.status in {"completed", "failed"}
            claim = JsonGraphRunClaim(record, cached, self, lock)
            if cached:
                claim.close()
            return claim
        record = GraphRunRecord(
            graph_id=graph_id, run_id=run_id, session_id=session_id,
            task_digest=task_digest, config_digest=config_digest,
        )
        self._write(path, record)
        return JsonGraphRunClaim(record, False, self, lock)

    def checkpoint(self, claim: JsonGraphRunClaim, node_id: str,
                   schema_name: str, payload: dict[str, Any]) -> None:
        claim.record.nodes[node_id] = GraphNodeOutput(
            schema_name=schema_name, payload=payload,
        )
        self._persist(claim)

    def complete(self, claim: JsonGraphRunClaim, result: dict[str, Any]) -> None:
        claim.record.status = "completed"
        claim.record.result = result
        self._persist(claim)
        claim.close()

    def fail(self, claim: JsonGraphRunClaim, error: str) -> None:
        claim.record.status = "failed"
        claim.record.error = error
        claim.record.result = {
            "status": "error",
            "results": {"error": error},
            "node_errors": {"run": error},
            "run_id": claim.record.run_id,
            "session_id": claim.record.session_id,
            "structured_outputs": {
                node_id: saved.payload for node_id, saved in claim.record.nodes.items()
            },
            "cached": False,
        }
        self._persist(claim)
        claim.close()

    def _persist(self, claim: JsonGraphRunClaim) -> None:
        self._write(self.root / f"{self._key(claim.record.graph_id, claim.record.run_id)}.json", claim.record)

    @staticmethod
    def _read(path: Path) -> GraphRunRecord | None:
        if not path.exists():
            return None
        return GraphRunRecord.model_validate_json(path.read_text())

    @staticmethod
    def _write(path: Path, record: GraphRunRecord) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(record.model_dump_json(indent=2))
        os.replace(tmp, path)


__all__ = ["JsonGraphRunClaim", "JsonGraphRunLedger"]
