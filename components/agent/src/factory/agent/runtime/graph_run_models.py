"""Serializable application-owned graph run envelopes."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class GraphNodeOutput(BaseModel):
    schema_name: str
    payload: dict[str, Any]
    model_config = ConfigDict(extra="forbid")


class GraphRunRecord(BaseModel):
    schema_version: Literal[1] = 1
    graph_id: str
    run_id: str
    session_id: str
    task_digest: str
    config_digest: str
    status: Literal["running", "completed", "failed"] = "running"
    nodes: dict[str, GraphNodeOutput] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None
    model_config = ConfigDict(extra="forbid")


__all__ = ["GraphNodeOutput", "GraphRunRecord"]
