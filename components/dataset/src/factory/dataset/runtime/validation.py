"""Canonical record validation for generation stage boundaries."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, Literal

from .records import ConversationRecord


def validate_conversation_records(records: Iterable[Any]) -> Iterator[Any]:
    """Validate and yield canonical ConversationRecord values lazily."""
    for index, record in enumerate(records):
        try:
            yield ConversationRecord.model_validate(record)
        except Exception as error:
            raise ValueError(f"Invalid conversation record at index {index}") from error


def validate_can_frame_records(records: Iterable[Any]) -> Iterator[Any]:
    """Validate CAN frame records (pass-through with basic shape check)."""
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(
                f"CAN frame record at index {index} must be a dict, got {type(record).__name__}"
            )
        yield record


def validate_generic_records(records: Iterable[Any]) -> Iterator[Any]:
    """Pass-through validator — length check only, no schema enforcement."""
    yield from records


def dispatch_validator(
    records: Iterable[Any],
    record_schema: Literal[
        "conversation", "can_frame", "can_artifact", "generic"
    ] = "conversation",
) -> Iterator[Any]:
    """Dispatch to the correct validator based on the recipe record schema."""
    validators = {
        "conversation": validate_conversation_records,
        "can_frame": validate_can_frame_records,
        "can_artifact": validate_generic_records,
        "generic": validate_generic_records,
    }
    validator = validators.get(record_schema)
    if validator is None:
        raise ValueError(f"Unknown record_schema: {record_schema}")
    return validator(records)
