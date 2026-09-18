# Bug: context_snapshot fields leak into stages that don't accept them

**Severity:** P1 — multi-stage recipes fail when snapshot has stage-specific config keys
**Component:** components/dataset
**Discovered:** 2026-08-02 during can-ml pilot on 751AC1C3 with `recipe://local/can-pipeline-aug@1`

## Symptom

`dataset_submit_generation` with `recipe://local/can-pipeline-aug@1` and a `context_snapshot` JSON like `{"dbc_path": "...", "vehicle_id": "..."}` fails after ~10s in the second stage (can_profile) with:

```
ValueError: Unsupported can_profile configuration: ['dbc_path', 'vehicle_id']
  File ".../stage_runner.py", line 92, in run_stage_loop
    records = list(stage.execute(records, stage_config))
  File ".../can_profile.py", line 41, in execute
    raise ValueError(f"Unsupported can_profile configuration: {sorted(unknown)}")
```

The first stage (can_ingest) succeeds because its `allowed_config` is `{"mf4_paths", "dbc_path", "vehicle_id"}`. The second stage (can_profile) rejects the same dict because its `allowed_config` is `{"window_ms", "correlation_threshold", "input_uri"}`.

## Root cause

`components/dataset/src/factory/dataset/runtime/recipe_config.py:20-37` — `_snapshot_overrides` returns the **entire** payload for every stage unless `payload["stage_overrides"]` is present. Single-stage recipes (e.g. `can-ingest@1`) work because can_ingest accepts the keys. Multi-stage recipes (`can-pipeline@1`, `can-pipeline-aug@1`, etc.) fail on the second stage.

The prior working job `3b0106b9` (2026-07-28) used `recipe://local/can-ingest@1` (single stage), so this issue was hidden.

## Fix options

1. **Filter by stage `allowed_config`** (recipe_config.py): before applying snapshot overrides, intersect with the stage's allowed_config. Stage-agnostic keys (`multiplier`, `seed`) pass through everywhere; stage-specific keys (`dbc_path`) only pass to stages that accept them.
2. **Document the `stage_overrides` pattern** (docs + MCP tool description) and require callers to use it for multi-stage recipes. The current docstring is silent.
3. **Make stages silently ignore unknown keys** (defensive): change the `ValueError` to a `logger.debug` for unknown config keys. Risk: hides real typos.
4. **Auto-scope common keys** in the recipe loader: keys matching `dbc_path`/`vehicle_id` go to can_ingest only; keys matching `window_ms` go to can_window only; etc.

## Files involved

- components/dataset/src/factory/dataset/runtime/recipe_config.py:20-37 — `_snapshot_overrides`
- components/dataset/src/factory/dataset/runtime/recipe_config.py:147-171 — `_populate_stage_config`
- components/dataset/src/factory/dataset/runtime/adapters/can_profile.py:35-42 — `allowed_config` + raise
- components/dataset/src/factory/dataset/runtime/adapters/can_synthesize.py:55-70 — `allowed_config`
- components/dataset/src/factory/dataset/runtime/adapters/can_window.py — same pattern
- components/dataset/src/factory/dataset/runtime/adapters/can_augment.py — same pattern

## Workaround

Use the `stage_overrides` scoping in the context_snapshot JSON:

```json
{
  "stage_overrides": {
    "can_ingest": {"dbc_path": "/Volumes/Crucial X9/can_data/dbc_files/toyota_legacy_combined.dbc", "vehicle_id": "751AC1C3"}
  }
}
```

Other stages get an empty config dict.
