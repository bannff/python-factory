"""Strict trusted configuration for Agent runtime adapter selection."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class AgentRuntimeSelection(BaseModel):
    """Versioned project-owned selection of one registered runtime bundle."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["v1"] = "v1"
    runtime_adapter_id: str = Field(min_length=1, max_length=128)
    options: dict[str, Any] = Field(default_factory=dict)


def load_runtime_selection(path: str | Path | None = None) -> AgentRuntimeSelection:
    """Load trusted YAML, with one temporary env compatibility fallback."""
    configured = path or os.getenv("AGENT_RUNTIME_CONFIG")
    if configured:
        payload = yaml.safe_load(Path(configured).read_text(encoding="utf-8"))
        return AgentRuntimeSelection.model_validate(payload)
    legacy = os.getenv("AGENT_RUNTIME_ADAPTER")
    return AgentRuntimeSelection(
        runtime_adapter_id=legacy or "langchain-langgraph",
    )


__all__ = ["AgentRuntimeSelection", "load_runtime_selection"]
