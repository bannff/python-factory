# Bug: dataset_submit_generation reports "completed" with empty-digest artifact when downstream stages produce 0 records

**Severity:** P1 — silent data loss; downstream consumers get a 0-byte file
**Component:** components/dataset
**Discovered:** 2026-08-02 during can-ml pilot on 751AC1C3 (job `3b42ebc6`)

## Symptom

`dataset_submit_generation` with `recipe://local/can-pipeline-aug@1` returns:
```json
{"status": "completed", "artifact": {"dataset_uri": ".../dataset-e3b0c44298fc1c14...jsonl", "digest": "e3b0c44298fc1c14..."}}
```

The artifact file is **0 bytes**. Its digest is the SHA-256 of the empty string (`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`). The `quality_results.passed` is `true` because the quality check just verifies the (empty) record count.

The "completed" status is the success code — callers (including `dataset_get_artifact`) treat it as a valid bundle.

## Root cause

`components/dataset/src/factory/dataset/runtime/materializer.py:48-58` — `run_stage_loop` returns the final records and the worker writes them to the artifact. If the final stage produces 0 records, the artifact is empty but the write succeeds.

`components/dataset/src/factory/dataset/runtime/local.py:46-51` — `create_or_get_job` always marks the job as `completed` if no exception is raised. The empty-bundle case raises no exception.

`components/dataset/src/factory/dataset/runtime/quality.py` (or wherever `evaluate_quality` lives) — `record_count: passed: 0` is a passing check, so `quality.passed = True`.

Three failures in series:
1. Empty artifact considered "completed" (success)
2. Empty digest `e3b0...` is a well-known SHA-256 of empty string — should be a sentinel
3. Quality check passes for 0 records

## Reproduction

See the can-pipeline-aug@1 issue (`python-factory-pipeline-bug.md`). The profile stage produces 1 record, the synthesize stage receives 1 record (not the 1.8M-frame ingest output) and emits 0 records. The artifact is empty.

## Fix options

1. **Fail-closed on empty final output**: in `LocalDatasetMaterializer.materialize` (materializer.py:28-58), if the final `records` list is empty, raise `ValueError("Recipe produced an empty dataset")`. The job transitions to `failed` and the worker persists the error.
2. **Sentinel digest check**: in `LocalDatasetStore.get_artifact` (local.py:93-107), if the artifact's digest equals the empty-string SHA-256, raise `ValueError("Artifact digest is empty-string sentinel — bundle is empty")`.
3. **Quality check tightening**: `evaluate_quality` should fail if `record_count == 0` for a non-empty-pipeline recipe.
4. **All of the above**, with each layer adding defense-in-depth.

## Files involved

- components/dataset/src/factory/dataset/runtime/materializer.py:28-58 — empty records don't fail
- components/dataset/src/factory/dataset/runtime/local.py:46-51 — completed status regardless
- components/dataset/src/factory/dataset/runtime/quality_can.py (or similar) — record_count check
- components/dataset/src/factory/dataset/runtime/bundle_writer.py — empty-bundle write

## Workaround

Always check the artifact's record count after `dataset_get_artifact`. If `n_records == 0` (or the bundle file is 0 bytes), the job is a silent failure.

## Severity argument

This is the most insidious of the four bugs found in this pilot. A caller who uses `dataset_get_artifact` to retrieve the bundle URI, then passes it to `machine_learning`, will get a 0-record training run that silently produces an empty model. The new terminal (`dataset_materialize_can_training_bundle`) also has the same behavior — when I called it, it returned `status: "failed"` because the profile produced 0 records; but the older async path can return `status: "completed"` with an empty bundle. This is a P0 if the dataset brick is meant to be trusted by downstream ML stages.
