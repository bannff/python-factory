"""Workflow Executor — bridges registry kind=workflow to strands_tools.workflow.

Strands ``workflow`` is an Agent ``@tool`` over ``WorkflowManager`` (not a
``MultiAgentBase`` like Graph/Swarm), so we bridge: build per-task agents
with our standard plugins, drive ``create_workflow`` + ``start_workflow``
under ``asyncio.to_thread``, and map ``workflow['task_results']`` back to
``GraphResult`` so existing event consumers keep working.

The local subclass that injects plugins + honors per-task timeout lives
in ``_workflow_manager.py``; see its docstring for the upstream SDK gap
bds. ``test_executors_workflow.py::test_canary_sdk_method_names_present``
fails fast on a future ``strands-agents-tools`` upgrade that renames
the private methods we override.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from factory.agent.runtime.ports import GraphResult

from ._envelope_scope import envelope_scope
from ._template import inject_variables
from ._workflow_manager import (
    PARENT_TOOL_SPECS,
    build_parent_agent,
    make_factory_manager,
    make_wf_id,
)

logger = logging.getLogger(__name__)


def _emit_event(event_type: str, payload: dict[str, Any]) -> None:
    """Emit brick-boundary event via tool_invoker. Fire-and-forget."""
    try:
        from factory.mcp_utils.interface import get_service
        invoker = get_service("tool_invoker")
        if invoker:
            invoker("events_publish",
                    source="agent.workflow_executor",
                    event_type=event_type, payload=payload)
    except Exception:
        pass


def _wf_error(
    graph_id: str, rid: str, error: str, results: dict[str, Any] | None = None,
    order: list[str] | None = None, elapsed: float = 0.0,
) -> GraphResult:
    """Emit graph.failed and return a run_id-tagged error GraphResult."""
    _emit_event("graph.failed", {
        "graph_id": graph_id, "workflow_id": graph_id, "run_id": rid,
        "status": "failed", "error": error,
    })
    return GraphResult(
        status="error", results={"error": error, **(results or {})},
        execution_order=order or [], execution_time=elapsed, run_id=rid,
    )


def _attr(c: Any, k: str, d: Any = None) -> Any:
    """Read field from Pydantic model or dict (uffq compat shim)."""
    return c.get(k, d) if isinstance(c, dict) else getattr(c, k, d)


def _extract_error(resp: dict) -> str:
    items = resp.get("content") or []
    if items and isinstance(items[0], dict):
        return str(items[0].get("text", ""))
    return str(resp)


def _shape_results(wf: dict) -> tuple[dict[str, Any], list[str]]:
    """Map ``workflow['task_results']`` to ``GraphResult.results`` + order."""
    raw = wf.get("task_results", {}) or {}
    by_completed: list[tuple[str, str]] = []
    results: dict[str, Any] = {}
    for task_id, tr in raw.items():
        results[task_id] = {
            "status": tr.get("status"),
            "result": tr.get("result"),
        }
        ts = tr.get("completed_at") or ""
        if ts:
            by_completed.append((str(ts), task_id))
    by_completed.sort()
    return results, [tid for _, tid in by_completed]


class WorkflowExecutor:
    """Executes a ``kind=workflow`` registration via strands_tools.workflow.

    Constructor signature mirrors ``GraphExecutor`` for parity at the
    dispatch site (``GraphExecutor.run``).
    """

    def __init__(
        self,
        config: dict[str, Any] | Any,
        swarm_registry: Any | None = None,
        agent_registry: Any | None = None,
        graph_registry: Any | None = None,
        backend: str = "strands",
    ) -> None:
        # Accept dict or typed WorkflowConfig — read via _attr.
        self.config = config
        self.swarm_registry = swarm_registry
        self.agent_registry = agent_registry
        self.graph_registry = graph_registry
        self.backend = backend
        self._mcp_tools: list[Any] | None = None  # set by GraphExecutor

    async def run(self, task: str, context: dict[str, Any]) -> GraphResult:
        """Execute the workflow. Returns ``GraphResult`` for envelope parity."""
        graph_id = _attr(self.config, "id", "unknown")
        wf_id = make_wf_id(graph_id, context.get("run_id"))
        t0 = time.monotonic()

        with envelope_scope(context) as run_id:
            rid = run_id or wf_id
            try:
                tasks = self._build_tasks(context)
            except Exception as e:
                return _wf_error(graph_id, rid, f"factory: {e}")

            _emit_event("graph.launched", {
                "graph_id": graph_id, "workflow_id": graph_id,
                "run_id": rid, "status": "running",
                "kind": "workflow", "node_count": len(tasks),
                "nodes": [t["task_id"] for t in tasks],
            })

            try:
                outcome = await asyncio.to_thread(
                    self._run_blocking, wf_id, tasks, context,
                )
            except Exception as e:
                logger.exception("Workflow %s crashed", wf_id)
                return _wf_error(graph_id, rid, str(e))

            status, order, results, err = outcome
            elapsed = time.monotonic() - t0
            if status == "completed":
                _emit_event("graph.completed", {
                    "graph_id": graph_id, "workflow_id": graph_id,
                    "run_id": rid, "status": "completed",
                    "execution_time": elapsed, "execution_order": order,
                })
                return GraphResult(
                    status="completed", execution_order=order,
                    results=results, execution_time=elapsed, run_id=rid,
                )
            return _wf_error(
                graph_id, rid, err or "workflow failed",
                results=results, order=order, elapsed=elapsed,
            )

    # --- internals ---

    def _build_tasks(self, context: dict[str, Any]) -> list[dict]:
        """Resolve factory + render template vars over runtime context."""
        from factory.agent.registry.factories import get_factory

        factory_key = _attr(self.config, "factory")
        if not factory_key:
            raise ValueError("workflow registration missing 'factory' key")
        factory = get_factory(str(factory_key))
        tasks = factory(context)
        rendered: list[dict] = []
        for t in tasks:
            tt = dict(t)
            for field in ("description", "system_prompt"):
                if field in tt and isinstance(tt[field], str):
                    tt[field] = inject_variables(tt[field], context)
            rendered.append(tt)
        return rendered

    def _run_blocking(
        self, wf_id: str, tasks: list[dict], context: dict[str, Any],
    ) -> tuple[str, list[str], dict[str, Any], str | None]:
        """Sync driver run inside ``asyncio.to_thread``."""
        node_configs = {t["task_id"]: t for t in tasks}
        Manager = make_factory_manager(node_configs, context)
        parent_tools: list[Any] = list(PARENT_TOOL_SPECS) + (self._mcp_tools or [])
        parent = build_parent_agent(parent_tools)
        manager = Manager(parent_agent=parent)

        create_resp = manager.create_workflow(wf_id, tasks)
        if create_resp.get("status") != "success":
            return "error", [], {}, _extract_error(create_resp)
        start_resp = manager.start_workflow(wf_id)
        wf = manager.get_workflow(wf_id) or {}
        results, order = _shape_results(wf)
        if start_resp.get("status") != "success":
            return "error", order, results, _extract_error(start_resp)
        return "completed", order, results, None
