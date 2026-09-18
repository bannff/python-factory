"""Safe provider profiles for framework-native chat model construction."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .openai_compat_policy import resolve_profile_inputs

_OPENROUTER_PREFIX = "openrouter/"
_OLLAMA_PREFIX = "ollama/"
_OPENAI_COMPAT_PREFIX = "openai-compat/"


@dataclass(frozen=True, slots=True)
class ChatProfile:
    """Non-secret configuration for one framework-native chat model."""

    provider: str
    model: str
    base_url: str | None = None
    api_key_env: str | None = None
    default_headers: dict[str, str] = field(default_factory=dict)
    max_retries: int = 2


def resolve_chat_profile(model_id: str) -> ChatProfile:
    """Resolve a prefixed model id without reading or returning credentials."""
    candidate = model_id.strip()
    if not candidate:
        raise ValueError("model id is required")
    if candidate == "openrouter":
        return _openrouter_profile(os.getenv("OPENROUTER_MODEL", ""))
    if candidate.startswith(_OPENROUTER_PREFIX):
        return _openrouter_profile(candidate.removeprefix(_OPENROUTER_PREFIX))
    if candidate.startswith(_OLLAMA_PREFIX):
        return _ollama_profile(candidate.removeprefix(_OLLAMA_PREFIX))
    if candidate.startswith(_OPENAI_COMPAT_PREFIX):
        return _openai_compat_profile(candidate.removeprefix(_OPENAI_COMPAT_PREFIX))
    return ChatProfile(provider="bedrock", model=candidate)


def _openrouter_profile(model: str) -> ChatProfile:
    native_model = _required_model(model)
    headers = {
        key: value
        for key, value in (
            ("HTTP-Referer", os.getenv("OPENROUTER_HTTP_REFERER", "").strip()),
            ("X-Title", os.getenv("OPENROUTER_APP_TITLE", "").strip()),
        )
        if value
    }
    return ChatProfile(
        provider="openrouter",
        model=native_model,
        base_url=os.getenv(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1",
        ).strip(),
        api_key_env="OPENROUTER_API_KEY",
        default_headers=headers,
        max_retries=_positive_int("OPENROUTER_MAX_RETRIES", default=2),
    )


def _ollama_profile(model: str) -> ChatProfile:
    return ChatProfile(
        provider="ollama",
        model=_required_model(model),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
    )


def _openai_compat_profile(name: str) -> ChatProfile:
    base_url, api_key_env, model = resolve_profile_inputs(name)
    return ChatProfile(
        provider="openai-compat", model=model,
        base_url=base_url, api_key_env=api_key_env,
    )


def _required_model(model: str) -> str:
    candidate = model.strip()
    if not candidate:
        raise ValueError("provider-native model id is required")
    return candidate


def _positive_int(name: str, *, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


__all__ = ["ChatProfile", "resolve_chat_profile"]
