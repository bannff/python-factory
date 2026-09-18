"""Strict nested DTOs used by Sandbox MCP contracts."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from ..core import EnvironmentStatus
from .contracts import StrictModel


class SandboxEnvironmentInfo(StrictModel):
    env_id: str
    status: EnvironmentStatus
    instance_type: str
    created_at: str
    public_ip: str | None = None
    private_ip: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SandboxAAAMockConfig(StrictModel):
    enabled: bool = False
    service_name: str = ""
    operations: list[str] = Field(default_factory=list)
    relationships: list[dict[str, str]] = Field(default_factory=list)
    bypass_mode: str = "authorize_all"


class SandboxOdinMockConfig(StrictModel):
    enabled: bool = False
    material_sets: dict[str, dict[str, str]] = Field(default_factory=dict)


class SandboxCloudAuthMockConfig(StrictModel):
    enabled: bool = False
    bypass_mode: str = "disable"
    issuer: str = "https://mock-cloudauth.localhost"
    token_endpoint: str = "/oauth2/token"


class SandboxCoralMockConfig(StrictModel):
    enabled: bool = False
    service_stubs: list[dict[str, Any]] = Field(default_factory=list)


class SandboxTurtleMockConfig(StrictModel):
    enabled: bool = False
    credential_paths: list[str] = Field(default_factory=list)


class SandboxServiceMockConfig(StrictModel):
    aaa: SandboxAAAMockConfig = Field(default_factory=SandboxAAAMockConfig)
    odin: SandboxOdinMockConfig = Field(default_factory=SandboxOdinMockConfig)
    cloudauth: SandboxCloudAuthMockConfig = Field(default_factory=SandboxCloudAuthMockConfig)
    coral: SandboxCoralMockConfig = Field(default_factory=SandboxCoralMockConfig)
    turtle: SandboxTurtleMockConfig = Field(default_factory=SandboxTurtleMockConfig)


__all__ = [
    "SandboxAAAMockConfig", "SandboxCloudAuthMockConfig", "SandboxCoralMockConfig",
    "SandboxEnvironmentInfo", "SandboxOdinMockConfig", "SandboxServiceMockConfig",
    "SandboxTurtleMockConfig",
]
