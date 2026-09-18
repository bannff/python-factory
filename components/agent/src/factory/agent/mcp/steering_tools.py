"""Typed Agent steering document MCP tools."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from factory.mcp_utils.interface import ToolResult, authoring, deterministic, fail, ok

from ..authoring import authoring_enabled
from ..runtime.steering_documents import (
    SteeringDocument, create_steering, delete_steering, list_steering, read_steering,
    update_steering,
)
from .contracts.discovery import EmptyInput
from .contracts.steering import (
    SteeringCreateInput, SteeringDeleteInput, SteeringDeleteOutput, SteeringDetailOutput,
    SteeringListOutput, SteeringMutationOutput, SteeringRefInput, SteeringSummary,
    SteeringUpdateInput,
)

if TYPE_CHECKING:
    from ..agent import SuperAgent


def _summary(document: SteeringDocument) -> SteeringSummary:
    return SteeringSummary(id=document.id, title=document.title, sha256=document.sha256)


def _detail(document: SteeringDocument) -> SteeringDetailOutput:
    return SteeringDetailOutput(**_summary(document).model_dump(), content=document.content)


def register(mcp: Any, agent: "SuperAgent") -> None:
    @mcp.tool()
    @deterministic(input_model=EmptyInput, output_model=SteeringListOutput)
    def agent_list_steering() -> ToolResult[SteeringListOutput]:
        documents = [_summary(document) for document in list_steering()]
        return ok(SteeringListOutput(count=len(documents), documents=documents))

    @mcp.tool()
    @deterministic(input_model=SteeringRefInput, output_model=SteeringDetailOutput)
    def agent_read_steering(document_id: str) -> ToolResult[SteeringDetailOutput]:
        document = read_steering(document_id)
        return fail("steering_not_found") if document is None else ok(_detail(document))

    if not authoring_enabled(getattr(agent, "settings", None)):
        return

    @mcp.tool()
    @authoring(input_model=SteeringCreateInput, output_model=SteeringMutationOutput)
    def agent_create_steering(
        document_id: str, content: str,
    ) -> ToolResult[SteeringMutationOutput]:
        try:
            document = create_steering(document_id, content)
        except FileExistsError:
            return fail("steering_exists")
        except (OSError, ValueError):
            return fail("steering_write_failed")
        return ok(SteeringMutationOutput(created=True, document=_detail(document)))

    @mcp.tool()
    @authoring(input_model=SteeringUpdateInput, output_model=SteeringMutationOutput)
    def agent_update_steering(
        document_id: str, content: str, expected_sha256: str,
    ) -> ToolResult[SteeringMutationOutput]:
        try:
            document = update_steering(document_id, content, expected_sha256)
        except RuntimeError:
            return fail("steering_revision_conflict")
        except (OSError, ValueError):
            return fail("steering_write_failed")
        return ok(SteeringMutationOutput(created=False, document=_detail(document)))

    @mcp.tool()
    @authoring(input_model=SteeringDeleteInput, output_model=SteeringDeleteOutput)
    def agent_delete_steering(
        document_id: str, expected_sha256: str,
    ) -> ToolResult[SteeringDeleteOutput]:
        try:
            delete_steering(document_id, expected_sha256)
        except FileNotFoundError:
            return fail("steering_not_found")
        except RuntimeError:
            return fail("steering_revision_conflict")
        except OSError:
            return fail("steering_write_failed")
        return ok(SteeringDeleteOutput(deleted=True, document_id=document_id))


__all__ = ["register"]
