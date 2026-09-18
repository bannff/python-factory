"""Typed boundary coverage for all checked-in Metrics FastMCP registrations."""
from __future__ import annotations

import asyncio
import inspect
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from factory.metrics.mcp.contracts.operational import RecordInput
from factory.metrics.server import create_mcp_server
from factory.mcp_utils.interface import ToolResult


def _server():
    return create_mcp_server()


def _tools() -> dict[str, object]:
    server = _server()
    return {
        tool.name: asyncio.run(server.get_tool(tool.name))
        for tool in asyncio.run(server.list_tools())
        if tool.name.startswith("metrics_")
    }


def test_fresh_server_has_exact_metrics_inventory_and_categories() -> None:
    tools = _tools()
    assert len(tools) == 28
    for category, expected in {"deterministic": 16, "operational": 7, "authoring": 5}.items():
        assert sum(getattr(tool.fn, "_mcp_category", None) == category for tool in tools.values()) == expected


def test_every_metrics_tool_has_strict_dto_boundary_and_exact_envelope() -> None:
    for tool in _tools().values():
        fn = tool.fn
        input_model = getattr(fn, "_mcp_input_model")
        output_model = getattr(fn, "_mcp_output_model")
        assert input_model.model_config["extra"] == "forbid"
        assert input_model.model_config["strict"] is True
        assert output_model.model_config["extra"] == "forbid"
        assert output_model.model_config["strict"] is True
        assert set(output_model.model_fields) != {"value"}
        assert all(field.annotation is not object for field in output_model.model_fields.values())
        assert get_type_hints(fn)["return"] == ToolResult[output_model]


def test_flat_ingress_rejects_unknown_and_coercible_values() -> None:
    with pytest.raises(ValidationError):
        RecordInput.model_validate({"metric_id": "m", "value": 1.0, "unknown": True})
    with pytest.raises(ValidationError):
        RecordInput.model_validate({"metric_id": "m", "value": "1.0"})


def test_domain_negative_authoring_and_seed_outcomes_are_successful_data() -> None:
    tools = _tools()
    status = tools["metrics_authoring_status"].fn()
    assert status.ok is True and status.data.enabled is False
    from factory.mcp_utils.runtime.tool_catalog import ToolCatalog
    from factory.metrics.mcp.seed import register
    from factory.metrics.runtime.adapters.memory import InMemoryMetricsComputer, InMemoryMetricsStore
    from factory.metrics.runtime.runtime import MetricsRuntime
    server = ToolCatalog("empty-metrics")
    register(server, MetricsRuntime(InMemoryMetricsStore(), InMemoryMetricsComputer()))
    sample = asyncio.run(server.get_tool("metrics_seed_sample_data")).fn()
    assert sample.ok is True and sample.data.ok is False


def test_drift_and_partial_portfolio_results_remain_successful_envelopes(monkeypatch) -> None:
    tools = _tools()
    drift = tools["metrics_detect_drift"].fn(metric_id="missing")
    assert drift.ok is True and drift.data.metric_id == "missing"
    monkeypatch.setattr("factory.metrics.mcp.ingestion._query_sipp", lambda errors: errors.append("sipp_peak: query failed") or {})
    portfolio = tools["metrics_ingest_portfolio"].fn(include_veritas=False)
    assert portfolio.ok is True and portfolio.data.errors == ["sipp_peak: query failed"]


def test_public_contract_modules_do_not_import_runtime_models() -> None:
    """MCP DTOs remain independent of Metrics runtime/domain model classes."""
    import inspect
    from factory.metrics.mcp.contracts import authoring, deterministic

    for module in (authoring, deterministic):
        assert "runtime.models" not in inspect.getsource(module)


def test_authoring_nested_dto_dump_keeps_flat_tool_kwargs() -> None:
    """Decorator-normalized nested DTO data reaches authoring tools as dict kwargs."""
    from factory.metrics.mcp.contracts.authoring import DefinitionCreate

    result = _tools()["metrics_define_metric"].fn(
        definition=DefinitionCreate(id="contract-metric", name="Contract Metric").model_dump()
    )
    assert result.ok is True
    assert result.data.ok is False
    assert result.data.error == "authoring_disabled"
