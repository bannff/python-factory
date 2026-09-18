# Bug: ml_train_timeseries tool has broken import

**Severity:** P1 — the documented ML training tool cannot be called
**Component:** components/machine_learning
**Discovered:** 2026-08-02 during can-ml pilot on 751AC1C3

## Symptom

Calling `ml_train_timeseries` via the machine_learning MCP server returns:
```
Tool 'ml_train_timeseries' failed: cannot import name 'TimeSeriesModelConfig'
from 'factory.machine_learning.runtime.ports'
('/Users/danielrodrigo/Workspace/python-factory/components/machine_learning/src/factory/machine_learning/runtime/ports.py')
```

The tool is listed in the MCP tool catalog with full input schema but every call fails with the import error.

## Root cause

`TimeSeriesModelConfig` is defined in `components/machine_learning/src/factory/machine_learning/runtime/time_series_ports.py:91` but the ml_train_timeseries tool's adapter (probably in `mcp/finetuning_tools.py` or `runtime/finetuning.py`) imports it from `factory.machine_learning.runtime.ports` — the wrong module.

## Reproduction

```python
# Via MCP
ml_train_timeseries(
    model_type="lightgbm",
    X_uri="file:///.../X.npy",
    y_uri="file:///.../y.npy",
)
# Error: cannot import name 'TimeSeriesModelConfig' from 'factory.machine_learning.runtime.ports'
```

## Fix options

1. **Fix the import** in the tool's adapter module — change `from factory.machine_learning.runtime.ports import TimeSeriesModelConfig` to `from factory.machine_learning.runtime.time_series_ports import TimeSeriesModelConfig` (or expose it from `ports`).
2. **Re-export** `TimeSeriesModelConfig` from `ports.py` for backward compatibility.

## Files involved

- components/machine_learning/src/factory/machine_learning/runtime/ports.py — needs re-export
- components/machine_learning/src/factory/machine_learning/runtime/time_series_ports.py:91 — has the class
- components/machine_learning/src/factory/machine_learning/mcp/finetuning_tools.py (or similar) — import site

## Workaround (until fixed)

Use the `can_ml_train.py` script at `scripts/CAN/can_ml_train.py` which calls the runtime directly (bypasses the broken MCP wrapper). The script trains LightGBM, Chronos-2, and LNN on a per-CAN-ID basis. It uses the OLD format (X_2d.npy, y.npy) but the new flat training data (X.npy, y.npy) is compatible if you copy/symlink.

## Severity argument

P1 because the can-ml pilot relies on this tool to evaluate model performance against the synthesized dataset. Without it, we can't answer the user's "does the data produce a useful model" question via the documented MCP path.
