# Bug: can-pipeline@1 and can-pipeline-aug@1 have broken stage composition

**Severity:** P0 — the documented end-to-end recipes for CAN materialization are non-functional
**Component:** components/dataset
**Spec:** .github/spec/can-failure-prediction.md, .github/spec/ml-dataset-generation.md
**Discovered:** 2026-08-02 during can-ml pilot on 751AC1C3

## Symptom

`dataset_submit_generation` with `recipe://local/can-pipeline-aug@1` returns `status: "completed"` and an artifact URI, but the artifact is a 0-byte file with digest `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (SHA-256 of empty string).

Manifest stage lineage shows the wiring:

| stage | input records | output records |
|---|---|---|
| can_ingest | 0 | **1,841,338** |
| can_profile | 1,841,338 | 1 (constraint schema) |
| can_synthesize | 1 | **0** |
| can_window | 0 | 0 |
| can_augment | 0 | 0 |

`can_synthesize` receives the 1-record profile output as its `records` input, not the 1.8M-frame ingest output. It groups records by `arbitration_id`, finds zero CAN-ID groups, and emits nothing.

## Root cause

`components/dataset/src/factory/dataset/runtime/recipe.py:79-96`:
```python
"recipe://local/can-pipeline@1": (
    "can-pipeline-v1",
    [
        {"name": "can_ingest", "config": {}},
        {"name": "can_profile", "config": {}},
        {"name": "can_synthesize", "config": {}},
        {"name": "can_window", "config": {}},
    ],
),
```

The recipe wires stages as `stage[i].output → stage[i+1].input`. The `can_profile` stage produces a single constraint schema, not frames. The `can_synthesize` stage needs the **frames** (from ingest) and the **schema** (as `constraint_schema` config), not the schema as input.

The new terminal `dataset_materialize_can_training_bundle` (can_terminal_pipeline.py:60-77) handles this correctly by:
1. Running can_ingest
2. Running can_profile
3. Loading the profile as a `constraint_schema` config
4. Running can_synthesize with `input_uri=ingest_output_uri, config={..., "constraint_schema": profile}`

But the recipe-based pipeline in the older `dataset_submit_generation` flow has no such composition step. The `can_synthesize` adapter alone (can_synthesize.py:50-108) can take an `input_uri` config and synthesize from a JSONL, but the multi-stage recipe doesn't route the ingest output there.

## Evidence

Successful prior job `dce71238` (2026-07-15) used **single-stage** `recipe://local/can-synthesize@1` with:
- `input_artifact_uris=[file:///.../keystone-751AC1C3-sampled-...jsonl]` (a separately-sampled CAN data file)
- `context_snapshot.uri=.../keystone_snapshots/context-eea2a066...json` (with dbc_path + vehicle_id)
- Resolved config: `{"multiplier": 10, "failure_rate": 0.1, "seed": 42, "method": "gaussian_copula"}`
- Output: 4,320 records with `failure_mode`, `is_failure: 1`

It worked because the synthesize stage got the FRAMES directly via `input_uri`, not as a chained input from can_profile.

## Fix options

1. **Remove or deprecate** `can-pipeline@1` and `can-pipeline-aug@1` — they cannot work with the current stage architecture. Add a clear error message if someone tries to use them.
2. **Add a composition step** to multi-stage recipes: the `can_synthesize` stage should be wired to receive BOTH the ingest output as input AND the profile as `constraint_schema` config. This requires a recipe-schema extension.
3. **Document the manual sequence** (which works today):
   - can-ingest@1 → produces ingest artifact
   - can-profile@1 → produces profile artifact (with input_uri=ingest)
   - can-synthesize@1 → produces synth artifact (with input_uri=ingest OR sampled variant, constraint_schema=profile)
   - can-window@1 → windowed
   - can-augment@1 → augmented
4. **Fix the new terminal** (the read-only snapshot bug is separate) and route users there. The terminal already has the right composition.

## Files involved

- components/dataset/src/factory/dataset/runtime/recipe.py:78-97 — broken recipes
- components/dataset/src/factory/dataset/runtime/adapters/can_synthesize.py:103-108 — input_uri handling
- components/dataset/src/factory/dataset/runtime/adapters/can_profile.py:80-107 — single-record schema output
- components/dataset/src/factory/dataset/runtime/can_terminal_pipeline.py:60-77 — correct composition (for reference)

## Workaround (until fixed)

Run each stage as a separate `dataset_submit_generation` job using single-stage recipes, with `input_artifact_uris` pointing at the previous stage's artifact URI and config overrides via the context_snapshot `stage_overrides` block. This is the pattern the prior dce71238 job used.

## Recommendation

Option 4 (fix the new terminal's read-only snapshot bug) is the right path forward. The terminal's composition logic is correct; the multi-stage recipes are obsolete and should be removed or marked `@deprecated` with an `ingest -> synthesize` composition stage added.
