"""Seed tool for default AutoSec metric definitions."""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from factory.mcp_utils.interface import ToolResult, operational, ok
from factory.mcp_utils.registration import typed_tool

from .contracts.operational import (
    SeedDefaultsInput, SeedDefaultsOutput, SeedSampleDataInput, SeedSampleDataOutput,
)

from ..core import MetricType
from ..runtime.models import MetricDefinition

if TYPE_CHECKING:
    from ..runtime.runtime import MetricsRuntime

_AUTOSEC_DEFAULTS: list[dict[str, Any]] = [
    {
        "id": "autosec-coverage-score", "name": "Coverage Score",
        "metric_type": MetricType.GAUGE, "domain": "autosec",
        "category": "coverage", "source_brick": "veritas",
        "input_tool": "query_veritas",
        "format": "percent", "bounds": (0, 100),
        "thresholds": {"warning": 70, "critical": 50},
        "tags": ["autosec", "coverage"],
    },
    {
        "id": "autosec-peak-avg", "name": "PEAK Score Average",
        "metric_type": MetricType.GAUGE, "domain": "autosec",
        "category": "risk", "source_brick": "security",
        "input_tool": "sipp_run_query",
        "format": "score", "bounds": (0, 100),
        "thresholds": {"warning": 70, "critical": 50},
        "tags": ["autosec", "risk"],
    },
    {
        "id": "autosec-finding-count", "name": "Finding Count",
        "metric_type": MetricType.COUNTER, "domain": "autosec",
        "category": "risk", "source_brick": "security",
        "input_tool": "sipp_run_query",
        "format": "number", "tags": ["autosec", "risk"],
    },
    {
        "id": "autosec-mttr", "name": "Mean Time to Remediate",
        "metric_type": MetricType.GAUGE, "domain": "autosec",
        "category": "performance", "source_brick": "security",
        "input_tool": "sipp_run_query",
        "format": "duration", "tags": ["autosec", "performance"],
    },
    {
        "id": "autosec-drift-rate", "name": "Drift Rate",
        "metric_type": MetricType.GAUGE, "domain": "autosec",
        "category": "coverage", "source_brick": "metrics",
        "input_tool": "metrics_detect_drift",
        "format": "percent", "bounds": (0, 100),
        "thresholds": {"warning": 70, "critical": 50},
        "tags": ["autosec", "coverage"],
    },
    {
        "id": "autosec-eval-pass-rate", "name": "Eval Pass Rate",
        "metric_type": MetricType.GAUGE, "domain": "autosec",
        "category": "quality", "source_brick": "evals",
        "input_tool": "evals_run_suite",
        "format": "percent", "bounds": (0, 100),
        "thresholds": {"warning": 70, "critical": 50},
        "tags": ["autosec", "quality"],
    },
    {
        "id": "autosec-resource-count", "name": "Resource Count",
        "metric_type": MetricType.GAUGE, "domain": "autosec",
        "category": "coverage", "source_brick": "veritas",
        "input_tool": "query_veritas",
        "format": "number", "tags": ["autosec", "coverage"],
    },
    {
        "id": "autosec-portfolio-health", "name": "Portfolio Health",
        "metric_type": MetricType.COMPOSITE, "domain": "autosec",
        "category": "risk", "source_brick": "metrics",
        "input_tool": "metrics_compute_aggregation",
        "format": "score", "bounds": (0, 100),
        "thresholds": {"warning": 70, "critical": 50},
        "composite_formula": (
            "avg(autosec-coverage-score, autosec-peak-avg,"
            " autosec-eval-pass-rate)"
        ),
        "tags": ["autosec", "risk", "composite"],
    },
]


def register(mcp: Any, runtime: "MetricsRuntime") -> None:
    """Register seed tools."""

    @typed_tool(mcp)
    @operational(input_model=SeedDefaultsInput, output_model=SeedDefaultsOutput)
    def metrics_seed_defaults() -> ToolResult[SeedDefaultsOutput]:
        """Seed default AutoSec metric definitions (idempotent)."""
        created, skipped = [], []
        for raw in _AUTOSEC_DEFAULTS:
            mid = raw["id"]
            if runtime.get_definition(mid) is not None:
                skipped.append(mid)
                continue
            defn = MetricDefinition(**raw)
            runtime.register_definition(defn)
            created.append(mid)
        return ok(SeedDefaultsOutput(ok=True, created=created, skipped=skipped, total=len(_AUTOSEC_DEFAULTS)))

    @typed_tool(mcp)
    @operational(input_model=SeedSampleDataInput, output_model=SeedSampleDataOutput)
    def metrics_seed_sample_data(
        hours: int = 48, points_per_metric: int = 24,
    ) -> ToolResult[SeedSampleDataOutput]:
        """Seed time-spread sample data points for all registered metrics.

        Generates data points spread evenly across the last `hours` window
        so snapshots and trend charts show meaningful values.
        """
        definitions = runtime.list_definitions()
        if not definitions:
            return ok(SeedSampleDataOutput(ok=False, error="No metrics registered. Run metrics_seed_defaults first."))

        _FORMAT_RANGES: dict[str, tuple[float, float, float]] = {
            # (low, high, trend_range)
            "percent": (60.0, 95.0, 10.0),
            "score": (50.0, 90.0, 8.0),
            "number": (10.0, 500.0, 50.0),
            "duration": (1.0, 72.0, 5.0),
        }
        default_range = (0.0, 100.0, 10.0)

        now = datetime.now(timezone.utc).timestamp()
        span = hours * 3600
        total = 0

        for defn in definitions:
            mid = defn["id"]
            low, high, trend = _FORMAT_RANGES.get(defn.get("format", ""), default_range)
            for i in range(points_per_metric):
                ts = now - span + i * (span / points_per_metric)
                base = random.uniform(low, high)
                value = round(base + (i / points_per_metric) * trend, 2)
                runtime.store.record(mid, value, None, ts)
            total += points_per_metric

        return ok(SeedSampleDataOutput(ok=True, metrics_seeded=len(definitions),
            points_per_metric=points_per_metric, total_points=total))
