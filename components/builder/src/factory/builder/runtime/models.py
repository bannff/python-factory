"""Transport-neutral result DTOs for Builder adapters."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PageReadSuccess(_Result):
    """Successful page read used as a fallback by URL-backed operations."""

    kind: Literal["page"] = "page"
    url: str
    content: str
    status: int = Field(ge=200, le=299)


class PageReadFailure(_Result):
    """Safe page-read failure that retains an available HTTP status."""

    kind: Literal["page_error"] = "page_error"
    url: str
    status: int | None = Field(default=None, ge=100, le=599)
    error_code: Literal["http_error", "request_failed"]


class SearchResult(_Result):
    title: str = ""
    url: str = ""
    snippet: str = ""
    repository: str = ""
    path: str = ""
    line: int | None = Field(default=None, ge=1)


class CodeSearchResult(_Result):
    kind: Literal["search"] = "search"
    query: str
    results: list[SearchResult]
    total: int = Field(ge=0)
    page: int = Field(ge=1)


class PipelineStage(_Result):
    name: str
    status: str


class PipelineDetails(_Result):
    kind: Literal["pipeline"] = "pipeline"
    name: str
    status: str
    stages: list[PipelineStage]
    health_metrics: dict[str, str | int | float | bool]


class PackageFile(_Result):
    kind: Literal["package_file"] = "package_file"
    content: str
    status: int = Field(default=200, ge=200, le=299)


class PackageFiles(_Result):
    kind: Literal["package_files"] = "package_files"
    files: list[str]
    count: int = Field(ge=0)


BuilderResult = PageReadSuccess | PageReadFailure | CodeSearchResult | PipelineDetails | PackageFile | PackageFiles
