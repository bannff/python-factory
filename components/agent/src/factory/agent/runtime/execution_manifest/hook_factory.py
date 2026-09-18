"""Closed reconstruction of manifest-bound HookProviders."""
from __future__ import annotations

from typing import Any

from .behavior_registry import verify_hook
from .descriptors import HookDescriptor


def build_hook(descriptor: HookDescriptor) -> Any:
    verify_hook(descriptor)
    config = descriptor.config
    if descriptor.kind == "graph-lifecycle":
        from factory.agent.plugins.multiagent_lifecycle import GraphLifecyclePlugin
        return GraphLifecyclePlugin(
            graph_id=str(config["graph_id"]), run_id=str(config["run_id"]),
        )
    if descriptor.kind == "swarm-lifecycle":
        from factory.agent.plugins.multiagent_lifecycle import SwarmLifecyclePlugin
        return SwarmLifecyclePlugin(
            swarm_id=str(config["swarm_id"]), run_id=str(config["run_id"]),
        )
    if descriptor.kind == "no-revisit":
        from .no_revisit import NoRevisitHook
        return NoRevisitHook()
    raise ValueError(f"unsupported manifest hook: {descriptor.kind!r}")


__all__ = ["build_hook"]
