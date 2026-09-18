"""MCP primitives for backend module.

This package contains:
- deterministic.py: Read-only query tools (contract tools)
- operational.py: Stateful backend operations (cache, graph, document)
- authoring.py: Security-gated configuration tools
- resources.py: Static/queryable data (schemas, docs, stats)
- prompts.py: Guided workflows for common tasks
- docs.py: Documentation content
- templates.py: Prompt templates
"""

from . import deterministic, operational, authoring, resources, prompts, docs, templates

__all__ = [
    "deterministic",
    "operational",
    "authoring",
    "resources",
    "prompts",
    "docs",
    "templates",
]
