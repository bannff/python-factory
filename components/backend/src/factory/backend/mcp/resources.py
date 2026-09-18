"""MCP resources for backend module."""

from __future__ import annotations

from typing import Any

from .docs import DOCS, get_doc, list_docs
from .templates import TEMPLATES, get_template, list_templates
from ..runtime.registry import get_registry, AdapterConfig


def register(mcp: Any) -> None:
    """Register backend resources."""

    @mcp.resource("backend://docs")
    def backend_docs_list() -> str:
        """List available backend documentation."""
        docs = list_docs()
        lines = ["# Backend Documentation", ""]
        for doc in docs:
            lines.append(f"- backend://docs/{doc}")
        return "\n".join(lines)

    @mcp.resource("backend://docs/{name}")
    def backend_doc(name: str) -> str:
        """Get specific backend documentation."""
        doc = get_doc(name)
        if doc is None:
            return f"Documentation '{name}' not found. Available: {list_docs()}"
        return doc

    @mcp.resource("backend://templates")
    def backend_templates_list() -> str:
        """List available prompt templates."""
        templates = list_templates()
        lines = ["# Backend Templates", ""]
        for t in templates:
            lines.append(f"- backend://templates/{t}")
        return "\n".join(lines)

    @mcp.resource("backend://templates/{name}")
    def backend_template(name: str) -> str:
        """Get specific prompt template."""
        template = get_template(name)
        if template is None:
            return f"Template '{name}' not found. Available: {list_templates()}"
        return template

    @mcp.resource("backend://schema/adapter-config")
    def backend_adapter_schema() -> str:
        """Get JSON schema for adapter configuration."""
        import json
        return json.dumps(AdapterConfig.model_json_schema(), indent=2)

    @mcp.resource("backend://adapters")
    def backend_adapters() -> str:
        """Get current adapter registry status."""
        registry = get_registry()
        adapters = registry.list_adapters()
        
        lines = ["# Backend Adapters", ""]
        if not adapters:
            lines.append("No adapters registered.")
            return "\n".join(lines)
        
        for name in adapters:
            config = registry.get_adapter(name)
            if config:
                status = "✓ enabled" if config.enabled else "✗ disabled"
                lines.append(f"- {name} ({config.adapter_type.value}/{config.backend}): {status}")
        
        return "\n".join(lines)

    @mcp.resource("backend://adapters/{name}")
    def backend_adapter_detail(name: str) -> str:
        """Get details for a specific adapter."""
        registry = get_registry()
        config = registry.get_adapter(name)
        
        if config is None:
            return f"Adapter '{name}' not found."
        
        lines = [
            f"# Adapter: {name}",
            "",
            f"Type: {config.adapter_type.value}",
            f"Backend: {config.backend}",
            f"Enabled: {config.enabled}",
        ]
        
        if config.connection_string:
            lines.append(f"Connection: {config.connection_string}")
        
        if config.options:
            lines.append(f"Options: {config.options}")
        
        stats = registry.get_stats(name)
        if stats:
            lines.extend([
                "",
                "## Statistics",
                f"Operations: {stats.operation_count}",
                f"Errors: {stats.error_count}",
            ])
        
        return "\n".join(lines)

    @mcp.resource("backend://factory-cross-ref")
    def backend_factory_cross_ref() -> str:
        """Cross-reference with other factory bricks."""
        return """# Backend Factory Integration

## Related Bricks

### kb (Knowledge Base)
- Uses document adapters for vector storage metadata
- Graph adapters for knowledge graph relationships

### workflow
- Cache adapters for workflow state
- Document adapters for workflow definitions

### events
- Cache for event deduplication
- Document store for event history

### telemetry
- Cache for metric aggregation buffers
- Graph for service dependency mapping

## Integration Patterns

1. **Unified Storage**: Use backend adapters as the storage layer for other bricks
2. **Health Aggregation**: Backend health feeds into overall system health
3. **Configuration**: Centralized adapter configuration via authoring tools
"""
