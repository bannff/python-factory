"""Helpers for ``GraphExecutor`` — limits + safe condition builder.

Split out from ``graph.py`` to keep that module under the 200-LOC
guard once the lifecycle plugin wiring landed (Wave 2). The two
helpers don't depend on executor state — they're pure functions over
a builder/condition spec.
"""
from __future__ import annotations

import re
from typing import Any


def apply_limits(builder: Any, config: Any) -> None:
    """Apply execution limits to the graph builder.

    ``config`` is a ``GraphConfig`` Pydantic model post-uffq, but the
    helper survives a plain dict for back-compat with any non-default
    code path. Reads via ``getattr`` for either shape.
    """
    timeout = getattr(config, "execution_timeout", None) if not isinstance(
        config, dict) else config.get("execution_timeout")
    if timeout:
        try:
            builder.set_execution_timeout(float(timeout))
        except AttributeError:
            pass
    node_timeout = getattr(config, "node_timeout", None) if not isinstance(
        config, dict) else config.get("node_timeout")
    if node_timeout:
        try:
            builder.set_node_timeout(float(node_timeout))
        except AttributeError:
            pass
    max_execs = getattr(config, "max_node_executions", None) if not isinstance(
        config, dict) else config.get("max_node_executions")
    if max_execs:
        try:
            builder.set_max_node_executions(int(max_execs))
        except AttributeError:
            pass
    if isinstance(config, dict) and config.get("reset_on_revisit"):
        try:
            builder.reset_on_revisit(True)
        except AttributeError:
            pass
    # bd:python-factory-h5mju — single choke point: fill any bound still left
    # None (e.g. no explicit max_node_executions) with the platform default so
    # this build path is never unbounded either. Preserves anything set above.
    from factory.agent.runtime.graph_bounds import apply_execution_bounds
    nodes = config.get("nodes") if isinstance(config, dict) else getattr(config, "nodes", None)
    apply_execution_bounds(builder, node_count=len(nodes) if nodes else 0)


_DEFAULTS = {
    "True": True, "False": False, "None": None, "0": 0, "1": 1,
}


def build_condition(spec: str, conditions: dict[str, str]) -> Any:
    """Build a safe condition function (no ``eval``).

    Parses ``'SEARCH_TEXT' in str(state.results.get('node'))`` via
    regex — never evaluated as code.
    """
    cdef = conditions.get(spec, spec)
    state_get_m = re.search(
        r"state\.get\(['\"](\w+)['\"],\s*(True|False|None|0|1)?\)", cdef,
    )
    node_m = re.search(r"state\.results\.get\(['\"](\w+)['\"]", cdef)
    text_m = re.search(r"'([^']+)'\s+in\s+str", cdef)
    state_key = state_get_m.group(1) if state_get_m else ""
    default_token = state_get_m.group(2) if state_get_m else None
    default_value = _DEFAULTS.get(default_token, False)
    node_id = node_m.group(1) if node_m else ""
    search = text_m.group(1) if text_m else ""

    def condition_fn(state: Any) -> bool:
        if state_key:
            if isinstance(state, dict):
                return bool(state.get(state_key, default_value))
            return bool(getattr(state, state_key, default_value))
        if not node_id or not search:
            return False
        results = getattr(state, "results", {})
        if isinstance(results, dict):
            return search in str(results.get(node_id, ""))
        return False

    return condition_fn
