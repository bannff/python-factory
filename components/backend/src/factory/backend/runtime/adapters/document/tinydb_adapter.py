"""Backward-compatible TinyDB document adapter.

Delegates to ``factory.storage`` brick's TinyDBDocumentStore.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import DocumentAdapter
from factory.backend.runtime.models import Document


class TinyDBAdapter(DocumentAdapter):
    """TinyDB document adapter — delegates to storage brick."""

    def __init__(self, storage_path: str = "data.json") -> None:
        from factory.storage.runtime.adapters.doc_tinydb import (
            TinyDBDocumentStore,
        )
        self._delegate = TinyDBDocumentStore(db_path=storage_path)

    def connect(self) -> None:
        pass  # TinyDBDocumentStore opens on __init__

    def health_check(self) -> bool:
        h = self._delegate.health_check()
        return h.healthy

    def upsert(
        self, collection: str, document_id: str, data: Dict[str, Any],
    ) -> Document:
        # Try update first, fall back to insert
        existing = self._delegate.get(collection, document_id)
        if existing:
            self._delegate.update(collection, document_id, data)
        else:
            self._delegate.insert(collection, data, doc_id=document_id)
        return Document(id=document_id, collection=collection, data=data)

    def get(
        self, collection: str, document_id: str,
    ) -> Optional[Document]:
        doc = self._delegate.get(collection, document_id)
        if doc is None:
            return None
        return Document(
            id=doc.id, collection=doc.collection, data=doc.data,
        )

    def find(
        self, collection: str, query: Dict[str, Any],
    ) -> List[Document]:
        docs = self._delegate.find(collection, query)
        return [
            Document(id=d.id, collection=d.collection, data=d.data)
            for d in docs
        ]

    def delete(self, collection: str, document_id: str) -> bool:
        return self._delegate.delete(collection, document_id)


class TinyDBDocumentAdapter(TinyDBAdapter):
    """Backward-compatible name used by runtime imports."""

    def __init__(self, db_path: str = "data.json") -> None:
        super().__init__(storage_path=db_path)
