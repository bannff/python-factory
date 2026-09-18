from typing import List, Optional
from pydantic import BaseModel, Field
import uuid

class Envelope(BaseModel):
    """Context envelope for passing auditing and multi-tenancy information."""
    user_id: Optional[str] = None
    tenant_id: Optional[str] = "default"
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    roles: List[str] = Field(default_factory=list)
    
    def is_admin(self) -> bool:
        return "admin" in self.roles
