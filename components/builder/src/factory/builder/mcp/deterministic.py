"""Deterministic typed MCP tools for Builder."""
from __future__ import annotations

from typing import Any
from factory.mcp_utils.interface import ToolResult, deterministic, ok
from factory.mcp_utils.registration import typed_tool

from ..core import SUPPORTED_ADAPTERS
from ..runtime.runtime import BuilderRuntime
from .contracts.models import (
    CapabilitiesOutput,
    ConfigOptionOutput,
    ConfigSchemaOutput,
    EmptyInput,
    HealthOutput,
)


def register(mcp: Any, runtime: BuilderRuntime) -> None:
    """Register deterministic tools."""

    @typed_tool(mcp)
    @deterministic(input_model=EmptyInput, output_model=CapabilitiesOutput)
    def builder_get_capabilities() -> ToolResult[CapabilitiesOutput]:
        """Return machine-readable capabilities for Builder."""
        EmptyInput.model_validate({})
        return ok(CapabilitiesOutput(
            name="builder", version="0.1.0", adapters=SUPPORTED_ADAPTERS,
            features=["code_package_read", "code_search", "pipeline_inspection", "internal_website_read"],
        ))

    @typed_tool(mcp)
    @deterministic(input_model=EmptyInput, output_model=HealthOutput)
    def builder_health_check() -> ToolResult[HealthOutput]:
        """Fast readiness probe for Builder."""
        EmptyInput.model_validate({})
        health = runtime.health_check()
        return ok(HealthOutput(
            healthy=bool(health.get("healthy", False)),
            adapter=health.get("adapter") if isinstance(health.get("adapter"), str) else "unknown",
        ))

    @typed_tool(mcp)
    @deterministic(input_model=EmptyInput, output_model=ConfigSchemaOutput)
    def builder_describe_config_schema() -> ToolResult[ConfigSchemaOutput]:
        """Describe Builder configuration schema."""
        EmptyInput.model_validate({})
        return ok(ConfigSchemaOutput(type="object", properties={
            "adapter": ConfigOptionOutput(
                type="string", enum=["mock", "mcp_proxy"], default="mock",
            ),
        }))
