"""Strands-backed AI assistant — isolated behind the AssistantLoop protocol.

This module is ONLY imported when strands-agents is installed AND a model is
configured. The guarded import in assistant.resolve_assistant() ensures the lean
app never touches this file.

Architecture:
  - Connects to OpenArcade's own MCP server via MCPClient + stdio transport.
  - All tools auto-load from the single server.py source of truth.
  - Provider→builder map: polymorphism over conditionals.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncIterator, Callable

from strands import Agent
from strands.memory import MemoryManager
from mcp import StdioServerParameters, stdio_client
from strands.tools.mcp import MCPClient

from .assistant import AssistantConfig, AssistantLoop
from .memory_store import LocalJsonMemoryStore
from .model_catalog import resolve_boto_session

_SYSTEM_PROMPT = """\
You are the OpenArcade assistant — a friendly retro-gaming concierge.

You help the user browse their game library, launch games, tweak settings,
remap controllers, manage cores, and troubleshoot — all through the MCP tools
available to you.

You can also remember user preferences (favorite genres, games, settings) and
personal notes across sessions using your memory tools. Proactively offer to
remember things the user mentions caring about.

Rules:
- ALWAYS use a tool to answer factual questions (game list, settings values,
  system info). Never guess or hallucinate game data.
- You operate on the MANAGEMENT PLANE only. You are NEVER in the gameplay hot
  loop — launching a game hands off to RetroArch; you do not control gameplay.
- Be concise, helpful, and enthusiastic about retro games.
- If a tool errors or a capability isn't available, say so honestly.

Grounding (MANDATORY):
- You MUST NOT invent, guess, or list game titles from your own training data.
- The user's library is ONLY what the list_games and library_summary tools
  return. These show curated, launchable games (cover art present + ROM resolved).
- ALWAYS call list_games or library_summary before answering questions about
  what games, systems, or counts are in the library. Never rely on memory of a
  previous call — the library may have changed.
- If the user asks about a game not in list_games results, say it is not in
  their curated library (it may exist uncurated, but is not playable from the wall).

Knowledge grounding (emulator/core/ROM/how-to questions):
- For questions about which core to use, ROM naming conventions, how to fix
  launch issues, or emulator configuration, ALWAYS call knowledge_search first
  and ground your answer in the returned documents.
- Do NOT invent emulator facts, core names, or troubleshooting steps from
  training data — use what knowledge_search returns.
- If knowledge_search returns empty for a topic, say you don't have that info
  in the knowledge base rather than guessing.
"""


# ---------------------------------------------------------------------------
# Provider → model builder map (polymorphism over conditionals)
# ---------------------------------------------------------------------------


def _build_bedrock(model_id: str, api_key: str | None):  # noqa: ANN201
    """Build a BedrockModel using whatever AWS creds are active (any profile)."""
    from strands.models.bedrock import BedrockModel

    session = resolve_boto_session()
    if session is not None:
        # BedrockModel rejects region_name + boto_session together; the session
        # must carry the region. Rebuild with a region if the profile lacks one.
        if not session.region_name:
            import boto3

            session = boto3.Session(
                profile_name=session.profile_name,
                region_name=os.environ.get("AWS_REGION") or "us-east-1",
            )
        return BedrockModel(model_id=model_id, boto_session=session)
    region = os.environ.get("AWS_REGION") or "us-east-1"
    return BedrockModel(model_id=model_id, region_name=region)


def _build_openai(model_id: str, api_key: str | None):  # noqa: ANN201
    """Build an OpenAIModel with API key."""
    from strands.models.openai import OpenAIModel

    return OpenAIModel(client_args={"api_key": api_key}, model_id=model_id)


def _build_anthropic(model_id: str, api_key: str | None):  # noqa: ANN201
    """Build an AnthropicModel with API key."""
    from strands.models.anthropic import AnthropicModel

    return AnthropicModel(
        client_args={"api_key": api_key}, model_id=model_id, max_tokens=1024
    )


def _build_gemini(model_id: str, api_key: str | None):  # noqa: ANN201
    """Build a GeminiModel with API key."""
    from strands.models.gemini import GeminiModel

    return GeminiModel(client_args={"api_key": api_key}, model_id=model_id)


def _build_ollama(model_id: str, api_key: str | None):  # noqa: ANN201
    """Build an OllamaModel (local, no key needed)."""
    from strands.models.ollama import OllamaModel

    host = os.environ.get("OPENARCADE_OLLAMA_HOST", "http://localhost:11434")
    return OllamaModel(host=host, model_id=model_id)


def _build_litellm(model_id: str, api_key: str | None):  # noqa: ANN201
    """Build a LiteLLMModel with API key."""
    from strands.models.litellm import LiteLLMModel

    return LiteLLMModel(client_args={"api_key": api_key}, model_id=model_id)


# Map provider name → builder function
PROVIDER_BUILDERS: dict[str, Callable[[str, str | None], object]] = {
    "bedrock": _build_bedrock,
    "openai": _build_openai,
    "anthropic": _build_anthropic,
    "gemini": _build_gemini,
    "ollama": _build_ollama,
    "litellm": _build_litellm,
}


# ---------------------------------------------------------------------------
# MCP server params
# ---------------------------------------------------------------------------


def _build_mcp_server_params(config: AssistantConfig) -> StdioServerParameters:
    """Build stdio params to launch the OpenArcade MCP server as a subprocess."""
    env = {**os.environ}
    if config.gamelist_path:
        env["OPENARCADE_GAMELIST"] = config.gamelist_path
    if config.media_root:
        env["OPENARCADE_MEDIA_ROOT"] = config.media_root
    env["OPENARCADE_SYSTEM"] = config.system

    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "control_plane.server"],
        env=env,
    )


# ---------------------------------------------------------------------------
# StrandsAssistant
# ---------------------------------------------------------------------------


class StrandsAssistant:
    """Full Strands-backed assistant consuming OpenArcade's MCP tools.

    Satisfies the AssistantLoop protocol.
    """

    def __init__(self, *, config: AssistantConfig) -> None:
        self._config = config
        self._mcp_params = _build_mcp_server_params(config)

    def _build_model(self):  # noqa: ANN201
        """Construct the model from config via the provider→builder map.

        Guarded import: if a provider's strands extra isn't installed, raises
        ImportError with an honest message.
        """
        provider = self._config.provider
        builder = PROVIDER_BUILDERS.get(provider)
        if builder is None:
            raise ValueError(f"Unknown provider: {provider!r}")

        try:
            return builder(self._config.model_id or "", self._config.api_key)
        except ImportError as exc:
            raise ImportError(
                f"Provider '{provider}' not installed — "
                f"pip install strands-agents[{provider}]"
            ) from exc

    async def send(self, message: str) -> AsyncIterator[str]:
        """Send a user message through the Strands agent; yield the response text.

        The whole turn (MCPClient session + agent invocation) is synchronous and
        blocking, so it runs in a worker thread via asyncio.to_thread to keep the
        UI event loop responsive. MCPClient is a SYNC context manager (`with`),
        scoping the MCP subprocess lifecycle to the turn.
        """
        text = await asyncio.to_thread(self._run_turn, message)
        if text:
            yield text

    def _run_turn(self, message: str) -> str:
        """Blocking single-turn agent invocation (runs off the event loop)."""
        mcp_client = MCPClient(lambda: stdio_client(self._mcp_params))
        with mcp_client:
            tools = mcp_client.list_tools_sync()
            memory_store = LocalJsonMemoryStore()
            memory_manager = MemoryManager(
                stores=[memory_store],
                add_tool_config=True,   # Registers add_memory tool
                search_tool_config=True,  # Registers search_memory tool
                injection=True,         # Auto-injects relevant memories before each call
            )
            agent = Agent(
                model=self._build_model(),
                tools=tools,
                system_prompt=_SYSTEM_PROMPT,
                memory_manager=memory_manager,
            )
            return str(agent(message))


# Protocol compliance assertion (static type checkers catch this too)
_: AssistantLoop = StrandsAssistant(config=AssistantConfig(model_id="test"))  # type: ignore[assignment]
