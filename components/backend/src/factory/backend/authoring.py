"""Security-gated authoring tools for backend adapters."""

from __future__ import annotations

import functools
import os
from typing import Any, Callable, TypeVar

from pydantic import ValidationError

from .runtime.registry import AdapterConfig, AdapterType, get_registry

T = TypeVar("T")

ENV_VAR = "BACKEND_ENABLE_AUTHORING_TOOLS"


def is_authoring_enabled() -> bool:
    """Check if authoring tools are enabled."""
    value = os.environ.get(ENV_VAR, "").lower()
    return value in ("1", "true", "yes")


def require_authoring_enabled(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to require authoring tools to be enabled."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        if not is_authoring_enabled():
            raise PermissionError(
                f"Authoring tools are disabled. Set {ENV_VAR}=1 to enable."
            )
        return func(*args, **kwargs)
    return wrapper


class AuthoringTools:
    """Security-gated authoring tools for backend adapters."""

    def get_status(self) -> dict[str, Any]:
        """Get authoring tools status."""
        return {
            "enabled": is_authoring_enabled(),
            "env_var": ENV_VAR,
            "registry_adapters": len(get_registry().list_adapters()),
        }

    @require_authoring_enabled
    def register_adapter(self, config: AdapterConfig) -> dict[str, Any]:
        """Register a new adapter."""
        registry = get_registry()
        registry.register(config)
        return {
            "ok": True,
            "name": config.name,
            "type": config.adapter_type.value,
            "backend": config.backend,
        }

    @require_authoring_enabled
    def unregister_adapter(self, name: str) -> dict[str, Any]:
        """Unregister an adapter."""
        registry = get_registry()
        if registry.get(name) is None:
            return {"ok": False, "error": f"Adapter '{name}' not found"}
        registry.unregister(name)
        return {"ok": True, "name": name}

    @require_authoring_enabled
    def update_adapter_config(
        self,
        name: str,
        enabled: bool | None = None,
        connection_string: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update adapter configuration."""
        registry = get_registry()
        config = registry.get(name)
        if config is None:
            return {"ok": False, "error": f"Adapter '{name}' not found"}
        
        # Create updated config
        updates: dict[str, Any] = {}
        if enabled is not None:
            updates["enabled"] = enabled
        if connection_string is not None:
            updates["connection_string"] = connection_string
        if options is not None:
            updates["options"] = {**config.options, **options}
        
        # Re-register with updates
        new_config = config.model_copy(update=updates)
        registry.unregister(name)
        registry.register(new_config)
        
        return {"ok": True, "name": name, "updates": updates}

    def validate_config(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate adapter configuration without registering."""
        try:
            # Convert string adapter_type to enum
            if "adapter_type" in data and isinstance(data["adapter_type"], str):
                data["adapter_type"] = AdapterType(data["adapter_type"])
            
            config = AdapterConfig(**data)
            return {
                "valid": True,
                "config": config.model_dump(),
            }
        except (ValidationError, ValueError) as e:
            return {
                "valid": False,
                "errors": str(e),
            }


# Global instance
_authoring_tools: AuthoringTools | None = None


def get_authoring_tools() -> AuthoringTools:
    """Get the global authoring tools instance."""
    global _authoring_tools
    if _authoring_tools is None:
        _authoring_tools = AuthoringTools()
    return _authoring_tools
