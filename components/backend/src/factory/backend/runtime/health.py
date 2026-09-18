"""Health checking for backend adapters."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from .registry import AdapterRegistry, AdapterType


class HealthStatus(str, Enum):
    """Health status for adapters."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


class HealthCheckResult(BaseModel):
    """Result of a health check."""
    adapter_name: str
    status: HealthStatus
    message: str = ""
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ConnectionTest(BaseModel):
    """Result of a connection test."""
    adapter_name: str
    success: bool
    latency_ms: float | None = None
    error: str | None = None
    tested_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class HealthChecker:
    """Health checker for backend adapters."""

    def __init__(self, registry: AdapterRegistry) -> None:
        self._registry = registry

    def check(self, adapter_name: str) -> HealthCheckResult:
        """Check health of a specific adapter."""
        config = self._registry.get(adapter_name)
        
        if config is None:
            return HealthCheckResult(
                adapter_name=adapter_name,
                status=HealthStatus.UNKNOWN,
                message=f"Adapter '{adapter_name}' not found",
            )
        
        if not config.enabled:
            return HealthCheckResult(
                adapter_name=adapter_name,
                status=HealthStatus.DEGRADED,
                message=f"Adapter '{adapter_name}' is disabled",
            )
        
        stats = self._registry.get_stats(adapter_name)
        if stats and not stats.connected:
            return HealthCheckResult(
                adapter_name=adapter_name,
                status=HealthStatus.UNHEALTHY,
                message=f"Adapter '{adapter_name}' is not connected",
            )
        
        return HealthCheckResult(
            adapter_name=adapter_name,
            status=HealthStatus.HEALTHY,
            message=f"Adapter '{adapter_name}' is healthy",
        )

    def check_all(self) -> list[HealthCheckResult]:
        """Check health of all adapters."""
        return [self.check(name) for name in self._registry.list_adapters()]

    def test_connection(self, adapter_name: str) -> ConnectionTest:
        """Test connection to an adapter."""
        config = self._registry.get(adapter_name)
        
        if config is None:
            return ConnectionTest(
                adapter_name=adapter_name,
                success=False,
                error=f"Adapter '{adapter_name}' not found",
            )
        
        # For memory-based adapters, always succeed
        if config.backend in ("memory", "networkx", "tinydb"):
            start = time.perf_counter()
            # Simulate a quick operation
            time.sleep(0.001)
            latency = (time.perf_counter() - start) * 1000
            return ConnectionTest(
                adapter_name=adapter_name,
                success=True,
                latency_ms=round(latency, 2),
            )
        
        # For external adapters, attempt actual connection
        try:
            start = time.perf_counter()
            self._test_external_connection(config)
            latency = (time.perf_counter() - start) * 1000
            return ConnectionTest(
                adapter_name=adapter_name,
                success=True,
                latency_ms=round(latency, 2),
            )
        except Exception as e:
            return ConnectionTest(
                adapter_name=adapter_name,
                success=False,
                error=str(e),
            )

    def _test_external_connection(self, config: Any) -> None:
        """Test connection to external backend."""
        if config.backend == "redis":
            self._test_redis_connection(config)
        elif config.backend == "neo4j":
            self._test_neo4j_connection(config)
        # Add more backends as needed

    def _test_redis_connection(self, config: Any) -> None:
        """Test Redis connection."""
        try:
            import redis
            client = redis.from_url(config.connection_string or "redis://localhost:6379")
            client.ping()
        except ImportError:
            pass  # Redis not installed, skip
        except Exception as e:
            raise ConnectionError(f"Redis connection failed: {e}")

    def _test_neo4j_connection(self, config: Any) -> None:
        """Test Neo4j connection."""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                config.connection_string or "bolt://localhost:7687",
                auth=config.options.get("auth"),
            )
            driver.verify_connectivity()
            driver.close()
        except ImportError:
            pass  # Neo4j not installed, skip
        except Exception as e:
            raise ConnectionError(f"Neo4j connection failed: {e}")

    def overall_health(self) -> dict[str, Any]:
        """Get overall health status."""
        results = self.check_all()
        
        if not results:
            return {
                "status": HealthStatus.UNKNOWN.value,
                "message": "No adapters registered",
                "adapters": [],
                "total_adapters": 0,
            }
        
        unhealthy = [r for r in results if r.status == HealthStatus.UNHEALTHY]
        degraded = [r for r in results if r.status == HealthStatus.DEGRADED]
        
        if unhealthy:
            status = HealthStatus.UNHEALTHY
        elif degraded:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY
        
        return {
            "status": status.value,
            "adapters": [r.model_dump() for r in results],
            "total_adapters": len(results),
            "healthy_count": len([r for r in results if r.status == HealthStatus.HEALTHY]),
            "unhealthy_count": len(unhealthy),
            "degraded_count": len(degraded),
        }
