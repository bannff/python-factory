"""Port for graph run claims, checkpoints, and terminal result caching."""
from __future__ import annotations

from typing import Any, Protocol

from .graph_run_models import GraphRunRecord


class GraphRunClaim(Protocol):
    record: GraphRunRecord
    cached: bool

    def close(self) -> None: ...


class GraphRunLedger(Protocol):
    def claim(
        self, graph_id: str, run_id: str, session_id: str,
        task_digest: str, config_digest: str,
    ) -> GraphRunClaim: ...

    def checkpoint(
        self, claim: GraphRunClaim, node_id: str,
        schema_name: str, payload: dict[str, Any],
    ) -> None: ...

    def complete(self, claim: GraphRunClaim, result: dict[str, Any]) -> None: ...

    def fail(self, claim: GraphRunClaim, error: str) -> None: ...


class GraphRunConflict(RuntimeError):
    """The run ID is active or belongs to different immutable inputs."""


__all__ = ["GraphRunClaim", "GraphRunConflict", "GraphRunLedger"]
