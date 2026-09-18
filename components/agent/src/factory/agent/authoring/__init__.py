"""Authoring helpers for safely modifying a Super Agent project via MCP."""

from .manager import AuthoringManager
from .paths import AuthoringPaths
from .validation import (
    authoring_enabled,
    validate_config,
    validate_tool_module,
    AuthoringError,
    ConfigKind,
)

__all__ = [
    "AuthoringManager",
    "AuthoringPaths",
    "authoring_enabled",
    "validate_config",
    "validate_tool_module",
    "AuthoringError",
    "ConfigKind",
]
