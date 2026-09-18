"""Native MCP v2 server interface exposing workflow tools, resources, and prompts.

This module is the public MCP surface. It must not contain domain logic.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from factory.mcp_utils.interface import set_service
from factory.workflow.authoring import AuthoringManager, authoring_enabled
from factory.workflow.runtime.runtime import WorkflowRuntime
from factory.workflow.mcp import (
    deterministic,
    loop_deterministic,
    loop_operational,
    operational,
    execution,
    authoring,
    register_resources,
    register_prompts,
    register_views,
)


def get_runtime() -> WorkflowRuntime:
    """Create a default WorkflowRuntime from environment / defaults."""
    from factory.workflow.runtime.models import Settings
    from factory.workflow.runtime.storage.sqlite import SqliteWorkflowStorage
    from factory.workflow.runtime.execution.adapters import create_executor

    config_dir = Path(os.environ.get("WORKFLOW_CONFIG_DIR", "./config"))
    try:
        return WorkflowRuntime.from_config_dir(config_dir)
    except Exception as exc:
        if "Missing settings.yaml" not in str(exc):
            raise
        settings = Settings()
        db_path = config_dir / "data" / "workflow.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        storage = SqliteWorkflowStorage(db_path)
        storage.init_schema()
        return WorkflowRuntime(
            config_dir=config_dir,
            settings=settings,
            settings_raw=settings.model_dump(),
            workflows=[],
            storage=storage,
            executor=create_executor(),
        )


def _register_tools(registry: Any, runtime: WorkflowRuntime) -> None:
    enabled = authoring_enabled(runtime.settings_raw)
    manager = AuthoringManager(runtime.config_dir) if enabled else None
    runtime.set_runtime_flags(authoring_enabled=enabled, running_mode="stdio")
    deterministic.register(registry, runtime)
    loop_deterministic.register(registry, runtime)
    loop_operational.register(registry, runtime)
    set_service("workflow_loop_reconciler", runtime.reconcile_loops)
    operational.register(registry, runtime)
    execution.register(registry, runtime)
    from factory.workflow.runtime.background_recovery import schedule_background_recovery
    set_service(
        "workflow_background_reconciler",
        lambda submit: schedule_background_recovery(runtime, submit),
    )
    authoring.register(registry, runtime, manager)
    register_views(registry, runtime)


def create_tool_catalog(runtime: WorkflowRuntime | None = None) -> Any:
    """Create the transport-neutral Workflow tool catalog."""
    from factory.mcp_utils.runtime.tool_catalog import ToolCatalog

    active_runtime = runtime or get_runtime()
    catalog = ToolCatalog("workflow-module")
    _register_tools(catalog, active_runtime)
    register_resources(catalog, active_runtime)
    register_prompts(catalog, active_runtime)
    return catalog


def create_mcp_server(runtime: WorkflowRuntime | None = None) -> Any:
    """Return the canonical framework-neutral catalog."""
    return create_tool_catalog(runtime)


def get_capabilities() -> dict[str, Any]:
    """Delegate capability reporting to the configured runtime."""
    return get_runtime().get_capabilities()


def health_check() -> dict[str, Any]:
    """Report actual configured storage, executor, and durable readiness."""
    return get_runtime().health_check()


def describe_config_schema() -> dict[str, Any]:
    """Return the runtime's authoritative Pydantic schemas."""
    return get_runtime().describe_config_schema()
