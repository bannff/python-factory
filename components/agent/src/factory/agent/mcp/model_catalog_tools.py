"""Deterministic Agent MCP tool exposing the safe chat-model catalog.

Delegates only to ``factory.llm_gateway.interface.list_chat_models`` and
projects each descriptor onto an Agent-local DTO carrying ``model_id``/
``provider``/``model`` plus OpenRouter's own public per-token pricing when
available. No endpoint, credential env name, base URL, secret, or raw
catalog error crosses the boundary: any unavailable or malformed catalog
collapses to one fixed safe ``ToolResult`` error.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from pydantic import ValidationError

from factory.mcp_utils.interface import ToolResult, deterministic, fail, ok

from .contracts.model_catalog import (
    ChatModelDTO, ModelCatalogInput, ModelCatalogOutput,
)

if TYPE_CHECKING:
    from ..agent import SuperAgent

CATALOG_UNAVAILABLE = "model_catalog_unavailable"


def build_model_catalog(*, refresh: bool = False) -> ModelCatalogOutput:
    """Project the gateway catalog onto Agent-local safe descriptors.

    Raises ``ValueError``/``ValidationError`` when the catalog is unavailable
    or malformed; the tool maps either to the single fixed safe error.
    """
    from factory.llm_gateway.interface import list_chat_models

    models = [
        ChatModelDTO(
            model_id=item.model_id, provider=item.provider, model=item.model,
            prompt_usd_per_token=item.pricing.prompt_usd_per_token if item.pricing else None,
            completion_usd_per_token=item.pricing.completion_usd_per_token if item.pricing else None,
        )
        for item in list_chat_models(refresh=refresh)
    ]
    return ModelCatalogOutput(count=len(models), models=models)


def register(mcp: Any, agent: "SuperAgent") -> None:
    """Register the deterministic ``agent_list_models`` catalog tool."""
    del agent  # ambient catalog; no per-agent state is read

    @mcp.tool()
    @deterministic(input_model=ModelCatalogInput, output_model=ModelCatalogOutput)
    def agent_list_models(refresh: bool = False) -> ToolResult[ModelCatalogOutput]:
        """List configured chat models as safe id/provider/model descriptors."""
        try:
            return ok(build_model_catalog(refresh=refresh))
        except (ValueError, ValidationError, OSError):
            return fail(CATALOG_UNAVAILABLE)


__all__ = ["CATALOG_UNAVAILABLE", "build_model_catalog", "register"]
