"""Authoring helpers - re-exports from authoring/ subpackage for backwards compatibility."""

from .authoring.manager import AuthoringManager
from .authoring.paths import AuthoringPaths
from .authoring.validation import (
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
