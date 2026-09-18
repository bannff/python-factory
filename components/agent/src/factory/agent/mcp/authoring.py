"""Strict typed authoring MCP tools for SuperAgent."""
from __future__ import annotations

from typing import Any, TYPE_CHECKING, cast

from factory.mcp_utils.interface import ToolResult, authoring, ok

from ..authoring import AuthoringError, AuthoringManager, ConfigKind
from .contracts.authoring import (
    AgentCreateInput, AgentDeleteInput, AgentForkInput, AuthoringResult, AuthoringStatusOutput,
    ConfigItemInput, ConfigWriteInput, KindInput, ModuleInput, ModuleWriteInput,
    SettingsWriteInput, SquadCreateInput, SquadDeleteInput,
)
from .contracts.discovery import EmptyInput

if TYPE_CHECKING:
    from ..agent import SuperAgent


def _result(value: dict[str, Any]) -> ToolResult[AuthoringResult]:
    """Keep existing authoring payloads opaque under one concrete DTO."""
    return ok(AuthoringResult(success=bool(value.get("ok", True)), result=value))


def register(mcp: Any, agent: "SuperAgent") -> None:
    """Register gated configuration authoring tools."""
    manager = AuthoringManager(agent.config_dir)

    @mcp.tool()
    @authoring(input_model=EmptyInput, output_model=AuthoringStatusOutput)
    def authoring_status() -> ToolResult[AuthoringStatusOutput]:
        return ok(AuthoringStatusOutput(enabled=True, config_root=str(agent.config_dir)))

    @mcp.tool()
    @authoring(input_model=KindInput, output_model=AuthoringResult)
    def list_config_items(kind: str) -> ToolResult[AuthoringResult]:
        return _result({"ok": True, "items": manager.list_items(cast(ConfigKind, kind))})

    @mcp.tool()
    @authoring(input_model=ConfigItemInput, output_model=AuthoringResult)
    def read_config(kind: str, item_id: str) -> ToolResult[AuthoringResult]:
        return _result({"ok": True, "config": manager.read_yaml_config(cast(ConfigKind, kind), item_id)})

    @mcp.tool()
    @authoring(input_model=ConfigWriteInput, output_model=AuthoringResult)
    def write_config(kind: str, config: dict[str, Any]) -> ToolResult[AuthoringResult]:
        return _result(manager.write_yaml_config(cast(ConfigKind, kind), config))

    @mcp.tool()
    @authoring(input_model=ConfigItemInput, output_model=AuthoringResult)
    def delete_config(kind: str, item_id: str) -> ToolResult[AuthoringResult]:
        return _result(manager.delete_yaml_config(cast(ConfigKind, kind), item_id))

    @mcp.tool()
    @authoring(input_model=EmptyInput, output_model=AuthoringResult)
    def read_settings() -> ToolResult[AuthoringResult]:
        return _result({"ok": True, "settings": manager.read_settings()})

    @mcp.tool()
    @authoring(input_model=SettingsWriteInput, output_model=AuthoringResult)
    def write_settings(settings: dict[str, Any]) -> ToolResult[AuthoringResult]:
        return _result(manager.write_settings(settings))

    @mcp.tool()
    @authoring(input_model=ModuleInput, output_model=AuthoringResult)
    def read_tool_module(module_name: str) -> ToolResult[AuthoringResult]:
        return _result(manager.read_tool_module(module_name))

    @mcp.tool()
    @authoring(input_model=ModuleWriteInput, output_model=AuthoringResult)
    def write_tool_module(module_name: str, code: str) -> ToolResult[AuthoringResult]:
        return _result(manager.write_tool_module(module_name, code))

    @mcp.tool()
    @authoring(input_model=ModuleInput, output_model=AuthoringResult)
    def delete_tool_module(module_name: str) -> ToolResult[AuthoringResult]:
        return _result(manager.delete_tool_module(module_name))

    @mcp.tool()
    @authoring(input_model=EmptyInput, output_model=AuthoringResult)
    async def reload_config() -> ToolResult[AuthoringResult]:
        await agent.agent_registry.load()
        await agent.swarm_registry.load()
        await agent.graph_registry.load()
        await agent.tool_registry.load()
        if agent.squad_registry is not None:
            await agent.squad_registry.load()
        return _result({"ok": True, "agents": len(agent.agent_registry.agents)})

    @mcp.tool()
    @authoring(input_model=AgentCreateInput, output_model=AuthoringResult)
    async def agent_create_agent(config: dict[str, Any]) -> ToolResult[AuthoringResult]:
        from ..registry.defaults import AGENTS_TYPED
        requested_id = str(config.get("id", ""))
        if requested_id in {entry.id for entry in AGENTS_TYPED}:
            return _result({"ok": False, "error": "id_collides_with_builtin", "details": f"'{requested_id}' is a built-in persona id; choose a different id."})
        try:
            result = manager.write_yaml_config("agent", config)
        except AuthoringError as error:
            return _result({"ok": False, "error": "invalid_config", "details": str(error)})
        await agent.agent_registry.load()
        return _result({"ok": True, "id": result["id"], "path": result["path"]})

    @mcp.tool()
    @authoring(input_model=AgentDeleteInput, output_model=AuthoringResult)
    async def agent_delete_agent(agent_id: str) -> ToolResult[AuthoringResult]:
        from ..registry.defaults import AGENTS_TYPED
        if agent_id in {entry.id for entry in AGENTS_TYPED}:
            return _result({"ok": False, "error": "cannot_delete_builtin", "id": agent_id})
        removed = manager.delete_yaml_config("agent", agent_id).get("ok", False)
        await agent.agent_registry.load()
        return _result({"ok": bool(removed), "error": None if removed else "not_found", "id": agent_id})

    @mcp.tool()
    @authoring(input_model=AgentForkInput, output_model=AuthoringResult)
    async def agent_fork_agent(source_agent_id: str, new_agent_id: str) -> ToolResult[AuthoringResult]:
        """Copy any persona (built-in or user) to a new id the owner can
        freely edit. Built-ins always win an id collision (registry
        invariant), so a fork is always a distinct id, never an override —
        row 33 (feature-map): "the definition panel forks a private
        template copy on first edit"."""
        source = agent.agent_registry.get(source_agent_id)
        if source is None:
            return _result({"ok": False, "error": "source_not_found", "id": source_agent_id})
        from ..registry.defaults import AGENTS_TYPED
        if new_agent_id in {entry.id for entry in AGENTS_TYPED}:
            return _result({"ok": False, "error": "id_collides_with_builtin",
                            "details": f"'{new_agent_id}' is a built-in persona id; choose a different id."})
        config = {**source.model_dump(), "id": new_agent_id}
        try:
            result = manager.write_yaml_config("agent", config)
        except AuthoringError as error:
            return _result({"ok": False, "error": "invalid_config", "details": str(error)})
        manager.write_fork_provenance("agent", new_agent_id, source_agent_id)
        await agent.agent_registry.load()
        return _result({"ok": True, "id": result["id"], "path": result["path"], "forked_from": source_agent_id})

    @mcp.tool()
    @authoring(input_model=AgentDeleteInput, output_model=AuthoringResult)
    async def agent_reset_agent(agent_id: str) -> ToolResult[AuthoringResult]:
        """Discard a fork's local edits, restoring it to its source
        persona's CURRENT definition (built-ins may themselves change
        between releases; reset always re-copies from the live source,
        never a frozen snapshot). Only valid for a persona this tool
        itself forked — a plain user-authored persona with no recorded
        provenance has nothing to reset to."""
        source_id = manager.read_fork_provenance("agent", agent_id)
        if source_id is None:
            return _result({"ok": False, "error": "not_a_fork", "id": agent_id})
        source = agent.agent_registry.get(source_id)
        if source is None:
            return _result({"ok": False, "error": "source_not_found", "id": source_id})
        config = {**source.model_dump(), "id": agent_id}
        try:
            manager.write_yaml_config("agent", config)
        except AuthoringError as error:
            return _result({"ok": False, "error": "invalid_config", "details": str(error)})
        manager.write_fork_provenance("agent", agent_id, source_id)
        await agent.agent_registry.load()
        return _result({"ok": True, "id": agent_id, "reset_from": source_id})

    @mcp.tool()
    @authoring(input_model=SquadCreateInput, output_model=AuthoringResult)
    async def agent_create_squad(config: dict[str, Any]) -> ToolResult[AuthoringResult]:
        """Create or update a deployable squad (team-of-agents) as DATA."""
        from ..registry.defaults_squads import SQUADS_TYPED
        requested_id = str(config.get("id", ""))
        if requested_id in {entry.id for entry in SQUADS_TYPED}:
            return _result({"ok": False, "error": "id_collides_with_builtin",
                            "details": f"'{requested_id}' is a built-in squad id; choose another."})
        try:
            result = manager.write_yaml_config("squad", config)
        except AuthoringError as error:
            return _result({"ok": False, "error": "invalid_config", "details": str(error)})
        if agent.squad_registry is not None:
            await agent.squad_registry.load()
        return _result({"ok": True, "id": result["id"], "path": result["path"]})

    @mcp.tool()
    @authoring(input_model=SquadDeleteInput, output_model=AuthoringResult)
    async def agent_delete_squad(squad_id: str) -> ToolResult[AuthoringResult]:
        """Delete a user-authored squad; built-in squads cannot be deleted."""
        from ..registry.defaults_squads import SQUADS_TYPED
        if squad_id in {entry.id for entry in SQUADS_TYPED}:
            return _result({"ok": False, "error": "cannot_delete_builtin", "id": squad_id})
        removed = manager.delete_yaml_config("squad", squad_id).get("ok", False)
        if agent.squad_registry is not None:
            await agent.squad_registry.load()
        return _result({"ok": bool(removed), "error": None if removed else "not_found", "id": squad_id})
