"""Post-run metrics helper for multi-agent lifecycle plugin.

Split from ``multiagent_lifecycle.py`` to keep both files <200 LOC
(meta-architect's split contingency). Records ``autosec-finding-count``
data points at the end of a graph/swarm run by querying the graph
brick for findings produced under the run id.

All calls go through ``tool_invoker`` (MCP-first). Fire-and-forget —
failures never break the workflow.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def record_run_metrics(
    workflow_id: str, run_id: str, elapsed: float,
) -> None:
    """Record findings metrics for a completed graph/swarm run.

    ``elapsed`` retained for parity with previous helper signature
    even though the metrics surface doesn't currently consume it.
    """
    invoker = _get_invoker()
    if invoker is None or not run_id:
        return
    try:
        findings = _count_findings(invoker, run_id)
        records: list[dict[str, Any]] = []
        if findings["total"] > 0:
            records.append({
                "metric_id": "autosec-finding-count",
                "value": findings["total"],
                "labels": {"graph_id": workflow_id, "run_id": run_id},
            })
        for severity, count in findings["by_severity"].items():
            if count > 0:
                records.append({
                    "metric_id": "autosec-finding-count",
                    "value": count,
                    "labels": {
                        "graph_id": workflow_id, "run_id": run_id,
                        "severity": str(severity).lower(),
                    },
                })
        if records:
            invoker("metrics_record_batch", records=records)
            logger.info(
                "Recorded %d metrics for run %s", len(records), run_id,
            )
    except Exception:
        logger.debug("metrics record failed", exc_info=True)


def _count_findings(invoker: Any, run_id: str) -> dict[str, Any]:
    """Query graph for findings by ``run_id``."""
    try:
        result = invoker(
            "graph_graph_find_entities", entity_type=None,
            properties={"run_id": run_id}, limit=100,
        )
        entities = (
            result.data.entities
            if result and result.ok and result.data is not None else []
        )
        total = 0
        by_severity: dict[str, int] = {}
        for entity in entities:
            if entity.type not in {"ProvenExploit", "VerifiedExploit", "SecurityFinding"}:
                continue
            severity = str(entity.properties.get("severity", "unknown"))
            total += 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
        return {"total": total, "by_severity": by_severity}
    except Exception:
        return {"total": 0, "by_severity": {}}


def _get_invoker() -> Any:
    """Get the MCP tool invoker. Returns ``None`` if unavailable."""
    try:
        from factory.mcp_utils.interface import get_service
        return get_service("tool_invoker")
    except Exception:
        return None
