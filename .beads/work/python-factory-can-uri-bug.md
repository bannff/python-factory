# Bug: dataset_submit_generation input_artifact_uris must be file:// prefixed

**Severity:** P1 — silent data loss; no validation error, just empty pipeline
**Component:** components/dataset
**Discovered:** 2026-08-02 during can-ml pilot on 751AC1C3

## Symptom

`dataset_submit_generation` with `recipe://local/can-pipeline-aug@1` and `input_artifact_uris=["/Volumes/Crucial X9/.../foo.MF4", ...]` (plain absolute paths) returns `status: "failed", error: "can_ingest requires non-empty 'mf4_paths' config"` after 1 second.

The same call with the same paths rewritten as `file:///Volumes/Crucial%20X9/.../foo.MF4` (file:// URIs) succeeds.

## Root cause

`components/dataset/src/factory/dataset/runtime/recipe.py:152`:
```python
mf4_paths = [a.uri for a in request.input_artifacts if a.uri.startswith("file://")]
```

Plain `/Volumes/...` paths don't match the `file://` prefix filter → `mf4_paths = []` → the can_ingest stage config gets `mf4_paths=[]` → adapter raises.

The MCP `dataset_submit_generation` tool (operational.py:87-99) passes `input_artifact_uris` straight through to `DatasetInputRef.uri` without normalizing. The schema documents the parameter as `type: array, items: type: string` with no URI format hint.

## Reproduction

```python
dataset_submit_generation(
    recipe_uri="recipe://local/can-pipeline-aug@1",
    recipe_digest="f4a0d29725185035255a9f5cb8a99fb90788bd9f90d26b988d53c62da8354d27",
    input_artifact_uris=["/Volumes/Crucial X9/can_data/mf4_files/751AC1C3/00000011/00000001-6A0B6FCD.MF4", ...],
    # ... (job_id, etc.)
)
# Result: {"job_id": "...", "status": "failed", "error": "can_ingest requires non-empty 'mf4_paths' config"}
```

## Fix options

1. **Normalize in the MCP tool** (operational.py): coerce plain absolute paths to `file://` URIs before building `DatasetInputRef`. This is the safest fix because the canonical URI shape is file://.
2. **Normalize in the recipe** (recipe.py:152): accept both `file://` URIs and plain absolute paths. Expand the filter to also match `a.uri.startswith("/")`.
3. **Reject early** in `DatasetInputRef` validator or in `dataset_submit_generation`: validate the URI format upfront, return a clear error like `"input_artifact_uris must be file:// URIs or absolute paths"`.

## Files involved

- components/dataset/src/factory/dataset/mcp/operational.py:87-99 — input_artifact_uris plumbing
- components/dataset/src/factory/dataset/runtime/recipe.py:152 — silent filter
- components/dataset/src/factory/dataset/runtime/recipe_config.py:147-171 — stage config population
- components/dataset/src/factory/dataset/runtime/adapters/can_ingest.py:96-100 — mf4_paths check

## Workaround

Prefix every `input_artifact_uri` with `file://` and URL-encode the path (spaces → `%20`, etc.).
