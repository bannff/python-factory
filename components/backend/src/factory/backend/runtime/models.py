from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class Node(BaseModel):
    """Represents a node in the graph."""
    id: str
    label: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class Edge(BaseModel):
    """Represents an edge in the graph."""
    id: str
    from_id: str
    to_id: str
    relationship_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)

class Document(BaseModel):
    """Represents a document in the document store."""
    id: str
    collection: str
    data: Dict[str, Any]
    rev: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class SearchResult(BaseModel):
  """Generic container for search results"""
  items: List[Any]
  total: int
  page: int
  page_size: int
