"""Public interface for llm_gateway brick.

Other bricks should import from here, not from runtime internals.
"""

from .runtime.ports import (
    LLMProvider,
    EmbeddingProvider,
    LLMMessage,
    LLMResponse,
    EmbeddingResponse,
    LLMHealth,
)
from .runtime.runtime import LLMRuntime, get_runtime, reset_runtime
from .runtime.chat_profile import ChatProfile, resolve_chat_profile
from .runtime.chat_catalog import (
    CONFIGURED_CHAT_MODEL_ENV,
    ChatModelDescriptor,
    configured_chat_model_id,
    list_chat_models,
)
from .runtime.openrouter_catalog import ModelPricing

__all__ = [
    # Ports (protocols)
    "LLMProvider",
    "EmbeddingProvider",
    # Data classes
    "LLMMessage",
    "LLMResponse",
    "EmbeddingResponse",
    "LLMHealth",
    "ChatProfile",
    "ChatModelDescriptor",
    "ModelPricing",
    "CONFIGURED_CHAT_MODEL_ENV",
    "configured_chat_model_id",
    "resolve_chat_profile",
    "list_chat_models",
    # Runtime
    "LLMRuntime",
    "get_runtime",
    "reset_runtime",
]
