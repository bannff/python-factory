"""Strict typed contracts for the Agent safe chat-model catalog tool.

Egress exposes ``model_id``/``provider``/``model`` plus OpenRouter's own
public per-token USD pricing when available (``prompt_usd_per_token``/
``completion_usd_per_token`` — both ``None`` for non-OpenRouter providers,
which have no comparable public pricing source). No endpoint, base URL,
credential env name, secret, or raw catalog error crosses the boundary.
"""
from __future__ import annotations

from .discovery import StrictDTO


class ModelCatalogInput(StrictDTO):
    """List the configured safe chat-model catalog.

    ``refresh`` bypasses the cached provider catalog and re-fetches live.
    """

    refresh: bool = False


class ChatModelDTO(StrictDTO):
    """One non-secret model choice suitable for MCP and frontend projection."""

    model_id: str
    provider: str
    model: str
    prompt_usd_per_token: float | None = None
    completion_usd_per_token: float | None = None


class ModelCatalogOutput(StrictDTO):
    count: int
    models: list[ChatModelDTO]


__all__ = ["ChatModelDTO", "ModelCatalogInput", "ModelCatalogOutput"]
