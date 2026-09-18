"""Documentation for backend module."""

BACKEND_OVERVIEW = """
# Backend Brick

The backend brick provides pluggable storage adapters for the Python Factory.

## Supported Backends

### Cache Adapters
- **Memory**: In-memory cache for development/testing
- **Redis**: Production-ready distributed cache

### Graph Adapters
- **NetworkX**: In-memory graph for development
- **Neo4j**: Production graph database

### Document Adapters
- **TinyDB**: Lightweight JSON document store

## Architecture

```
backend/
├── runtime/
│   ├── runtime.py      # Core backend runtime
│   ├── registry.py     # Adapter registry
│   ├── health.py       # Health checking
│   ├── adapters/       # Backend implementations
│   │   ├── cache/      # Cache adapters
│   │   ├── graph/      # Graph adapters
│   │   └── document/   # Document adapters
└── mcp/
    └── tools.py        # MCP tool definitions
```

## Key Concepts

### Adapters
Adapters provide a unified interface to different storage backends.
Each adapter type (cache, graph, document) has multiple implementations.

### Registry
The adapter registry tracks all configured adapters and their health status.

### Runtime
The runtime manages adapter lifecycle and provides the operational interface.
"""

CACHE_GUIDE = """
# Cache Adapter Guide

## Memory Cache

Best for development and testing. Data is lost on restart.

```python
# Configuration
config = AdapterConfig(
    name="dev-cache",
    adapter_type="cache",
    backend="memory",
    enabled=True
)
```

## Redis Cache

Production-ready distributed cache with TTL support.

```python
# Configuration
config = AdapterConfig(
    name="prod-cache",
    adapter_type="cache",
    backend="redis",
    connection_string="redis://localhost:6379/0",
    options={"max_connections": 10}
)
```

## Operations

- `cache_get(key)` - Retrieve value by key
- `cache_set(key, value, ttl)` - Store value with optional TTL
- `cache_delete(key)` - Remove value
"""

GRAPH_GUIDE = """
# Graph Adapter Guide

## NetworkX (In-Memory)

Best for development and small graphs.

```python
config = AdapterConfig(
    name="dev-graph",
    adapter_type="graph",
    backend="networkx",
    enabled=True
)
```

## Neo4j

Production graph database for large-scale graph operations.

```python
config = AdapterConfig(
    name="prod-graph",
    adapter_type="graph",
    backend="neo4j",
    connection_string="bolt://localhost:7687",
    options={"auth": ("neo4j", "password")}
)
```

## Operations

- `graph_add_node(id, properties)` - Add node
- `graph_add_edge(from, to, properties)` - Add edge
- `graph_query(cypher)` - Execute query
"""

DOCUMENT_GUIDE = """
# Document Adapter Guide

## TinyDB

Lightweight JSON document store for simple use cases.

```python
config = AdapterConfig(
    name="docs",
    adapter_type="document",
    backend="tinydb",
    options={"path": "./data/docs.json"}
)
```

## Operations

- `document_insert(collection, doc)` - Insert document
- `document_find(collection, query)` - Query documents
- `document_update(collection, id, updates)` - Update document
"""

DOCS = {
    "overview": BACKEND_OVERVIEW,
    "cache": CACHE_GUIDE,
    "graph": GRAPH_GUIDE,
    "document": DOCUMENT_GUIDE,
}


def get_doc(name: str) -> str | None:
    """Get documentation by name."""
    return DOCS.get(name)


def list_docs() -> list[str]:
    """List available documentation."""
    return list(DOCS.keys())
