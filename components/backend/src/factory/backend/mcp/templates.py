"""Prompt templates for backend module."""

ADAPTER_CONFIG_TEMPLATE = """
# Adapter Configuration: {adapter_name}

## Details
Name: {adapter_name}
Type: {adapter_type}
Backend: {backend}
Connection: {connection_string}

## Status
Enabled: {enabled}
Health: {health_status}
"""

CACHE_OPERATION_TEMPLATE = """
# Cache Operation

## Request
Adapter: {adapter_name}
Operation: {operation}
Key: {key}

## Result
{result}
"""

GRAPH_OPERATION_TEMPLATE = """
# Graph Operation

## Request
Adapter: {adapter_name}
Operation: {operation}

## Details
{details}

## Result
{result}
"""

HEALTH_REPORT_TEMPLATE = """
# Backend Health Report

## Overall Status: {overall_status}

## Adapters
{adapter_statuses}

## Recommendations
{recommendations}
"""

TEMPLATES = {
    "adapter-config": ADAPTER_CONFIG_TEMPLATE,
    "cache-operation": CACHE_OPERATION_TEMPLATE,
    "graph-operation": GRAPH_OPERATION_TEMPLATE,
    "health-report": HEALTH_REPORT_TEMPLATE,
}


def get_template(name: str) -> str | None:
    """Get template by name."""
    return TEMPLATES.get(name)


def list_templates() -> list[str]:
    """List available templates."""
    return list(TEMPLATES.keys())


def render_template(name: str, **kwargs: str) -> str | None:
    """Render a template with provided values."""
    template = TEMPLATES.get(name)
    if template is None:
        return None
    try:
        return template.format(**kwargs)
    except KeyError:
        return template
