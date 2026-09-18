"""File-level operational typed MCP tools for Builder."""
from __future__ import annotations

from typing import Any
from factory.mcp_utils.interface import ToolResult, operational
from factory.mcp_utils.registration import typed_tool
from factory.mcp_utils.runtime.tool_failure import tool_execution_failure

from ..runtime.runtime import BuilderRuntime
from .contracts.models import (
    PackageFileInput,
    PackageFileOutput,
    PackageFilesInput,
    PackageFilesOutput,
)
from .projections import package_file, package_files


def register(mcp: Any, runtime: BuilderRuntime) -> None:
    """Register file-level operational tools."""

    @typed_tool(mcp)
    @operational(input_model=PackageFileInput, output_model=PackageFileOutput)
    async def builder_read_package_file(
        package_name: str, file_path: str, branch: str = "mainline",
    ) -> ToolResult[PackageFileOutput]:
        """Read a specific file from a code package."""
        request = PackageFileInput.model_validate({
            "package_name": package_name, "file_path": file_path, "branch": branch,
        })
        try:
            data = await runtime.read_package_file(
                request.package_name, request.file_path, request.branch,
            )
        except Exception:
            return tool_execution_failure(builder_read_package_file)
        output = package_file(data, request.package_name, request.file_path, request.branch)
        return ToolResult(ok=True, data=output) if output is not None else tool_execution_failure(builder_read_package_file)

    @typed_tool(mcp)
    @operational(input_model=PackageFilesInput, output_model=PackageFilesOutput)
    async def builder_list_package_files(
        package_name: str, path: str = "", branch: str = "mainline",
    ) -> ToolResult[PackageFilesOutput]:
        """List files in a code package directory."""
        request = PackageFilesInput.model_validate({
            "package_name": package_name, "path": path, "branch": branch,
        })
        try:
            data = await runtime.list_package_files(
                request.package_name, request.path, request.branch,
            )
        except Exception:
            return tool_execution_failure(builder_list_package_files)
        output = package_files(data, request.package_name, request.path, request.branch)
        return ToolResult(ok=True, data=output) if output is not None else tool_execution_failure(builder_list_package_files)
