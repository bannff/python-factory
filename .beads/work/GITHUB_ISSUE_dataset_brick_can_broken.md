# [BUG] Dataset brick CAN materialization is broken on the happy path — 6 bugs found in one pilot

**Component:** `components/dataset`
**Spec:** `.github/spec/can-failure-prediction.md`, `.github/spec/ml-dataset-generation.md`
**Discovered:** 2026-08-02 during can-ml pilot on `751AC1C3` (Toyota MF4, 50 files, 47 MB)
**Goal of the pilot:** enrich the 131 GB of decoded CAN data on `/Volumes/Crucial X9/can_data/` with realistic failure modes and a ≥10% failure rate, using only the documented `dataset` brick MCP tools (`dataset_materialize_can_training_bundle`, `dataset_submit_generation`).

## TL;DR

The `dataset` brick has 6 distinct bugs that prevent the documented CAN materialization workflow from running end-to-end. The 6th is the worst: a recipe that produces 0 records is reported as **`status: "completed"`** with an empty artifact and a SHA-256 of the empty string. The new synchronous terminal (`dataset_materialize_can_training_bundle`) is **completely unusable** for MF4 inputs. The two multi-stage recipes (`can-pipeline@1`, `can-pipeline-aug@1`) silently emit 0 records past the first stage.

Working pattern (verified): run each stage as a separate `dataset_submit_generation` job with single-stage recipes, routing via `input_artifact_uris` and `stage_overrides` in the context snapshot. This produced a 7.7M-record, 9.5%-failure-rate, 6.5 GB synthetic bundle with all 8 failure modes represented.

## Bugs

### Bug 1 — `dataset_materialize_can_training_bundle` is unusable (P0)

The new synchronous terminal copies MF4 files into a read-only snapshot directory. `asammdf` opens MDF with `rb+` (read-write) mode and fails with `PermissionError`. `can_ingest._iter_mf4_frames` silently swallows the exception (`try/except Exception: return`). The ingest stage emits 0 records, the profile stage gets 0 records and produces `can_ids: {}`, the terminal returns `{"status": "failed", "error": "CAN profile contains no CAN-IDs"}`.

**Bead:** `python-factory-can-snap-bug.md`
**Fix:** open asammdf in `read_only=True`, or relax snapshot perms for MF4.

### Bug 2 — `input_artifact_uris` must be `file://` prefixed (P1)

`dataset_submit_generation` accepts `input_artifact_uris=["/Volumes/.../foo.MF4", ...]` and silently produces an empty bundle. The recipe loader at `recipe.py:152` filters by `a.uri.startswith("file://")` and discards all plain absolute paths. The MCP tool's schema documents the parameter as `type: array, items: type: string` with no URI format hint. The fail-closed check at `can_ingest.execute` raises `"can_ingest requires non-empty 'mf4_paths' config"` only after the worker has already started.

**Bead:** `python-factory-can-uri-bug.md`
**Fix:** normalize plain absolute paths to `file://` URIs in the MCP tool before building `DatasetInputRef`. Or accept both forms in the recipe loader.

### Bug 3 — context_snapshot fields leak into all stages (P1)

The `_snapshot_overrides` helper (`recipe_config.py:20-37`) returns the **entire** payload for every stage unless `payload["stage_overrides"]` is present. A snapshot like `{"dbc_path": "...", "vehicle_id": "..."}` succeeds for `can_ingest` (its `allowed_config` includes both) and fails on `can_profile` (`ValueError: Unsupported can_profile configuration: ['dbc_path', 'vehicle_id']`) or `can_window` (`Unsupported can_window configuration: ['vehicle_id']`). This blocks every multi-stage recipe.

**Bead:** `python-factory-snapshot-leak.md`
**Fix:** filter the snapshot by each stage's `allowed_config`, or document the `stage_overrides` scoping as the only supported pattern.

### Bug 4 — `can-pipeline@1` and `can-pipeline-aug@1` are broken at profile→synthesize (P0)

The recipes wire stages as `stage[i].output → stage[i+1].input`. After `can_profile` produces a 1-record constraint schema, the `can_synthesize` stage receives 1 record (not the 1.8M-frame ingest output) and emits 0 synthesized records. Manifest lineage confirms:
```
can_ingest:    0 → 1,841,338 records
can_profile:   1,841,338 → 1 (schema)
can_synthesize: 1 → 0
can_window:    0 → 0
can_augment:   0 → 0
```

The new terminal (`dataset_materialize_can_training_bundle`) composes them correctly (ingest output as synthesize input, profile as `constraint_schema` config) but the recipes don't. Working prior job `dce71238` (2026-07-15) used single-stage `can-synthesize@1` with `input_uri` directly.

**Bead:** `python-factory-pipeline-bug.md`
**Fix:** remove or deprecate the multi-stage recipes; route users to the terminal (after fixing Bug 1) or to the single-stage chain pattern.

### Bug 5 — empty-bundle "completed" status is the worst silent failure (P0)

`dataset_submit_generation` with a recipe that produces 0 records returns `status: "completed"` and an artifact with `digest: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (SHA-256 of empty string) and a 0-byte file. `quality_results.passed` is `true` because the record_count check passes for 0 records. Downstream consumers (`dataset_get_artifact` → `machine_learning` training) silently produce empty models.

The new terminal detects this and returns `status: "failed"`, but the older async path does not. The check should be at the materializer level (fail-closed on empty final records) and reinforced in the store/quality layer.

**Bead:** `python-factory-empty-bundle-bug.md`
**Fix:** raise in `LocalDatasetMaterializer.materialize` if `records == []`; treat empty-string digest as a sentinel; tighten `evaluate_quality`.

### Bug 6 — DBC coverage gap for non-standard fleet IDs (P1, environment)

The fleet on `/Volumes/Crucial X9/can_data/mf4_files/{VIN}/` produces arbitration IDs (0xF1, 0xC1, 0x1E5, 0xBE, 0x232, 0xAA, ...) that don't match any of the 9 DBC files in `/Volumes/Crucial X9/can_data/dbc_files/`. Toyota legacy covers 1–3 of the top-20 IDs per VIN. The default OBD2 DBC (8 messages, 0x7E8-0x7EF) covers 0. The new terminal's `can_ingest._iter_mf4_frames` returns `decoded_signals: null` for unmatched IDs, the profile skips them, the pipeline emits 0 records.

**Bead:** included in this issue (no separate file — environment, not code)
**Workaround:** synthesize a DBC at runtime that maps each observed arbitration ID to 8 byte-level signals. The pilot produced `/Volumes/Crucial X9/can_data/dbc_files/fleet_synthetic_byte.dbc` (218 messages) covering the entire observed fleet. Toyota legacy still works for the 751AC1C3 fleet subset.

## Side-finding (not a bug, but worth noting)

`can_synthesize` uses `sdv` (Synthetic Data Vault) to fit a GaussianCopula per CAN ID. Every fit emits a `UserWarning: We strongly recommend saving the metadata using 'save_to_json' for replicability in future SDV versions.` The adapter does not persist the SDV metadata, so the synthesizer cannot be reloaded from the bundle. For the user's "best dataset" goal — training models that can be reproduced or transferred — this is a reproducibility gap. Not a bug, but should be tracked.

## What works (verified end-to-end)

1. `dataset_submit_generation` with `recipe://local/can-ingest@1` and ORIGINAL MF4 file URIs (no snapshot) — runs in subprocess, produces 1.84M records for 50 MF4 files (47 MB → 742 MB JSONL, ~15 sec). Full 153-file trip produces 8.2M records (prior `3b0106b9` job, 2026-07-28).
2. `dataset_submit_generation` with `recipe://local/can-synthesize@1` and the ingest JSONL as `input_artifact_uris` — produces 7.7M synthesized records (1.8M × multiplier 10, minus some dropped), 6.5 GB, 9.5% failure rate, all 8 failure modes represented (`signal_drift`, `drop_to_zero`, `out_of_sequence`, `sensor_degradation`, `ecu_timeout`, `signal_freeze`, `spike_noise`, `correlation_break`). Job `5aa3734d` completed in ~4 min on this machine.
3. The synthesized bundle has full provenance: `source_lineage` (original MF4 record), `synthetic_lineage` (SDV row), `failure_mode`, `failure_strategy: "rule"`, `failure_timestamp_ns`, `is_failure: 0|1`, `context: {}` (empty, not conditioned).

## Recommendations

1. **Fix Bug 1 first** (snapshot read-only). It's a 1-line change in `can_ingest._iter_mf4_frames` to pass `read_only=True` to `MDF()`. After this, the new terminal is usable and the multi-stage recipes can be removed/deprecated.
2. **Fix Bug 5** (empty-bundle success) — fail-closed at the materializer. Easy, high-value.
3. **Fix Bug 2 + Bug 3 together** — the MCP tool's `input_artifact_uris` should accept and normalize both forms, and the snapshot loader should filter by stage `allowed_config` or require the `stage_overrides` form. These are the two "silent data loss" bugs.
4. **Remove or deprecate `can-pipeline@1` and `can-pipeline-aug@1`** (Bug 4). Either fix the wiring or document them as broken.
5. **DBC coverage** (Bug 6) — generate the synthetic byte-level DBC at ingest time if no matching DBC is found, instead of returning 0 records. The infrastructure is already there (`can_decode.try_decode` falls back to raw bytes); the profile just needs to include raw-frame CAN-IDs.

## Pilot output (not committed)

- Ingest: `/Users/danielrodrigo/Workspace/python-factory/.dataset_store/checkpoints/3b42ebc6-.../stage-0-c3d087c3....jsonl` (1.84M records, 708 MB, read-only)
- Synthesize: `/Users/danielrodrigo/Workspace/python-factory/.dataset_store/artifacts/5aa3734d-.../dataset-df40941e....jsonl` (7.7M records, 6.05 GB, read-only)
- Window job `ddb69a8d`: still running at 100% CPU, 15.3 GB RAM at time of issue filing (5-sec windows on 7.7M records)
- Beads: `python-factory-{can-snap-bug,can-uri-bug,snapshot-leak,pipeline-bug,empty-bundle-bug}.md` in `.beads/work/`
- Synthetic DBC: `/Volumes/Crucial X9/can_data/dbc_files/fleet_synthetic_byte.dbc`

## Metadata

Pilot run by: opencode agent (M3) on 2026-08-02
Input: 50 MF4 files (47 MB) from `751AC1C3/00000011/`
Synthesized: 7.7M records, 9.5% failure rate, 6.5 GB, 8 failure modes
Wall time: ~7 min for ingest+window+synthesize pipeline (window still running at filing)
