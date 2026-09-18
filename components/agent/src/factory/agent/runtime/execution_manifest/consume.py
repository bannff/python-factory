"""Strict single-stream consumer for manifest-assembled native Graphs."""
from __future__ import annotations

import asyncio
import inspect
from contextlib import aclosing
from dataclasses import dataclass
from typing import Any, Callable

from .assemble import AssembledExecution
from .canonical import canonical_bytes
from .ports import EvidenceSink
from .result_serialization import json_safe, serialize_terminal

DEFAULT_MAX_RAW_EVENT_BYTES = 1024 * 1024
MAX_NATIVE_EVENT_TYPE_LENGTH = 128


class NullEvidenceSink:
    async def persist(
        self, sequence: int, event: dict[str, Any], *, terminal: bool,
    ) -> None:
        return None


@dataclass(frozen=True)
class StreamOutcome:
    translated_events: tuple[Any, ...]
    result: dict[str, Any]


async def consume_execution_stream(
    assembled: AssembledExecution, *, evidence_sink: EvidenceSink | None = None,
    translator: Callable[[dict[str, Any]], Any] | None = None,
    invocation_state: dict[str, Any] | None = None,
    max_raw_event_bytes: int = DEFAULT_MAX_RAW_EVENT_BYTES,
) -> StreamOutcome:
    """Invoke ``graph.stream_async`` exactly once and fail closed on protocol drift."""
    if type(max_raw_event_bytes) is not int or max_raw_event_bytes <= 0:
        raise ValueError("raw event max must be a positive integer")
    sink = evidence_sink or NullEvidenceSink()
    translate = translator or (lambda event: event)
    terminal: Any | None = None
    translated: list[Any] = []
    sequence = 0
    try:
        stream = assembled.graph.stream_async(
            assembled.manifest.invocation.task,
            invocation_state={
                **dict(assembled.manifest.invocation.invocation_state),
                **dict(invocation_state or {}),
            },
        )
        async with aclosing(stream):
            async for event in stream:
                event_type = event.get("type") if isinstance(event, dict) else None
                if (
                    type(event_type) is not str or not event_type
                    or len(event_type) > MAX_NATIVE_EVENT_TYPE_LENGTH
                    or not event_type.isprintable()
                ):
                    raise ValueError("malformed top-level Strands stream event")
                if terminal is not None:
                    if event_type == "multiagent_result":
                        raise ValueError("duplicate top-level terminal event")
                    raise ValueError("received a post-terminal stream event")
                raw = json_safe(event)
                if not isinstance(raw, dict):
                    raise ValueError("raw stream event did not serialize to an object")
                if len(canonical_bytes(raw)) > max_raw_event_bytes:
                    raise ValueError("raw stream event exceeds configured evidence bound")
                direct_terminal = event_type == "multiagent_result"
                await sink.persist(sequence, raw, terminal=direct_terminal)
                sequence += 1
                if direct_terminal:
                    if terminal is not None:
                        raise ValueError("duplicate top-level terminal event")
                    terminal = event.get("result")
                    if terminal is None:
                        raise ValueError("top-level terminal event has no result")
                    continue
                item = translate(raw)
                if inspect.isawaitable(item):
                    item = await item
                translated.append(item)
        if terminal is None:
            raise ValueError("Strands stream ended without a top-level terminal")
        provenance = {
            "manifest_digest": assembled.manifest.digest.value,
            "graph_id": assembled.manifest.graph_id,
            "origin": assembled.manifest.origin.model_dump(mode="json"),
            "records": [item.model_dump(mode="json") for item in assembled.manifest.provenance],
        }
        return StreamOutcome(
            translated_events=tuple(translated),
            result=serialize_terminal(terminal, provenance),
        )
    finally:
        # MCPClient.stop() joins its SDK background thread. Run deterministic
        # Agent ToolRegistry cleanup off-loop, after aclosing has cancelled and
        # awaited every nested Graph/Swarm stream.
        await asyncio.to_thread(assembled.close)


__all__ = [
    "DEFAULT_MAX_RAW_EVENT_BYTES", "NullEvidenceSink", "StreamOutcome",
    "consume_execution_stream",
]
