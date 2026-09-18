"""Companion-X Migration engine registration and enrollment authority tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import yaml

from factory.mcp_utils.interface import service_binding, service_callers
from factory.mcp_utils.runtime.tool_catalog import ToolCatalog
from factory.workflow.mcp.execution import register
from factory.workflow.runtime.models import Settings


def test_companion_x_registers_bounded_migration_engine() -> None:
    root = Path(__file__).parents[5]
    raw = yaml.safe_load((root / "projects/companion_x/config/settings.yaml").read_text())
    settings = Settings.model_validate(raw)
    engines = {item.engine_id: item for item in settings.execution_engines.engines}
    migration = engines["migration_import"]
    assert migration.invoke_target.brick_name == "migration"
    assert migration.invoke_target.tool_name == "migration_apply_execution"
    assert migration.max_attempts == 3
    assert migration.max_continuations == 1000
    assert migration.outcome.success.model_dump() == {
        "pointer": "/status", "equals": "completed"}
    assert migration.outcome.continuation.model_dump() == {
        "pointer": "/status", "equals": "partial"}
    assert migration.outcome.retryable.model_dump() == {
        "pointer": "/retryable", "equals": True}


def test_only_agent_and_migration_may_enroll_execution() -> None:
    catalog = ToolCatalog("workflow")
    register(catalog, MagicMock())
    tools = {tool.name: tool for tool in asyncio.run(catalog.list_tools())}
    enroll = tools["workflow.enroll_execution"]
    append = tools["workflow.append_execution_event"]
    assert service_callers(enroll) == frozenset({"agent", "migration"})
    assert service_binding(enroll) == "enrollment"
    assert service_callers(append) == frozenset({"agent"})
    assert service_binding(append) == "execution"
