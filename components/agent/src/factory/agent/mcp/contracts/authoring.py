"""Contracts for Agent authoring MCP tools."""
from __future__ import annotations

from typing import Any, Literal

from .discovery import StrictDTO

ConfigKind = Literal["agent", "swarm", "graph"]


class KindInput(StrictDTO):
    kind: ConfigKind


class ConfigItemInput(KindInput):
    item_id: str


class ConfigWriteInput(KindInput):
    config: dict[str, Any]


class SettingsWriteInput(StrictDTO):
    settings: dict[str, Any]


class ModuleInput(StrictDTO):
    module_name: str


class ModuleWriteInput(ModuleInput):
    code: str


class AgentCreateInput(StrictDTO):
    config: dict[str, Any]


class AgentDeleteInput(StrictDTO):
    agent_id: str


class AgentForkInput(StrictDTO):
    source_agent_id: str
    new_agent_id: str


class SquadCreateInput(StrictDTO):
    config: dict[str, Any]


class SquadDeleteInput(StrictDTO):
    squad_id: str


class AuthoringStatusOutput(StrictDTO):
    enabled: bool
    config_root: str


class AuthoringResult(StrictDTO):
    success: bool
    result: dict[str, Any]
