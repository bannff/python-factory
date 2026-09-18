"""In-memory Builder adapter for local development and tests."""
from __future__ import annotations

from ..models import (
    CodeSearchResult,
    PackageFile,
    PackageFiles,
    PageReadFailure,
    PageReadSuccess,
    PipelineDetails,
)


class MockBuilderAdapter:
    """BuilderPort implementation with deterministic local data."""

    def __init__(self) -> None:
        self._files: dict[str, str] = {}
        self._packages: dict[str, list[str]] = {}

    def seed_file(self, package: str, path: str, content: str) -> None:
        self._files[f"{package}/{path}"] = content
        self._packages.setdefault(package, []).append(path)

    async def read_url(self, url: str) -> PageReadSuccess:
        return PageReadSuccess(url=url, content=f"Mock content for {url}", status=200)

    async def search_code(
        self, query: str, search_type: str = "code", page: int = 1,
    ) -> CodeSearchResult:
        return CodeSearchResult(query=query, results=[], total=0, page=page)

    async def get_pipeline_details(self, pipeline_name: str) -> PipelineDetails:
        return PipelineDetails(name=pipeline_name, status="healthy", stages=[], health_metrics={})

    async def read_package_file(
        self, package_name: str, file_path: str, branch: str = "mainline",
    ) -> PackageFile | PageReadSuccess | PageReadFailure:
        content = self._files.get(f"{package_name}/{file_path}")
        if content is None:
            return PageReadFailure(
                url=f"mock://{package_name}/{file_path}", status=404, error_code="http_error",
            )
        return PackageFile(content=content)

    async def list_package_files(
        self, package_name: str, path: str = "", branch: str = "mainline",
    ) -> PackageFiles:
        files = self._packages.get(package_name, [])
        visible = [file for file in files if not path or file.startswith(path)]
        return PackageFiles(files=visible, count=len(visible))

    def health_check(self) -> dict[str, object]:
        return {"healthy": True, "adapter": "mock"}
