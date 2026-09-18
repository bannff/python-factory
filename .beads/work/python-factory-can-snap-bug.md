# Bug: dataset_materialize_can_training_bundle ingest yields 0 records

**Severity:** P0 — terminal is unusable for the documented happy path
**Component:** components/dataset
**Spec:** .github/spec/can-failure-prediction.md
**Discovered:** 2026-08-02 during can-ml pilot on /Volumes/Crucial X9/can_data/mf4_files/A67E579F (sanity) and 751AC1C3 (sanity)

## Symptom

`dataset_materialize_can_training_bundle` returns:
```json
{"status": "failed", "error": "CAN profile contains no CAN-IDs"}
```

## Root cause

1. `CanTerminalService.materialize` → `snapshot_sources` (can_terminal_sources.py:14) calls `atomic_write_immutable` for every MF4 source.
2. `atomic_write_immutable` writes the file with read-only permissions (mode 0o444).
3. `can_ingest._iter_mf4_frames` (can_ingest.py:127) calls `MDF(mf4_path)` which internally opens with `rb+` (asammdf/blocks/mdf_v4.py:401).
4. The MDF open fails with `PermissionError: [Errno 13] Permission denied` on every file.
5. The `try/except Exception: return` (can_ingest.py:128-130) silently swallows the error.
6. The ingest stage yields 0 records → profile stage gets 0 input → `can_ids: {}` → terminal fails validation.

## Evidence

```
$ python3 -c "from asammdf import MDF; MDF('/Users/.../can_terminal/sources/86cae57a6.../mf4-0-...mf4')"
PermissionError: [Errno 13] Permission denied: '/var/folders/.../bf692b22b69d_mf4-0-...mf4'

$ ls -la /Users/.../can_terminal/sources/86cae57a6.../mf4-0-...mf4
-r--r--r--@ 1 danielrodrigo  staff  275712 Aug  1 22:33 mf4-0-...mf4
```

Adapter-level test (bypassing materializer) shows can_ingest works: 20/20 records decoded with Toyota DBC on the same source.

The prior working job `3b0106b9` (2026-07-28) used the **older** `dataset_submit_generation` flow with `recipe://local/can-ingest@1` and 153 ORIGINAL MF4 file URIs (`file:///Volumes/Crucial X9/can_data/mf4_files/751AC1C3/00000011/...MF4`) — not snapshotted. It produced 8.2M records.

## Workaround (until fixed)

Use `dataset_submit_generation` with `recipe://local/can-pipeline-aug@1` and the original MF4 URIs (not the terminal tool). The async worker reads from the original paths.

## Fix options

1. **`can_ingest._iter_mf4_frames`**: open MDF with `read_only=True` (or fall back to `rb` mode). asammdf supports it.
2. **`snapshot_sources`**: copy MF4 with writable permissions; rely on `atomic_write_immutable` only for the bytes content (which is already SHA-256-pinned in the canonical request). The "immutability" guarantee can stay at the manifest level.
3. **`can_ingest`**: detect `PermissionError` and retry with `read_only=True`.

## Files involved

- components/dataset/src/factory/dataset/runtime/can_terminal_sources.py:49 — `atomic_write_immutable(target, content)`
- components/dataset/src/factory/dataset/runtime/adapters/can_ingest.py:127 — `MDF(mf4_path)` (silent PermissionError on rb+)
- components/dataset/src/factory/dataset/runtime/can_terminal_pipeline.py — uses snapshotted paths
- components/dataset/src/factory/dataset/runtime/atomic_io.py — write_immutable sets 0o444

## Bead

Created as discovered-from for the can-ml pilot. Tenet: "Investigate the cause before fixing the symptom" applies — the can_ingest silent error swallow is the proximate cause; the snapshot read-only is the root cause.
