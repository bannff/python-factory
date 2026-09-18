# Bug: dataset_submit_generation MCP schema marks optional args as required, breaking can_run_full_pipeline ingest stage

**Severity:** P1 — `can_run_full_pipeline` and any caller of `dataset_submit_generation` through MCP fails before the can_ingest fix is exercised, masking the P0 verification path
**Component:** factory.mcp_server (FastMCP schema generation for `dataset.dataset_submit_generation`)
**Discovered:** 2026-08-03 during CAN ML pilot retest of commit 3dca1018, fresh opencode session on 751AC1C3
**Status:** REPRODUCED — confirmed against the live MCP server (`companion-x_health_check` 40/40, all 5 env vars present) and against the existing `test_lightgbm_api_restart.py` test, which also fails on this same validation error
**Related:** commit 3dca1018 ("Contain Dataset MF4 and LightGBM failures") fixed Bug 1 + the new P0 independently of this bug

## Symptom

A caller invokes `machine_learning.mcp::can_run_full_pipeline` with a fixture MF4 + DBC + a `synthesize.multiplier: 1000` config (Path A from the CAN pilot retest handoff). The MCP process stays alive. No `.ips` crash. But the call returns a tool-level error:

```json
{
  "ok": true,
  "result": {
    "kind": "tool",
    "structured_content": {
      "error": "ingest submit failed: 8 validation errors for call[submit_generation]\nscenario_pack_identity\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]\nscenario_pack_version\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]\nscenario_pack_uri\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]\nscenario_pack_digest\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]\ngenerator_adapter\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]\ngenerator_version\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]\ngeneration_seed\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]\nrequested_views\n  Missing required keyword only argument [type=missing_keyword_only_argument, input_value={'recipe_uri': 'recipe://...'}, input_type=dict]",
      "stage": "ingest",
      "job_id": null
    }
  }
}
```

The Pydantic error URL `https://errors.pydantic.dev/2.12/v/missing_keyword_only_argument` confirms this is FastMCP's Pydantic-layer signature validation, not a runtime error inside the tool.

## Root cause

`factory.dataset.mcp.operational::submit_generation` (`components/dataset/src/factory/dataset/mcp/operational.py:39`) declares 8 keyword-only arguments after `*` with `= None` defaults in the Python signature:

```python
def submit_generation(
    recipe_uri: str,
    recipe_digest: str,
    context_snapshot_uri: str,
    context_snapshot_digest: str,
    tool_schema_snapshot_uri: str,
    tool_schema_snapshot_digest: str,
    *,
    allowed_tools: list[str] | None = None,
    input_artifact_uris: list[str] | None = None,
    input_artifact_digests: list[str] | None = None,
    input_artifact_roles: list[str] | None = None,
    scenario_pack_identity: str | None = None,
    scenario_pack_version: str | None = None,
    scenario_pack_uri: str | None = None,
    scenario_pack_digest: str | None = None,
    generator_adapter: str | None = None,
    generator_version: str | None = None,
    generation_seed: int | None = None,
    requested_views: str | None = None,
    fail_closed: bool = True,
    retry_from_checkpoint_only: bool = True,
    idempotency_key: str | None = None,
    schema_version: str = "1.0",
    storage_root: str | None = None,
) -> dict:
```

But the JSON schema that FastMCP generates and advertises (`companion-x_get_brick_tools dataset` → `dataset_submit_generation.input_schema.required`) lists **all 23 fields as required**:

**Bug trigger is specific to the parameter shape:** the 8 affected fields are declared as **keyword-only args after a `*` separator with `= None` defaults**. Regular optional args with `= None` / `= "..."` / `= False` defaults in the same tool (and in `dataset_materialize_can_training_bundle`) are emitted correctly into the schema's optional section. Verified against the new fields added to `dataset_materialize_can_training_bundle` in #713 (`dbc_catalog_id`, `vehicle_alias`, `dbc_catalog_version`, `message_fingerprints`, `failure_pattern_refs`, etc.) — all appear under `properties` with `default: null` and are absent from `required`. Only the post-`*` keyword-only block on `submit_generation` is dropped. Fix searches should focus on FastMCP's handling of `inspect.signature(...).parameters[name].kind == KEYWORD_ONLY` with `default is None`.

```json
"required": [
  "recipe_uri", "recipe_digest", "context_snapshot_uri", "context_snapshot_digest",
  "tool_schema_snapshot_uri", "tool_schema_snapshot_digest",
  "allowed_tools", "input_artifact_uris", "input_artifact_digests", "input_artifact_roles",
  "scenario_pack_identity", "scenario_pack_version", "scenario_pack_uri", "scenario_pack_digest",
  "generator_adapter", "generator_version", "generation_seed", "requested_views",
  "fail_closed", "retry_from_checkpoint_only", "idempotency_key", "schema_version", "storage_root"
]
```

This is a FastMCP schema-generation regression. The Python defaults are being dropped when the `input_schema` is built. Pydantic then sees 8 keyword-only arguments without defaults and rejects any call that doesn't supply all of them.

`can_keystone_runner.py::run_keystone_stage` (`components/machine_learning/src/factory/machine_learning/runtime/can_keystone_runner.py:40-46`) only constructs the 14 fields the ingest stage actually needs:

```python
request = build_dataset_request(
    recipe_uri, input_uris, context_config, snaps, idempotency_key,
    input_roles=input_roles,
)
receipt = invoker(
    "dataset_submit_generation", **request, storage_root=str(root),
)
```

…and `build_dataset_request` (`can_keystone_dataset_payload.py:48-89`) returns a 14-key flat dict (recipe_uri, recipe_digest, the two snapshot pairs, allowed_tools, input_artifact_uris/digests/roles, fail_closed, retry_from_checkpoint_only, idempotency_key, schema_version). The 8 scenario-generation fields are intentionally omitted because they describe a separate codepath (`ScenarioPackGenerationInput`) that the Dataset runtime constructs internally when its model has all 7 fields.

## Why this is distinct from the P0 MCP crash

- The P0 was a hard process termination with a `.ips` file. This bug returns a structured tool-level error and the MCP process stays alive (`pgrep -fl 'factory.mcp_server.core'` returns 86749, 86785 before and after).
- The P0 was about `ml_train_timeseries` (machine_learning brick). This bug is about `dataset_submit_generation` (dataset brick).
- The P0 was fixed by commit 3dca1018 (verified live on 2026-08-03 — see Verification below). This bug is pre-existing, reproducible against `main` HEAD, and the existing `test_lightgbm_api_restart.py` (which uses the same `can_run_full_pipeline` path through a fresh API subprocess) also fails with this same error.

## Reproduction (live MCP, fresh opencode session)

```bash
# 1. Fixture (4.3 KB MF4 + DBC)
uv run --project . python -c "
import sys; sys.path.insert(0, '.')
from projects.companion_x.api_restart_support import write_fixture
from pathlib import Path
root = Path('.dataset_store/can_pilot_retest_20260803_1133')
root.mkdir(parents=True, exist_ok=True)
write_fixture(root)
"

# 2. Sanity: health + env vars + model-root dirs
companion-x_health_check  # healthy: 40/40
ps eww -p $(pgrep -f factory.mcp_server.core | head -1) | tr ' ' '\n' | grep -E 'ML_|TORCH|LNN|PATCHTST'
# → 5 lines, all under .dataset_store/

# 3. Call can_run_full_pipeline via the live MCP
companion-x_call_brick_tool \
  brick_name=machine_learning tool_name=can_run_full_pipeline \
  arguments='{"mf4_dir":".dataset_store/can_pilot_retest_20260803_1133/capture",
              "dbc_path":".dataset_store/can_pilot_retest_20260803_1133/capture/fixture.dbc",
              "vehicle_id":"retest-fixture-1",
              "storage_root":".dataset_store/can_pilot_retest_20260803_1133/datasets",
              "max_samples":80, "top_n_can_ids":1,
              "model_types":["lightgbm"],
              "config_overrides":{"synthesize":{"multiplier":1000,"failure_rate":0.3,"seed":7}}}'

# → tool-level error: "ingest submit failed: 8 validation errors for call[submit_generation]"
# → MCP process still alive (PIDs 86749, 86785)
# → No new python3.13-*.ips in ~/Library/Logs/DiagnosticReports/
```

The existing pytest reproduction is even simpler:

```bash
uv run --project projects/companion_x pytest \
  projects/companion_x/test/test_lightgbm_api_restart.py -x
# → KeyError: 'comparison_table' on line 46 (pipeline["comparison_table"])
#   because pipeline has no "error" key but also no "comparison_table" key
#   (it has the 8-validation-error structured_content above)
```

## Why the retest still PASSES the original P0/Bug 1 verification

The P0 crash and Bug 1 read-only-MF4 failure live in different code paths that don't depend on `can_run_full_pipeline` going through `dataset_submit_generation`:

- **New P0 (MCP crash on `ml_train_timeseries`):** `ml_train_timeseries` is its own MCP tool on the machine_learning brick. Calling it directly with valid `X_uri`/`y_uri` (file:// paths to `.npy` files) and a small config works end-to-end. LightGBM produced a real MLflow artifact (AUROC 0.90, model_path in `.dataset_store/lightgbm_models/.../mlflow-model/`); LSTM produced a real `model.pt` artifact. The MCP process stayed alive across both calls. No `.ips`.
- **Bug 1 (read-only MF4 permission denied):** `dataset_materialize_can_training_bundle` on the fixture MF4 after `chmod 444 fixture.mf4` returned `status: completed` with full augment artifacts. The new `open_mf4_stream` (`components/dataset/src/factory/dataset/runtime/mf4_source.py`) opens the file with `O_RDONLY` and passes the descriptor to `MDF(stream, read_only=True)`, so asammdf's broken `read_only=True` no-op is bypassed by an OS-level read-only descriptor.

Both 3dca1018 fix goals are verified. The schema bug blocks the *combined* `can_run_full_pipeline` end-to-end run, but the individual failure modes from the handoff are independently fixed.

## Suggested fix

Two paths, in order of preference:

1. **Find the FastMCP schema-generation regression** that drops `= None` defaults from keyword-only arguments and file an upstream issue / PR. The Pydantic 2.12 + FastMCP version combination on this checkout is generating incorrect `required` lists for any tool that uses keyword-only args with defaults.
2. **Make the 8 affected args explicitly defaulted via `Field(default=None, ...)` on a Pydantic model** the tool takes, so FastMCP's schema generator picks up the defaults. Or split the scenario-generation fields behind a nested `ScenarioPackGenerationInput` object in the MCP signature (matches the underlying runtime model).

Until fixed, the `can_run_full_pipeline` end-to-end recipe remains unusable. Individual stage tools (`can_ingest`, `ml_train_timeseries`) and `dataset_materialize_can_training_bundle` (the synchronous terminal) all work and are sufficient for the CAN pilot's per-CAN training path (Path B in the retest handoff).
