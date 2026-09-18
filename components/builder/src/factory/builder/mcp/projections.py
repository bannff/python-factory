"""One-way MCP projections of transport-neutral Builder result DTOs."""
from __future__ import annotations

from ..runtime.models import (
    CodeSearchResult,
    PackageFile,
    PackageFiles,
    PageReadFailure,
    PageReadSuccess,
    PipelineDetails,
)
from .contracts.models import (
    PackageFileOutput,
    PackageFilesOutput,
    PageFallbackOutput,
    PipelineOutput,
    PipelineStageOutput,
    SearchCodeOutput,
    SearchResultOutput,
    UrlReadOutput,
)


def _fallback(result: PageReadSuccess) -> PageFallbackOutput:
    return PageFallbackOutput(url=result.url, content=result.content, status=result.status)


def url_read(result: object) -> UrlReadOutput | None:
    if not isinstance(result, PageReadSuccess):
        return None
    return UrlReadOutput(url=result.url, content=result.content, status=result.status)


def search_code(result: object, query: str, page: int) -> SearchCodeOutput | None:
    if isinstance(result, PageReadSuccess):
        return SearchCodeOutput(query=query, results=[], total=0, page=page, page_fallback=_fallback(result))
    if not isinstance(result, CodeSearchResult):
        return None
    rows = [SearchResultOutput(**item.model_dump()) for item in result.results]
    return SearchCodeOutput(query=result.query, results=rows, total=result.total, page=result.page)


def pipeline(result: object, pipeline_name: str) -> PipelineOutput | None:
    if isinstance(result, PageReadSuccess):
        return PipelineOutput(
            name=pipeline_name, status="page_read", stages=[], health_metrics={},
            page_fallback=_fallback(result),
        )
    if not isinstance(result, PipelineDetails):
        return None
    stages = [PipelineStageOutput(**stage.model_dump()) for stage in result.stages]
    return PipelineOutput(
        name=result.name, status=result.status, stages=stages, health_metrics=result.health_metrics,
    )


def package_file(result: object, package: str, path: str, branch: str) -> PackageFileOutput | None:
    if isinstance(result, PageReadFailure) and result.status == 404:
        return PackageFileOutput(found=False, package=package, path=path, branch=branch, status=404)
    if isinstance(result, PageReadSuccess):
        return PackageFileOutput(
            found=True, package=package, path=path, branch=branch, status=result.status,
            content=result.content, page_url=result.url,
        )
    if not isinstance(result, PackageFile):
        return None
    return PackageFileOutput(
        found=True, package=package, path=path, branch=branch, status=result.status, content=result.content,
    )


def package_files(result: object, package: str, path: str, branch: str) -> PackageFilesOutput | None:
    if isinstance(result, PageReadSuccess):
        return PackageFilesOutput(
            package=package, path=path, branch=branch, files=[], count=0,
            page_fallback=_fallback(result),
        )
    if not isinstance(result, PackageFiles):
        return None
    return PackageFilesOutput(package=package, path=path, branch=branch, files=result.files, count=result.count)
