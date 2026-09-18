from typing import Any, Optional
import json
from .base import CacheAdapter

class RedisAdapter(CacheAdapter):
    """Redis cache adapter implementation."""

    def __init__(self, url: str):
        self.url = url
        self._client = None

    def connect(self) -> None:
        try:
            import redis
            self._client = redis.from_url(self.url, decode_responses=True)
        except ImportError:
            raise ImportError("redis not installed. Install with 'pip install redis'")

    def health_check(self) -> bool:
        if not self._client:
            return False
        try:
            return self._client.ping()
        except Exception:
            return False

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        if not self._client:
            raise RuntimeError("Redis client not connected")
        
        # Simple serialization for demo purposes
        # In prod, might want pickle or consistent JSON
        if isinstance(value, (dict, list)):
            val_str = json.dumps(value)
        else:
            val_str = str(value)
            
        return self._client.set(key, val_str, ex=ttl)

    def get(self, key: str) -> Optional[Any]:
        if not self._client:
            raise RuntimeError("Redis client not connected")
            
        val_str = self._client.get(key)
        if val_str is None:
            return None
            
        # Attempt minimal deserialization
        try:
            return json.loads(val_str)
        except (json.JSONDecodeError, TypeError):
            return val_str

    def delete(self, key: str) -> bool:
        if not self._client:
            raise RuntimeError("Redis client not connected")
        count = self._client.delete(key)
        return count > 0
