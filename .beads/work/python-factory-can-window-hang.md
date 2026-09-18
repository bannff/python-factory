# Bug: can_window@1 hangs on 6+ GB synthesized input

**Severity:** P2 — functional but not scalable; window step is the bottleneck for ML-ready bundles
**Component:** components/dataset
**Discovered:** 2026-08-02 during can-ml pilot on 751AC1C3 (job `ddb69a8d`)

## Symptom

`dataset_submit_generation` with `recipe://local/can-window@1` and a 6.05 GB synthesized JSONL (7.7M records) ran for 9+ hours with no progress:
- Log: only 3 lines (the startup banner and a dependency warning)
- Checkpoint directory: empty (no stage output written)
- RSS: dropped from 15 GB to 2.7 GB over time (likely GC)
- Status: `running` until killed

The job was supposed to window the synthesized records into 5-second trainable samples. 9 hours of CPU + 15 GB peak RAM produced nothing.

## Root cause (unconfirmed, needs investigation)

Likely one of:
1. `can_window.adapter` is single-threaded over all CAN IDs and does a per-record nested loop. With 7.7M records it may be O(N²) in practice.
2. The window stage reads the entire 6 GB input into memory, then sorts by timestamp per CAN ID. 7.7M records × 32 bytes per record ≈ 250 MB compressed but pandas-style windowing can balloon to 5-10x.
3. The synthesized records have a non-monotonic or empty `timestamp_ns` (we saw `synthetic_lineage.donor_timestamp_ns` is set, but the top-level `timestamp_ns` is the original MF4 timestamp). If the window stage expects monotonic per-CAN timestamps, the SDV samples (which interpolate between source records) may violate the invariant.

The job was killed (PID 72408) at 09:06:11 elapsed time.

## Reproduction

```python
dataset_submit_generation(
    recipe_uri="recipe://local/can-window@1",
    recipe_digest="0c409a5a5c3e8a5f34cd4a9ef862596de432a22217731400bf34f3131888079b",
    input_artifact_uris=["file:///.../dataset-df40941e6f95d98b....jsonl"],  # 6.05 GB
    input_artifact_digests=["df40941e6f95d98b..."],
    context_snapshot_uri="file:///.../context-db2248bb....json",  # window_size_ms, step_size_ms
    # ...
)
# Status remains "running" indefinitely. No checkpoint output. No log progress.
```

## Fix options

1. **Add progress logging** to the can_window adapter so users can see what it's doing (current log is silent).
2. **Stream the input** instead of loading it all into memory.
3. **Verify window stage's invariants** for the SDV output (monotonic timestamps per CAN ID, etc.).
4. **Add a timeout** to the worker subprocess so it can't hang for 9 hours.
5. **Add a memory-and-time profile test** that runs the window stage on 100K records and asserts it completes in <5 min.

## Workaround (until fixed)

Two options:
- **Skip the window stage for now.** Train models directly on the 6.5 GB synthesized JSONL. Slower (no temporal structure) but unblocks the ML work.
- **Pre-sample the synthesized output** to ~1M records, then window that. The 1M subset should window in seconds-to-minutes.

The synthesized bundle is at:
`/Users/danielrodrigo/Workspace/python-factory/.dataset_store/artifacts/5aa3734d-290b-409c-b46c-101f4fac72fa/dataset-df40941e6f95d98b87a4281654562f1536e01e0ed020858d30ca0c8c79eca95e.jsonl`

(6.05 GB, 7,737,510 records, 9.5% failure rate, all 8 failure modes)

## Severity argument

P2, not P1: the synthesize step (which is the user's actual goal — "make a huge solid dataset with failures") works. The window step is a downstream optimization for ML training. Users can train on the JSONL directly, or pre-sample. The blocking issue is the silent failure of the upper pipeline (Beads 1-5); the window hang is a follow-on.
