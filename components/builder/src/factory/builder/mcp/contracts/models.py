"""Strict, JSON-safe MCP contracts for Builder."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    """Base model that rejects unknown and coerced wire values."""

    model_config = ConfigDict(extra="forbid", strict=True)


class EmptyInput(StrictInput):
    """No-argument MCP input."""


class ReadUrlInput(StrictInput):
    url: str = Field(min_length=1, max_length=4096)


class SearchCodeInput(StrictInput):
    query: str = Field(min_length=1, max_length=4096)
    search_type: Literal["code", "repositories"] = "code"
    page: int = Field(default=1, ge=1, le=10_000)


class PipelineInput(StrictInput):
    pipeline_name: str = Field(min_length=1, max_length=512)


class PackageFileInput(StrictInput):
    package_name: str = Field(min_length=1, max_length=512)
    file_path: str = Field(min_length=1, max_length=4096)
    branch: str = Field(default="mainline", min_length=1, max_length=512)


class PackageFilesInput(StrictInput):
    package_name: str = Field(min_length=1, max_length=512)
    path: str = Field(default="", max_length=4096)
    branch: str = Field(default="mainline", min_length=1, max_length=512)


class CapabilitiesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: Literal["builder"]
    version: str
    adapters: list[str]
    features: list[str]


class HealthOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    healthy: bool
    adapter: str


class ConfigOptionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["string"]
    enum: list[str]
    default: str


class ConfigSchemaOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    type: Literal["object"]
    properties: dict[str, ConfigOptionOutput]


class PageFallbackOutput(BaseModel):
    """Page-read evidence retained when an adapter lacks structured data."""

    model_config = ConfigDict(extra="forbid", strict=True)
    url: str
    content: str
    status: int = Field(ge=200, le=299)


class UrlReadOutput(PageFallbackOutput):
    pass


class SearchResultOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    title: str = ""
    url: str = ""
    snippet: str = ""
    repository: str = ""
    path: str = ""
    line: int | None = Field(default=None, ge=1)


class SearchCodeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str
    results: list[SearchResultOutput]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_fallback: PageFallbackOutput | None = None


class PipelineStageOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    status: str


class PipelineOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str
    status: str
    stages: list[PipelineStageOutput]
    health_metrics: dict[str, str | int | float | bool]
    page_fallback: PageFallbackOutput | None = None


class PackageFileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    found: bool
    package: str
    path: str
    branch: str
    status: int
    content: str | None = None
    page_url: str | None = None


class PackageFilesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    package: str
    path: str
    branch: str
    files: list[str]
    count: int = Field(ge=0)
    page_fallback: PageFallbackOutput | None = None
