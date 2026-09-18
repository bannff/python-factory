"""Backend runtime — composes cache, graph, and storage bricks.

Instead of maintaining parallel adapter implementations, the backend
runtime delegates to the specialised brick runtimes via their public
interfaces (``factory.<brick>.interface``).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .adapter_ops import AdapterOperations
from .registry import AdapterConfig, AdapterType, get_registry


class BackendRuntime:
    """Runtime that composes cache, graph, and storage bricks."""

    def __init__(self, config_dir: str = "./config") -> None:
        self._config_dir = Path(config_dir)
        self._cache_adapters: dict[str, Any] = {}
        self._graph_adapters: dict[str, Any] = {}
        self._document_adapters: dict[str, Any] = {}
        self._ops: AdapterOperations | None = None
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return
        settings_path = self._config_dir / "settings.yaml"
        settings = {}
        if settings_path.exists():
            with open(settings_path) as f:
                settings = yaml.safe_load(f) or {}
        self._register_defaults(settings)
        self._ops = AdapterOperations(
            self._cache_adapters, self._graph_adapters, self._document_adapters,
        )
        self._initialized = True

    # ---- internal setup ----

    def _register_defaults(self, settings: dict[str, Any]) -> None:
        registry = get_registry()
        for name, atype, cfg_key, factory in [
            ("default-cache", AdapterType.CACHE, "cache", self._make_cache),
            ("default-graph", AdapterType.GRAPH, "graph", self._make_graph),
            ("default-document", AdapterType.DOCUMENT, "document", self._make_doc),
        ]:
            cfg = settings.get(cfg_key, {})
            backend = cfg.get("backend", self._default_backend(atype))
            registry.register(AdapterConfig(
                name=name, adapter_type=atype, backend=backend,
                connection_string=cfg.get("connection_string"),
                options=cfg.get("options", {}),
            ))
            store = {
                "default-cache": self._cache_adapters,
                "default-graph": self._graph_adapters,
                "default-document": self._document_adapters,
            }
            store[name][name] = factory(backend, cfg)

    @staticmethod
    def _default_backend(atype: AdapterType) -> str:
        return {"cache": "memory", "graph": "networkx", "document": "tinydb"}[atype.value]

    def _make_cache(self, backend: str, cfg: dict[str, Any]) -> Any:
        from factory.cache.runtime.runtime import CacheRuntime
        return CacheRuntime(cfg).get_cache(backend)

    def _make_graph(self, backend: str, cfg: dict[str, Any]) -> Any:
        from factory.graph.runtime.runtime import GraphRuntime
        return GraphRuntime(cfg).get_graph(backend)

    def _make_doc(self, backend: str, cfg: dict[str, Any]) -> Any:
        from factory.storage.runtime.runtime import StorageRuntime
        db_path = cfg.get(
            "connection_string", str(self._config_dir / "data" / "db.json"),
        )
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        return StorageRuntime(cfg).get_document_store(backend, db_path=db_path)

    # ---- delegated operations (thin pass-throughs to AdapterOperations) ----

    def cache_get(self, key: str, adapter_name: str = "default-cache") -> Any:
        return self._ops.cache_get(key, adapter_name)

    def cache_set(self, key: str, value: Any, ttl_seconds: int | None = None,
                  adapter_name: str = "default-cache") -> None:
        self._ops.cache_set(key, value, ttl_seconds, adapter_name)

    def cache_delete(self, key: str, adapter_name: str = "default-cache") -> None:
        self._ops.cache_delete(key, adapter_name)

    def graph_add_node(self, node_id: str, properties: dict[str, Any],
                       adapter_name: str = "default-graph") -> None:
        self._ops.graph_add_node(node_id, properties, adapter_name)

    def graph_add_edge(self, source_id: str, target_id: str, edge_type: str,
                       properties: dict[str, Any],
                       adapter_name: str = "default-graph") -> None:
        self._ops.graph_add_edge(source_id, target_id, edge_type, properties, adapter_name)

    def graph_query(self, query: str, params: dict[str, Any],
                    adapter_name: str = "default-graph") -> list[dict[str, Any]]:
        return self._ops.graph_query(query, params, adapter_name)

    def document_insert(self, collection: str, document: dict[str, Any],
                        adapter_name: str = "default-document") -> str:
        return self._ops.document_insert(collection, document, adapter_name)

    def document_find(self, collection: str, query: dict[str, Any], limit: int = 100,
                      adapter_name: str = "default-document") -> list[dict[str, Any]]:
        return self._ops.document_find(collection, query, limit, adapter_name)

    def document_delete(self, collection: str, doc_id: str,
                        adapter_name: str = "default-document") -> None:
        self._ops.document_delete(collection, doc_id, adapter_name)


# Global runtime instance
_runtime: BackendRuntime | None = None


def get_runtime() -> BackendRuntime:
    global _runtime
    if _runtime is None:
        config_dir = os.environ.get("BACKEND_CONFIG_DIR", "./config")
        _runtime = BackendRuntime(config_dir=config_dir)
        _runtime.initialize()
    return _runtime


def reset_runtime() -> None:
    global _runtime
    _runtime = None
