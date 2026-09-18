"""Concurrency-safe envelope scope helper for graph and swarm executors."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator


@contextmanager
def envelope_scope(context: dict[str, Any]) -> Iterator[str | None]:
    """Push envelope updates from ``context`` and yield run_id.

    Mirrors the rehydrate/cleanup boilerplate that previously lived in
    GraphExecutor.run and SwarmExecutor.run. All imports are local so a
    missing mcp_utils does not break the executor; failures are silent
    by design (these are best-effort propagation hooks for telemetry).
    """
    reset_token = None
    run_id: str | None = None
    try:
        try:
            from factory.mcp_utils.interface import (
                envelope_updates_from_mapping,
                push_envelope_updates,
            )

            envelope_updates = envelope_updates_from_mapping(context)
            run_id = envelope_updates.get("run_id")
            if envelope_updates:
                try:
                    reset_token = push_envelope_updates(**envelope_updates)
                except Exception:
                    pass
        except Exception:
            pass

        yield run_id
    finally:
        if reset_token is not None:
            try:
                from factory.mcp_utils.interface import reset_envelope

                reset_envelope(reset_token)
            except Exception:
                pass
