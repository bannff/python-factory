"""Safe catalog of configured chat models."""
from __future__ import annotations

import os
from dataclasses import dataclass

from .chat_profile import resolve_chat_profile
from .openai_compat_policy import configured_profile_names
from .openrouter_catalog import ModelPricing, openrouter_models, openrouter_pricing


#: The variable that selects the deployment's chat model. Every ambient
#: consumer (the catalog below, side-chat planning) must resolve THIS, so no
#: consumer hand-maintains a default that can diverge from what chat uses.
CONFIGURED_CHAT_MODEL_ENV = "COMPANION_X_CHAT_MODEL"


def configured_chat_model_id() -> str:
    """Return the configured chat model selector ("" when unset)."""
    return os.getenv(CONFIGURED_CHAT_MODEL_ENV, "").strip()


@dataclass(frozen=True, slots=True)
class ChatModelDescriptor:
    """Non-secret model choice suitable for MCP and frontend projection."""

    model_id: str
    provider: str
    model: str
    pricing: ModelPricing | None = None


def list_chat_models(*, refresh: bool = False) -> tuple[ChatModelDescriptor, ...]:
    """List configured choices without exposing endpoints or credential names.

    The env default leads. When OpenRouter is configured, the live provider
    catalog (cached; offline falls back to the last cache) follows so the
    picker offers every OpenRouter model, not just the default — each carries
    OpenRouter's own per-token USD pricing when the catalog has it, so the
    picker can show and sort by cost without the owner asking. Named
    openai-compat profiles come last (no pricing source for a local/self-
    hosted endpoint).
    """
    candidates: list[str] = []
    default = configured_chat_model_id()
    if default:
        candidates.append(default)
    openrouter_active = _openrouter_configured(default)
    pricing_by_model = openrouter_pricing(refresh=refresh) if openrouter_active else {}
    if openrouter_active:
        candidates.extend(f"openrouter/{name}" for name in openrouter_models(refresh=refresh))
    candidates.extend(
        f"openai-compat/{name}" for name in configured_profile_names()
    )
    if not candidates:
        raise ValueError("chat model catalog unavailable")
    result: list[ChatModelDescriptor] = []
    seen: set[tuple[str, str]] = set()
    try:
        for model_id in dict.fromkeys(candidates):
            profile = resolve_chat_profile(model_id)
            key = (profile.provider, profile.model)
            if key in seen:
                continue
            seen.add(key)
            result.append(ChatModelDescriptor(
                model_id=model_id, provider=profile.provider, model=profile.model,
                pricing=pricing_by_model.get(profile.model) if profile.provider == "openrouter" else None,
            ))
    except ValueError as exc:
        raise ValueError("chat model catalog unavailable") from exc
    if not result:
        raise ValueError("chat model catalog unavailable")
    return tuple(result)


def _openrouter_configured(default: str) -> bool:
    if not os.getenv("OPENROUTER_API_KEY", "").strip():
        return False
    return default == "openrouter" or default.startswith("openrouter/")


__all__ = [
    "CONFIGURED_CHAT_MODEL_ENV",
    "ChatModelDescriptor",
    "configured_chat_model_id",
    "list_chat_models",
]
