"""Assistant config MCP tools — get/set provider, model, API key.

register() wires these onto the passed FastMCP instance (cerv6 pattern).

SECURITY CONTROLS:
  CONTROL #2: get_assistant_config NEVER returns the key value.
  CONTROL #4: set_assistant_config returns success/fail-closed, never echoes key.
"""

from __future__ import annotations

from typing import Any

from .assistant_config_service import (
    AssistantProvider,
    KeychainBackend,
    KeychainUnavailable,
    has_api_key,
    requires_api_key,
    resolve_keychain,
    save_assistant_config,
    store_api_key,
    load_assistant_config,
)


def register(mcp: Any, *, context: Any) -> None:
    """Register assistant config tools (get_assistant_config, set_assistant_config)."""

    @mcp.tool()
    def get_assistant_config() -> dict[str, Any]:
        """Get the current assistant provider and model config.

        CONTROL #2: NEVER includes the API key value. Returns has_api_key bool.
        """
        keychain = resolve_keychain()
        stored = load_assistant_config()
        provider = stored.get("provider", "bedrock")
        return {
            "provider": provider,
            "model_id": stored.get("model_id", ""),
            "has_api_key": has_api_key(provider, keychain=keychain),
            "requires_api_key": requires_api_key(provider),
        }

    @mcp.tool()
    def set_assistant_config(
        provider: str, model_id: str, api_key: str | None = None
    ) -> dict[str, Any]:
        """Set assistant provider + model. Optionally store API key in OS keychain.

        Returns success/failure message. NEVER echoes the key back.
        """
        # Validate provider
        try:
            AssistantProvider(provider)
        except ValueError:
            return {"success": False, "message": f"Unknown provider: {provider}"}

        # Save non-secret config (CONTROL #1: JSON has no key)
        save_assistant_config(provider, model_id)

        # Store key if provided
        if api_key:
            keychain = resolve_keychain()
            try:
                store_api_key(provider, api_key, keychain=keychain)
            except KeychainUnavailable as exc:
                return {
                    "success": False,
                    "message": str(exc),
                    "config_saved": True,
                    "key_saved": False,
                }

        return {
            "success": True,
            "message": f"Assistant config saved: {provider}/{model_id}",
            "config_saved": True,
            "key_saved": bool(api_key),
        }
