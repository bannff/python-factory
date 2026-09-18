"""AssistantVM — single source of truth for the AI assistant state.

Shared by the landing Assistant page (nav destination) AND the floating
chat drawer so messages, config, and the resolved assistant instance are
consistent across both surfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

from .assistant_panel import ChatMessage


@dataclass
class AssistantVM:
    """View-model owning all mutable assistant state.

    Created once (Navigator.__init__) and passed to both the landing page
    builder and the overlay drawer builder.
    """

    messages: list[ChatMessage] = field(default_factory=list)
    config_open: bool = False
    is_null: bool = True

    # The resolved assistant instance (has .send(text) -> AsyncIterator[str])
    _assistant: Any = field(default=None, repr=False)
    # Reload callback -- set by Navigator after construction
    _reload_fn: Callable[[], None] | None = field(default=None, repr=False)

    @property
    def assistant(self) -> Any:
        return self._assistant

    def reload_config(self) -> None:
        """Hot-reload the assistant from saved config. Delegates to Navigator."""
        if self._reload_fn:
            self._reload_fn()

    async def send(self, text: str) -> AsyncIterator[str]:
        """Stream a response from the resolved assistant."""
        if self._assistant is None:
            return
        async for chunk in self._assistant.send(text):
            yield chunk
