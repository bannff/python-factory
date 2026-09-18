"""Pure view-model for the Settings → Assistant section.

Zero Flet imports. Maps assistant config state to presentation-ready rows.

SECURITY CONTROLS:
  CONTROL #3: API key field is password=True / store-only; after save show
    '✓ API key configured [Clear]', NEVER re-display value.
  CONTROL #5: If keychain is NullKeychain, show honest disabled state.
"""

from __future__ import annotations

from dataclasses import dataclass

from control_plane.assistant_config_service import (
    AssistantProvider,
    KeychainBackend,
    NullKeychain,
    has_api_key,
    load_assistant_config,
    requires_api_key,
)
from control_plane.model_catalog import models_for


@dataclass(frozen=True)
class AssistantSettingsVM:
    """View-model for the Settings → Assistant section."""

    provider: str
    provider_choices: tuple[str, ...]
    model_id: str
    # (label, model_id) choices for a provider dropdown; empty = free-text field.
    model_choices: tuple[tuple[str, str], ...]
    requires_api_key: bool
    has_api_key: bool
    # CONTROL #3: never contains the actual key value
    api_key_status: str  # "configured", "not_set", "not_required"
    keychain_available: bool
    # CONTROL #5: honest message when keychain unavailable
    keychain_message: str


def build_assistant_settings_vm(
    *, keychain: KeychainBackend | None = None
) -> AssistantSettingsVM:
    """Build the assistant settings VM from current config state."""
    from control_plane.assistant_config_service import resolve_keychain

    kc = keychain or resolve_keychain()
    stored = load_assistant_config()

    provider = stored.get("provider", "bedrock")
    model_id = stored.get("model_id", "")
    needs_key = requires_api_key(provider)
    keychain_available = not isinstance(kc, NullKeychain)

    # CONTROL #3: status string, never the actual key
    if not needs_key:
        api_key_status = "not_required"
    elif has_api_key(provider, keychain=kc):
        api_key_status = "configured"
    else:
        api_key_status = "not_set"

    # CONTROL #5: honest message
    if keychain_available:
        keychain_message = ""
    else:
        keychain_message = (
            "No secure keychain available on this device — "
            "set the key via OPENARCADE_API_KEY env var instead."
        )

    return AssistantSettingsVM(
        provider=provider,
        provider_choices=tuple(p.value for p in AssistantProvider),
        model_id=model_id,
        model_choices=models_for(provider),
        requires_api_key=needs_key,
        has_api_key=api_key_status == "configured",
        api_key_status=api_key_status,
        keychain_available=keychain_available,
        keychain_message=keychain_message,
    )
