"""Pydantic v2 MCP boundary models for sandbox lifecycle tools."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import StrictModel
from .nested_models import SandboxEnvironmentInfo


class SandboxProvisionRequest(StrictModel):
    instance_type: str = Field(default="t3.micro", min_length=1, max_length=128)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)
    auto_terminate: bool = True
    ami_id: str | None = Field(default=None, min_length=1, max_length=256)
    profile: str | None = Field(default=None, min_length=1, max_length=128)


class SandboxProvisionResult(StrictModel):
    success: Literal[True] = True
    environment: SandboxEnvironmentInfo
    profile: str | None = None


class SandboxEnvironmentRequest(StrictModel):
    env_id: str = Field(min_length=1, max_length=256)


class SandboxTerminateResult(StrictModel):
    success: Literal[True] = True
    env_id: str


class SandboxStatusResult(StrictModel):
    found: bool
    environment: SandboxEnvironmentInfo | None = None
    error: str | None = None


__all__ = [
    "SandboxEnvironmentRequest",
    "SandboxProvisionRequest",
    "SandboxProvisionResult",
    "SandboxStatusResult",
    "SandboxTerminateResult",
]
