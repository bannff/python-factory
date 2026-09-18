"""Core resolver — re-exports from the launch brick (single source of truth).

This file exists for backwards compatibility with existing wall imports.
The real implementation lives at factory.launch.runtime.core_resolver.
"""

from factory.launch.interface import resolve_core_path, DEFAULT_CORE_STEMS, default_cores_dir

__all__ = ["resolve_core_path", "DEFAULT_CORE_STEMS", "default_cores_dir"]
