"""Concrete Agent adapters and LangChain/LangGraph production factories."""
from __future__ import annotations

import os
from typing import Any

from factory.mcp_utils.interface import CapabilityScope

from .langchain_chat import LangChainChatAgent
from .langchain_runtime import LangChainAgentRuntime
from .langgraph_runtime import LangGraphRuntime
from .memory import MemoryAgentRuntime, MemoryChatAgent, MemorySwarmRuntime
from .memory_graph import MemoryGraphRuntime, MemoryToolLoader
from .session_agent_mcp import SessionAgentMCP
from ..adapter_registry import (
    RuntimeAdapterFactory, get_runtime_adapter, register_runtime_adapter,
    registered_runtime_adapters,
)

__all__ = [
    "LangChainAgentRuntime", "LangChainChatAgent", "LangGraphRuntime",
    "MemoryAgentRuntime", "MemoryChatAgent", "MemoryGraphRuntime",
    "MemorySwarmRuntime", "MemoryToolLoader", "create_agent_adapter",
    "create_chat_agent", "create_graph_adapter", "create_runtime_pair",
    "create_swarm_adapter", "create_tool_loader",
]


def _scoped_client(
    parent_scope: CapabilityScope | None = None,
    tool_names: set[str] | None = None,
) -> Any:
    """Build an immutable exact surface through mcp_server's public API."""
    from factory.mcp_server.interface import create_exact_flat_native_scope
    from .native_v2_capabilities import create_native_v2_capability_client

    server, scope = create_exact_flat_native_scope(
        tool_names, parent_scope=parent_scope,
    )
    return create_native_v2_capability_client(server, scope)


def _langchain_runtime(
    parent_scope: CapabilityScope | None = None,
    tool_names: set[str] | None = None,
    steering: Any | None = None,
) -> LangChainAgentRuntime:
    from .langchain_model import build_langchain_chat_model

    model_id = os.getenv(
        "COMPANION_X_CHAT_MODEL", "us.anthropic.claude-sonnet-4-6",
    )
    client = (
        _scoped_client() if parent_scope is None and tool_names is None
        else _scoped_client(parent_scope, tool_names)
    )
    checkpoint_path = os.getenv(
        "COMPANION_X_CHECKPOINT_DB_PATH", "./.storage/agent-checkpoints.db",
    )
    from .approval_policy_store import SqliteApprovalPolicyStore
    approval_store = SqliteApprovalPolicyStore(os.getenv(
        "COMPANION_X_APPROVAL_POLICY_DB_PATH", "./.storage/agent-approval.db",
    ))
    return LangChainAgentRuntime(
        build_langchain_chat_model(model_id), client,
        model_id=model_id, model_builder=build_langchain_chat_model,
        checkpoint_path=checkpoint_path,
        steering=steering if steering is not None else SessionAgentMCP(),
        approval_store=approval_store,
    )


def _langchain_chat() -> LangChainChatAgent:
    from .langchain_model import build_langchain_chat_model

    model_id = os.getenv(
        "COMPANION_X_CHAT_MODEL", "us.anthropic.claude-sonnet-4-6",
    )
    session = SessionAgentMCP()
    runtime = _langchain_runtime(steering=session)
    return LangChainChatAgent(
        runtime, build_langchain_chat_model, model_id=model_id,
        session_binding=session,
    )


def _ensure_registry() -> None:
    if "langchain-langgraph" not in registered_runtime_adapters():
        register_runtime_adapter(RuntimeAdapterFactory(
            adapter_id="langchain-langgraph",
            agent=_langchain_runtime,
            chat=_langchain_chat,
            graph=lambda: LangGraphRuntime(_langchain_runtime()),
            coordination=lambda: LangGraphRuntime(_langchain_runtime()),
        ))


def _selected_adapter() -> Any:
    _ensure_registry()
    from ..runtime_selection import load_runtime_selection
    return get_runtime_adapter(load_runtime_selection().runtime_adapter_id)


def create_runtime_pair(
    parent_scope: CapabilityScope | None = None,
    tool_names: set[str] | None = None,
) -> tuple[LangChainAgentRuntime, LangGraphRuntime]:
    """Create a root runtime or one child narrowed from trusted authority."""
    agents = _langchain_runtime(parent_scope, tool_names)
    return agents, LangGraphRuntime(agents)


def create_agent_adapter(adapter_type: str | None = None) -> Any:
    """Create the trusted configured runtime; memory is test-only."""
    if adapter_type == "memory":
        return MemoryAgentRuntime()
    if adapter_type not in (None, "langchain", "langchain-langgraph"):
        raise ValueError("unknown agent runtime adapter")
    return _selected_adapter().agent()


def create_graph_adapter(adapter_type: str | None = None) -> Any:
    """Create bounded graph execution from trusted adapter selection."""
    if adapter_type == "memory":
        return MemoryGraphRuntime()
    if adapter_type not in (None, "langgraph", "langchain-langgraph"):
        raise ValueError("unknown graph runtime adapter")
    return _selected_adapter().graph()


def create_swarm_adapter(adapter_type: str | None = None) -> Any:
    """Create bounded coordination from trusted adapter selection."""
    if adapter_type == "memory":
        return MemorySwarmRuntime()
    if adapter_type not in (None, "langgraph", "langchain-langgraph"):
        raise ValueError("unknown coordination runtime adapter")
    return _selected_adapter().coordination()


def create_tool_loader(adapter_type: str = "memory") -> MemoryToolLoader:
    """Retain only the deterministic test loader; production uses scoped MCP."""
    if adapter_type == "memory":
        return MemoryToolLoader()
    raise ValueError("Production tools are supplied by ScopedCapabilityClientPort")


def create_chat_agent(adapter_type: str | None = None) -> Any:
    """Create chat from trusted adapter selection; memory is test-only."""
    if adapter_type == "memory":
        return MemoryChatAgent()
    if adapter_type not in (None, "langchain", "langchain-langgraph"):
        raise ValueError("unknown chat runtime adapter")
    return _selected_adapter().chat()
