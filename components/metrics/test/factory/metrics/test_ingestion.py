"""Smoke tests for portfolio ingestion tool.

Mocks the MCP aggregator to verify SIPP/Veritas queries and
derived metric recording.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from factory.metrics.runtime.adapters.memory import (
    InMemoryMetricsComputer,
    InMemoryMetricsStore,
)
from factory.metrics.runtime.runtime import MetricsRuntime
from factory.metrics.mcp.ingestion import (
    _compute_and_record,
    _query_sipp,
    _query_veritas,
)


@pytest.fixture()
def runtime() -> MetricsRuntime:
    return MetricsRuntime(
        store=InMemoryMetricsStore(),
        computer=InMemoryMetricsComputer(),
    )


@pytest.fixture()
def mock_agg():
    agg = MagicMock()
    with patch(
        "factory.metrics.mcp.ingestion._get_aggregator",
        return_value=agg,
    ):
        yield agg


# ── Helpers for mock responses ───────────────────────────────────

SIPP_PEAK_ROWS = [
    {"service_name": "app-a", "peak_score": 85.0},
    {"service_name": "app-b", "peak_score": 72.0},
]

SIPP_FINDING_ROWS = [
    {"severity": "critical", "cnt": 3},
    {"severity": "high", "cnt": 12},
]

VERITAS_TOPO_ROWS = [
    {"service": "app-a", "resource_count": 10},
    {"service": "app-b", "resource_count": 5},
    {"service": "app-c", "resource_count": 8},
]

VERITAS_POSTURE_ROWS = [
    {"service": "app-a", "peak": 85.0},
    {"service": "app-b", "peak": 72.0},
]


def _sipp_side_effect(tool_name: str, **kwargs):
    if tool_name == "sipp_run_query":
        if "peak_scores" in kwargs.get("sql", ""):
            return {"rows": SIPP_PEAK_ROWS}
        if "findings" in kwargs.get("sql", ""):
            return {"rows": SIPP_FINDING_ROWS}
    if tool_name == "query_veritas":
        if "OWNS" in kwargs.get("cypher_query", ""):
            return {"rows": VERITAS_TOPO_ROWS}
        return {"rows": VERITAS_POSTURE_ROWS}
    return {}


# ── Full ingestion ───────────────────────────────────────────────

class TestFullIngestion:
    def test_both_sources(self, mock_agg, runtime):
        mock_agg.invoke_tool.side_effect = _sipp_side_effect

        from factory.metrics.mcp.ingestion import register
        from factory.mcp_utils.runtime.tool_catalog import ToolCatalog

        mcp = ToolCatalog("test")
        register(mcp, runtime)

        # Call the inner function directly via module helpers
        errors: list[str] = []
        sipp = _query_sipp(errors)
        veritas = _query_veritas(None, errors)
        total = _compute_and_record(runtime, sipp, veritas)

        assert errors == []
        assert sipp["peak_rows"] == SIPP_PEAK_ROWS
        assert veritas["topo_rows"] == VERITAS_TOPO_ROWS
        assert total > 0  # peak-avg + coverage-pct + 2 findings + 3 resources


class TestSippOnly:
    def test_sipp_only_ingestion(self, mock_agg, runtime):
        mock_agg.invoke_tool.side_effect = _sipp_side_effect

        errors: list[str] = []
        sipp = _query_sipp(errors)
        total = _compute_and_record(runtime, sipp, {})

        assert errors == []
        assert len(sipp["peak_rows"]) == 2
        # peak-avg + 2 finding-count rows = 3
        assert total == 3


class TestVeritasOnly:
    def test_veritas_only_ingestion(self, mock_agg, runtime):
        mock_agg.invoke_tool.side_effect = _sipp_side_effect

        errors: list[str] = []
        veritas = _query_veritas(["app-a"], errors)
        total = _compute_and_record(runtime, {}, veritas)

        assert errors == []
        assert len(veritas["topo_rows"]) == 3
        # coverage-pct (0%) + 3 resource-count rows = 4
        assert total == 4


class TestErrorHandling:
    def test_aggregator_errors_captured(self, mock_agg, runtime):
        mock_agg.invoke_tool.side_effect = RuntimeError("connection refused")

        errors: list[str] = []
        sipp = _query_sipp(errors)
        veritas = _query_veritas(None, errors)

        assert len(errors) == 3  # 2 sipp + 1 veritas (posture skipped: no names)
        assert sipp["peak_rows"] == []
        assert veritas["topo_rows"] == []

        total = _compute_and_record(runtime, sipp, veritas)
        assert total == 0

    def test_partial_sipp_failure(self, mock_agg, runtime):
        """First SIPP query succeeds, second fails."""
        call_count = 0

        def _partial(tool_name, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"rows": SIPP_PEAK_ROWS}
            raise RuntimeError("timeout")

        mock_agg.invoke_tool.side_effect = _partial

        errors: list[str] = []
        sipp = _query_sipp(errors)

        assert len(errors) == 1
        assert sipp["peak_rows"] == SIPP_PEAK_ROWS
        assert sipp["finding_rows"] == []


class TestEmptyResults:
    def test_empty_sipp_results(self, mock_agg, runtime):
        mock_agg.invoke_tool.return_value = {"rows": []}

        errors: list[str] = []
        sipp = _query_sipp(errors)
        total = _compute_and_record(runtime, sipp, {})

        assert errors == []
        assert total == 0

    def test_empty_veritas_results(self, mock_agg, runtime):
        mock_agg.invoke_tool.return_value = {"rows": []}

        errors: list[str] = []
        veritas = _query_veritas(None, errors)
        total = _compute_and_record(runtime, {}, veritas)

        assert errors == []
        assert total == 0

    def test_none_response_from_aggregator(self, mock_agg, runtime):
        mock_agg.invoke_tool.return_value = None

        errors: list[str] = []
        sipp = _query_sipp(errors)

        assert errors == []
        assert sipp["peak_rows"] == []
