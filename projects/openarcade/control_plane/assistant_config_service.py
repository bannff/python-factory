"""Assistant config service — pure config + OS-keychain seam.

Manages provider/model selection (plain JSON) and API key storage
(OS keychain only — NEVER plaintext). MCP tools and the Settings UI
both consume this same service.

SECURITY CONTROLS:
  CONTROL #1: JSON contains ONLY provider+model_id — NEVER api_key.
  CONTROL #2: No repr/log/exception prints the key (enforced at callers).
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Protocol


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------


class AssistantProvider(str, Enum):
    """Supported LLM providers."""

    bedrock = "bedrock"
    openai = "openai"
    anthropic = "anthropic"
    gemini = "gemini"
    ollama = "ollama"
    litellm = "litellm"


def requires_api_key(provider: AssistantProvider | str) -> bool:
    """Return True if the provider needs an API key to function."""
    no_key_providers = {AssistantProvider.bedrock, AssistantProvider.ollama}
    try:
        p = AssistantProvider(provider)
    except ValueError:
        return True  # Unknown provider — assume key required
    return p not in no_key_providers


# ---------------------------------------------------------------------------
# Keychain protocol + implementations
# ---------------------------------------------------------------------------


class KeychainUnavailable(Exception):
    """Raised when no secure keychain backend is available."""


class KeychainBackend(Protocol):
    """Injectable OS keychain seam."""

    def get(self, service: str, key: str) -> str | None: ...
    def set(self, service: str, key: str, value: str) -> None: ...
    def delete(self, service: str, key: str) -> None: ...


_SERVICE = "openarcade"


class OSKeychain:
    """Wraps the `keyring` library; verifies the backend is secure at init."""

    def __init__(self) -> None:
        import keyring
        import keyring.errors

        try:
            backend = keyring.get_keyring()
        except keyring.errors.NoKeyringError as exc:
            raise KeychainUnavailable("No keyring backend available") from exc

        # Reject known-insecure backends
        backend_name = type(backend).__name__
        if backend_name in ("Keyring", "PlaintextKeyring"):
            raise KeychainUnavailable(
                f"Insecure keyring backend detected: {backend_name}"
            )
        # keyring.backends.fail.Keyring indicates no usable backend
        module = type(backend).__module__ or ""
        if "fail" in module:
            raise KeychainUnavailable("Keyring fail backend — no secure storage")

        self._keyring = keyring

    def get(self, service: str, key: str) -> str | None:
        return self._keyring.get_password(service, key)

    def set(self, service: str, key: str, value: str) -> None:
        self._keyring.set_password(service, key, value)

    def delete(self, service: str, key: str) -> None:
        try:
            self._keyring.delete_password(service, key)
        except Exception:
            pass  # Idempotent — if key doesn't exist, fine


class NullKeychain:
    """Fallback when no secure keychain is available. NEVER stores plaintext."""

    def get(self, service: str, key: str) -> str | None:
        return None

    def set(self, service: str, key: str, value: str) -> None:
        raise KeychainUnavailable(
            "No secure keychain available on this device — "
            "set the key via OPENARCADE_API_KEY env var instead."
        )

    def delete(self, service: str, key: str) -> None:
        raise KeychainUnavailable("No secure keychain available on this device.")


def resolve_keychain() -> KeychainBackend:
    """Return the best available keychain backend."""
    try:
        return OSKeychain()
    except (KeychainUnavailable, ImportError, Exception):
        return NullKeychain()


# ---------------------------------------------------------------------------
# Config file ops — CONTROL #1: JSON has provider+model_id ONLY, never api_key
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    """Resolve config directory (env override or ~/.config/openarcade/)."""
    env = os.environ.get("OPENARCADE_CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "openarcade"


def load_assistant_config(path: Path | None = None) -> dict[str, str]:
    """Load provider+model_id from assistant.json. Returns empty dict if missing."""
    config_file = (path or _config_dir()) / "assistant.json"
    if not config_file.exists():
        return {}
    text = config_file.read_text(encoding="utf-8")
    data = json.loads(text)
    # CONTROL #1: Only return safe fields
    result: dict[str, str] = {}
    if "provider" in data:
        result["provider"] = str(data["provider"])
    if "model_id" in data:
        result["model_id"] = str(data["model_id"])
    return result


def save_assistant_config(
    provider: str, model_id: str, path: Path | None = None
) -> None:
    """Persist provider+model_id to assistant.json. CONTROL #1: NEVER writes api_key."""
    config_dir = path or _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "assistant.json"
    # CONTROL #1: Only provider and model_id — no secrets
    data = {"provider": provider, "model_id": model_id}
    config_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Key ops — keychain INJECTED (testable, never touches real keychain in tests)
# ---------------------------------------------------------------------------


def store_api_key(
    provider: str, api_key: str, *, keychain: KeychainBackend
) -> None:
    """Store an API key in the OS keychain. Raises KeychainUnavailable on failure."""
    username = f"{provider}_api_key"
    keychain.set(_SERVICE, username, api_key)


def get_api_key(provider: str, *, keychain: KeychainBackend) -> str | None:
    """Retrieve an API key from the OS keychain. Returns None if not stored."""
    username = f"{provider}_api_key"
    return keychain.get(_SERVICE, username)


def clear_api_key(provider: str, *, keychain: KeychainBackend) -> None:
    """Remove an API key from the OS keychain."""
    username = f"{provider}_api_key"
    keychain.delete(_SERVICE, username)


def has_api_key(provider: str, *, keychain: KeychainBackend) -> bool:
    """Check if an API key exists in the keychain for this provider."""
    return get_api_key(provider, keychain=keychain) is not None
