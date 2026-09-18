"""Strict DTOs for the UI paint-carrier MCP family."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Output(BaseModel):
    model_config = ConfigDict(
        extra="forbid", strict=True, populate_by_name=True, serialize_by_alias=True,
    )


class CanvasPaintInput(_Input):
    """Permissive field values let the tool return failed envelopes."""

    target: Any
    payload: Any
    mode: Any = "snapshot"


class CanvasPayload(_Output):
    components: list[dict[str, Any]]
    name: str


class CanvasSentinel(_Output):
    target: str
    mode: str
    payload: CanvasPayload


class CanvasPaintOutput(_Output):
    canvas: CanvasSentinel = Field(alias="_a2ui_canvas")
    rendered: bool
    target: str
    mode: str
    component_count: int


class ChatPaintInput(_Input):
    payload: Any
    name: Any = None


class ChatPaintOutput(_Output):
    components: list[dict[str, Any]]
    name: str


class UIResourcePaintInput(_Input):
    body: Any
    mode: Any = "remote_dom"
    name: Any = None
    uri_suffix: Any = None


class UIResourceData(_Output):
    uri: str
    mimeType: str
    text: str


class UIResourcePaintOutput(_Output):
    type: str
    resource: UIResourceData
    factory_name: str = Field(alias="_factory_name")
    factory_mode: str = Field(alias="_factory_mode")


__all__ = [
    "CanvasPaintInput", "CanvasPaintOutput", "ChatPaintInput",
    "ChatPaintOutput", "UIResourcePaintInput", "UIResourcePaintOutput",
]
