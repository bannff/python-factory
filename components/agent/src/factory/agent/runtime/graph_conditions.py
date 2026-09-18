"""Closed registry of deterministic graph edge conditions."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .graph_output_models import resolve_output_schema

Condition = Callable[..., bool]


def _status_completed(node_result: Any) -> bool:
    return str(getattr(node_result, "status", "")).lower().endswith("completed")


def all_predecessors_valid(
    predecessors: tuple[str, ...], schemas: dict[str, str | None],
) -> Condition:
    """AND-gate every incoming edge despite Strands 1.48 OR readiness."""
    def condition(
        state: Any, *, invocation_state: dict[str, Any] | None = None,
        **_: Any,
    ) -> bool:
        results = getattr(state, "results", {})
        claim = (invocation_state or {}).get("graph_run_claim")
        ledger_nodes = getattr(getattr(claim, "record", None), "nodes", {})
        for node_id in predecessors:
            node_result = results.get(node_id)
            if node_result is None or not _status_completed(node_result):
                return False
            schema_name = schemas.get(node_id)
            if not schema_name:
                continue
            payload = None
            result = getattr(node_result, "result", None)
            structured = getattr(result, "structured_output", None)
            if structured is not None:
                payload = structured.model_dump(mode="json")
            elif node_id in ledger_nodes:
                payload = ledger_nodes[node_id].payload
            if payload is None:
                return False
            validated = resolve_output_schema(schema_name).model_validate(payload)
            if hasattr(validated, "complete") and validated.complete is not True:
                return False
        return True
    return condition


def resolve_condition(
    name: str, *, predecessors: tuple[str, ...],
    schemas: dict[str, str | None],
) -> Condition:
    """Resolve a named callable; condition strings are never evaluated."""
    if name == "all-predecessors-valid":
        return all_predecessors_valid(predecessors, schemas)
    raise ValueError(f"Unknown graph condition: {name!r}")


__all__ = ["all_predecessors_valid", "resolve_condition"]
