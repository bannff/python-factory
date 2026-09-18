"""mcp_utils' own local twin of the session/memory bricks' credential-free
completion builder (feature-map row 19).

Mirrors ``factory.session.runtime.title_complete``'s pattern exactly — no
cross-brick import of another brick's internals, resolved from
``llm_gateway``'s shared, credential-free ``ChatProfile`` so a side turn's
planner uses the exact provider/model chat itself resolves to.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from factory.llm_gateway.interface import resolve_chat_profile


def build_mcp_utils_complete(model_id: str) -> Callable[[str], str]:
    """Build a synchronous ``complete(prompt) -> str`` over an official
    LangChain chat model, resolved from the same profile chat itself uses."""
    profile = resolve_chat_profile(model_id)
    model = _build_model(profile)

    def complete(prompt: str) -> str:
        response = model.invoke(prompt)
        content = getattr(response, "content", response)
        return content if isinstance(content, str) else str(content)

    return complete


def _build_model(profile: Any) -> Any:
    if profile.provider == "openrouter":
        api_key = os.getenv(profile.api_key_env or "", "").strip()
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for OpenRouter chat")
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=profile.model, base_url=profile.base_url, api_key=api_key,
            default_headers=profile.default_headers, max_retries=profile.max_retries,
            timeout=profile.timeout_seconds,
        )
    if profile.provider == "bedrock":
        from langchain_aws import ChatBedrockConverse
        return ChatBedrockConverse(model=profile.model, region_name=profile.region)
    if profile.provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=profile.model, base_url=profile.base_url)
    raise ValueError(f"Unsupported chat provider for side-turn planner: {profile.provider}")


__all__ = ["build_mcp_utils_complete"]
