"""Build the adapter config + metadata for a provision call.

Resolves an optional profile into concrete Docker settings, bakes default
OTEL env into every container, and collects any profile setup commands.
Extracted from ``SandboxRuntime.provision`` so the runtime method stays a thin
orchestrator over these cohesive config-building steps.
"""
from __future__ import annotations

from typing import Any

from .models import SandboxConfig


def build_provision_context(
    cfg: SandboxConfig, profile: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Return ``(adapter_config, metadata, setup_commands)`` for ``cfg``.

    Mutates ``cfg.instance_type`` to ``"docker"`` when a profile is resolved,
    preserving the original in-place behavior the caller relies on.
    """
    adapter_config = cfg.model_dump()
    metadata: dict[str, Any] = {
        "timeout_seconds": cfg.timeout_seconds,
        "auto_terminate": cfg.auto_terminate,
    }
    setup_commands: list[str] = []
    if profile:
        from .profiles import resolve_profile
        p = resolve_profile(profile)
        adapter_config.update({
            "image": p.image, "ports": p.ports,
            "entrypoint": p.entrypoint, "container_name": p.container_name,
            "env_vars": p.env_vars,
        })
        cfg.instance_type = "docker"
        setup_commands = list(p.setup_commands)
        metadata.update({
            "profile": p.name,
            "image": p.image,
            "ports": p.ports,
            "health_check_url": p.health_check_url,
            "container_name": p.container_name,
            "shell": p.shell,
        })
    elif cfg.ami_id:
        metadata["ami_id"] = cfg.ami_id

    # Bake default OTEL into every container so anything running inside
    # (builds, tests, a deployed agent squad) exports back to the parent
    # collector. Explicit profile env wins over the defaults.
    from .observability import default_otel_env
    otel_env = default_otel_env(
        adapter_config.get("container_name", "sandbox"),
        metadata.get("profile"),
    )
    if otel_env:
        existing_env = dict(adapter_config.get("env_vars", {}) or {})
        adapter_config["env_vars"] = {**otel_env, **existing_env}
        metadata["otel_enabled"] = True
    return adapter_config, metadata, setup_commands
