"""Portfolio ingestion via SIPP and Veritas MCP tools.

Pulls data through the MCP aggregator, computes derived portfolio
metrics, and records them via the metrics runtime.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from factory.mcp_utils.interface import ToolResult, operational, ok
from factory.mcp_utils.registration import typed_tool

from .contracts.operational import PortfolioInput, PortfolioOutput

if TYPE_CHECKING:
    from ..runtime.runtime import MetricsRuntime

logger = logging.getLogger(__name__)


def _get_aggregator() -> Any:
    from factory.mcp_server.interface import get_server, get_aggregator
    get_server()
    return get_aggregator()


def _invoke(tool_name: str, **kwargs: Any) -> Any:
    agg = _get_aggregator()
    if agg is None:
        raise RuntimeError("MCP aggregator not available")
    return agg.invoke_tool(tool_name, **kwargs)


# ── SIPP queries ─────────────────────────────────────────────────

_PEAK_SCORES_SQL = (
    "SELECT service_name, peak_score FROM security.peak_scores"
    " WHERE scan_date = current_date"
)
_FINDING_COUNTS_SQL = (
    "SELECT severity, count(*) as cnt FROM security.findings GROUP BY severity"
)


def _query_sipp(errors: list[str]) -> dict[str, Any]:
    """Fetch PEAK scores and finding counts from SIPP."""
    peak_rows: list[dict[str, Any]] = []
    finding_rows: list[dict[str, Any]] = []
    try:
        result = _invoke(
            "sipp_run_query", sql=_PEAK_SCORES_SQL,
            group="TEAM-Security", timeout=300,
        )
        peak_rows = (result or {}).get("rows", [])
    except Exception as exc:
        logger.error("SIPP peak scores query failed: %s", exc)
        errors.append("sipp_peak: query failed")

    try:
        result = _invoke(
            "sipp_run_query", sql=_FINDING_COUNTS_SQL,
            group="TEAM-Security", timeout=300,
        )
        finding_rows = (result or {}).get("rows", [])
    except Exception as exc:
        logger.error("SIPP finding counts query failed: %s", exc)
        errors.append("sipp_findings: query failed")

    return {"peak_rows": peak_rows, "finding_rows": finding_rows}

# ── Veritas queries ──────────────────────────────────────────────

_TOPOLOGY_CYPHER = (
    "MATCH (a:VeritasApp)-[:OWNS]->(r) RETURN a.veritas_app_name"
    " AS service, count(r) AS resource_count LIMIT 100"
)
_POSTURE_CYPHER = (
    "MATCH (a:VeritasApp) WHERE a.veritas_app_name IN $names"
    " RETURN a.veritas_app_name AS service, a.peak_score AS peak"
    " LIMIT 100"
)


def _query_veritas(
    app_names: list[str] | None, errors: list[str],
) -> dict[str, Any]:
    """Fetch topology and posture from Veritas."""
    topo_rows: list[dict[str, Any]] = []
    posture_rows: list[dict[str, Any]] = []
    try:
        result = _invoke(
            "query_veritas", cypher_query=_TOPOLOGY_CYPHER, database="sdo",
        )
        topo_rows = (result or {}).get("rows", [])
    except Exception as exc:
        logger.error("Veritas topology query failed: %s", exc)
        errors.append("veritas_topology: query failed")

    names = app_names or [r.get("service", "") for r in topo_rows]
    if names:
        try:
            result = _invoke(
                "query_veritas", cypher_query=_POSTURE_CYPHER,
                database="sdo", params={"names": names},
            )
            posture_rows = (result or {}).get("rows", [])
        except Exception as exc:
            logger.error("Veritas posture query failed: %s", exc)
            errors.append("veritas_posture: query failed")

    return {"topo_rows": topo_rows, "posture_rows": posture_rows}

# ── Derived metrics ──────────────────────────────────────────────

def _compute_and_record(
    runtime: MetricsRuntime, sipp: dict[str, Any], veritas: dict[str, Any],
) -> int:
    """Compute derived metrics and record them. Returns count recorded."""
    batch: list[dict[str, Any]] = []

    scores = [
        r["peak_score"] for r in sipp.get("peak_rows", [])
        if r.get("peak_score") is not None
    ]
    if scores:
        batch.append({"metric_id": "portfolio-peak-avg", "value": sum(scores) / len(scores)})

    # portfolio-coverage-pct
    total_services = len(veritas.get("topo_rows", []))
    if total_services > 0:
        pct = min(round((len(scores) / total_services) * 100, 2), 100.0)
        batch.append({"metric_id": "portfolio-coverage-pct", "value": pct})

    for row in sipp.get("finding_rows", []):
        batch.append({
            "metric_id": "portfolio-finding-count",
            "value": float(row.get("cnt", 0)),
            "labels": {"severity": row.get("severity", "unknown")},
        })

    for row in veritas.get("topo_rows", []):
        batch.append({
            "metric_id": "portfolio-resource-count",
            "value": float(row.get("resource_count", 0)),
            "labels": {"service": row.get("service", "unknown")},
        })

    if batch:
        runtime.record_batch(batch)
    return len(batch)

# ── Registration ─────────────────────────────────────────────────

def register(mcp: Any, runtime: "MetricsRuntime") -> None:
    """Register portfolio ingestion tool."""

    @typed_tool(mcp)
    @operational(input_model=PortfolioInput, output_model=PortfolioOutput)
    def metrics_ingest_portfolio(
        app_names: list[str] | None = None,
        include_sipp: bool = True,
        include_veritas: bool = True,
    ) -> ToolResult[PortfolioOutput]:
        """Ingest portfolio metrics from SIPP and Veritas."""
        errors: list[str] = []
        sipp_data: dict[str, Any] = {}
        veritas_data: dict[str, Any] = {}

        if include_sipp:
            sipp_data = _query_sipp(errors)
        if include_veritas:
            veritas_data = _query_veritas(app_names, errors)

        total = _compute_and_record(runtime, sipp_data, veritas_data)

        return ok(PortfolioOutput(
            ok=len(errors) == 0,
            sipp_metrics={"peak_services": len(sipp_data.get("peak_rows", [])),
                          "finding_severities": len(sipp_data.get("finding_rows", []))},
            veritas_metrics={"topology_services": len(veritas_data.get("topo_rows", [])),
                             "posture_services": len(veritas_data.get("posture_rows", []))},
            errors=errors, total_recorded=total,
        ))
