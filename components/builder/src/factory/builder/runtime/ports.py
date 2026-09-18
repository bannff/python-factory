"""Protocol interfaces for Builder adapters."""
from __future__ import annotations

from typing import Protocol

from .models import (
    CodeSearchResult,
    PackageFile,
    PackageFiles,
    PageReadFailure,
    PageReadSuccess,
    PipelineDetails,
)


class BuilderPort(Protocol):
    """Transport-neutral access to internal Builder tooling."""

    async def read_url(self, url: str) -> PageReadSuccess | PageReadFailure: ...

    async def search_code(
        self, query: str, search_type: str = "code", page: int = 1,
    ) -> CodeSearchResult | PageReadSuccess | PageReadFailure: ...

    async def get_pipeline_details(
        self, pipeline_name: str,
    ) -> PipelineDetails | PageReadSuccess | PageReadFailure: ...

    async def read_package_file(
        self, package_name: str, file_path: str, branch: str = "mainline",
    ) -> PackageFile | PageReadSuccess | PageReadFailure: ...

    async def list_package_files(
        self, package_name: str, path: str = "", branch: str = "mainline",
    ) -> PackageFiles | PageReadSuccess | PageReadFailure: ...

    def health_check(self) -> dict[str, object]: ...
