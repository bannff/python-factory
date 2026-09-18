"""AI Assistant agent loop — framework-agnostic seam.

Exports:
  - AssistantLoop: Protocol defining the streaming send() contract.
  - NullAssistant: Always-importable fallback (no heavy deps).
  - resolve_assistant(config): Factory returning the Strands impl or NullAssistant.

The lean app imports ONLY this module — it never touches strands_assistant
directly, keeping the strands-agents dep fully optional.

SECURITY CONTROL #6: AssistantConfig does NOT persist/repr api_key.
  If an api_key field exists, field(repr=False) + custom __repr__ that redacts;
  resolve key lazily at model-build, don't retain.
SECURITY CONTROL #2: No repr/log/exception prints the key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol, runtime_checkable

from .assistant_config_service import (
    AssistantProvider,
    KeychainBackend,
    get_api_key,
    load_assistant_config,
    requires_api_key,
    resolve_keychain,
)


@runtime_checkable
class AssistantLoop(Protocol):
    """Streaming assistant interface consumed by the UI panel (future) and tests."""

    async def send(self, message: str) -> AsyncIterator[str]:
        """Send a user message; yield streamed text chunks."""
        ...  # pragma: no cover


class NullAssistant:
    """Graceful fallback when no model is configured or strands is unavailable.

    Always importable — zero heavy dependencies.
    """

    def __init__(self, message: str | None = None) -> None:
        self._message = message or (
            "Assistant unavailable — no model configured. "
            "Set OPENARCADE_MODEL_ID to enable the AI assistant."
        )

    async def send(self, message: str) -> AsyncIterator[str]:
        yield self._message


@dataclass(frozen=True)
class AssistantConfig:
    """Configuration for the assistant factory.

    CONTROL #6: api_key is repr=False and redacted in __repr__.
    Key is resolved lazily at model-build time, never retained beyond that.
    """

    model_id: str | None = None
    provider: str = "bedrock"
    gamelist_path: str | None = None
    system: str = "snes"
    media_root: str | None = None
    # CONTROL #6: never repr/persist the key
    api_key: str | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        """CONTROL #2: Custom repr that NEVER includes the api_key value."""
        return (
            f"AssistantConfig(model_id={self.model_id!r}, provider={self.provider!r}, "
            f"gamelist_path={self.gamelist_path!r}, system={self.system!r}, "
            f"media_root={self.media_root!r}, api_key={'<REDACTED>' if self.api_key else 'None'})"
        )

    @classmethod
    def from_env(cls) -> "AssistantConfig":
        """Build config from environment variables (back-compatible)."""
        return cls(
            model_id=os.environ.get("OPENARCADE_MODEL_ID")
            or os.environ.get("OPENARCADE_BEDROCK_MODEL"),
            provider=os.environ.get("OPENARCADE_PROVIDER", "bedrock"),
            gamelist_path=os.environ.get("OPENARCADE_GAMELIST"),
            system=os.environ.get("OPENARCADE_SYSTEM", "snes"),
            media_root=os.environ.get("OPENARCADE_MEDIA_ROOT"),
            api_key=os.environ.get("OPENARCADE_API_KEY"),
        )

    @classmethod
    def from_stored(cls, *, keychain: KeychainBackend | None = None) -> "AssistantConfig":
        """Build config from stored JSON + keychain.

        Falls back to from_env for gamelist/system/media_root.
        """
        kc = keychain or resolve_keychain()
        stored = load_assistant_config()
        provider = stored.get("provider", "bedrock")
        model_id = stored.get("model_id")

        # Resolve API key: keychain first, then env fallback
        api_key: str | None = None
        if requires_api_key(provider):
            api_key = get_api_key(provider, keychain=kc) or os.environ.get(
                "OPENARCADE_API_KEY"
            )

        return cls(
            model_id=model_id or os.environ.get("OPENARCADE_MODEL_ID"),
            provider=provider,
            gamelist_path=os.environ.get("OPENARCADE_GAMELIST"),
            system=os.environ.get("OPENARCADE_SYSTEM", "snes"),
            media_root=os.environ.get("OPENARCADE_MEDIA_ROOT"),
            api_key=api_key,
        )


def resolve_assistant(config: AssistantConfig | None = None) -> AssistantLoop:
    """Return the best available assistant implementation.

    Resolution order:
      1. If provider requires key and no key available → NullAssistant with
         honest message naming the provider.
      2. If config.model_id is set AND strands-agents is importable →
         StrandsAssistant (full MCP-backed agent).
      3. Otherwise → NullAssistant (honest fallback).

    The strands import is guarded so the lean app never breaks.
    """
    if config is None:
        config = AssistantConfig.from_env()

    if not config.model_id:
        return NullAssistant()

    # Fail-closed: provider needs key but none available
    if requires_api_key(config.provider) and not config.api_key:
        return NullAssistant(
            message=(
                f"Assistant unavailable — {config.provider} requires an API key. "
                f"Configure it in Settings → Assistant or set OPENARCADE_API_KEY."
            )
        )

    try:
        from .strands_assistant import StrandsAssistant  # noqa: F401
    except ImportError:
        return NullAssistant()

    return StrandsAssistant(config=config)
