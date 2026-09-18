# Bug: companion-x MCP server crashes silently during ml_train_timeseries

**Severity:** P0 — the documented ML training tool kills the MCP server process on first call, leaving opencode unable to recover without a full session restart
**Component:** factory.mcp_server.core (companion-x); consumer is components/machine_learning
**Discovered:** 2026-08-02 during can-ml pilot on 751AC1C3, real-data validation session
**Status:** REPRODUCED — crash confirmed twice today on the data-bearing machine, with all prereqs in place (env vars, healthy bricks, valid URIs, 30s-old fresh MCP process)

## Symptom

A clean opencode session is started with the four model-root env vars and `ML_ENABLE_AUTHORING_TOOLS=1` configured in `~/.config/opencode/opencode.jsonc`. The companion-x MCP process boots, all 40 bricks report healthy, env vars are confirmed on the process.

Then `ml_train_timeseries` is called via `companion-x_call_brick_tool` with a valid `lightgbm` invocation (see Reproduction). The opencode client receives:

```
MCP error -32000: Connection closed
```

The opencode log shows: `WARN MCP connection closed server=companion-x`.

No error payload from the training tool itself. No partial artifact. The companion-x process is gone — `pgrep -f 'factory.mcp_server.core'` returns nothing. The configured model-root directory (`ML_LIGHTGBM_MODEL_ROOT`, etc.) is empty — the crash happens before any artifact is written.

macOS generates a `python3.13-*.ips` crash report in `~/Library/Logs/DiagnosticReports/` at the same second, confirming a hard process termination (signal-based, not a clean exit) in the `factory.mcp_server.core` python child. The crash is also visible as a `.dylib` snapshot in `/var/folders/.../T/`.

The MCP server is a stdio child of opencode. There is no in-session command to re-spawn it. `/mcp` disable/re-enable does not re-read the config and does not reconnect to a manually-started process. The only recovery is to kill the session and start a new one.

## Why this is distinct from existing Beads

- **Not `python-factory-ml-import-bug.md` (Bug 7).** That import error is gone — `TimeSeriesModelConfig` resolves cleanly. The call gets past the import step. The crash happens later, in the training execution.
- **Not `python-factory-can-snap-bug.md` (Bug 1).** That bug is in the dataset brick's `can_ingest` path. The crash here is triggered from the machine_learning brick with valid `X_uri`/`y_uri` file:// paths to pre-materialized `.npy` files in `.dataset_store/pilot-1M-percan/can_25/`. The dataset brick is not invoked.
- **Not a code bug in the opencode config.** All five required env vars are present on the running process, confirmed by `ps eww -p $(pgrep -f 'factory.mcp_server.core' | head -1)`. The process is a fresh 30s-old boot. There is no configuration oversight on the caller side.

## Reproduction

### Prereqs (already met on the data-bearing machine)

- `~/.config/opencode/opencode.jsonc` includes the four model-root env vars and `ML_ENABLE_AUTHORING_TOOLS=1` under `companion-x.environment`.
- The four target directories exist: `.dataset_store/lightgbm_models/`, `.dataset_store/torch_models/`, `.dataset_store/lnn_models/`, `.dataset_store/patchtst_models/`.
- Per-CAN training arrays materialized at `.dataset_store/pilot-1M-percan/can_25/X.npy` (20K × 12) and `.../y.npy`.

### Procedure

1. Start a clean opencode session (so the config is read fresh).
2. In the new session, verify MCP state:
   - `companion-x_health_check` returns `healthy: 40/40 bricks`.
   - `ps eww -p $(pgrep -f 'factory.mcp_server.core' | head -1) | tr ' ' '\n' | grep -E 'ML_LIGHTGBM|TORCH_TS_MODEL|LNN_TS_MODEL|PATCHTST|ML_ENABLE_AUTHORING'` returns 5 lines.
3. Call `ml_train_timeseries` via `companion-x_call_brick_tool` against the `machine_learning` brick:
   ```
   model_type: lightgbm
   X_uri: file:///Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-percan/can_25/X.npy
   y_uri: file:///Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-percan/can_25/y.npy
   config: {window_size: 12, stride: 1, epochs: 5, batch_size: 64}
   experiment_name: pilot-1M-can25-test7
   ```
4. Observe: `MCP error -32000: Connection closed`. The opencode log shows the companion-x disconnect. `pgrep` returns nothing. A fresh `.ips` crash report appears in `~/Library/Logs/DiagnosticReports/`.

### Reproduction history

- 2026-08-02 ~11:02–11:07 CDT: six `python3.13-2026-08-02-110*.ips` crash reports generated during the user's first training attempts in the previous session (after the env-var config landed).
- 2026-08-02 15:04:24 CDT: one `python3.13-2026-08-02-150404.ips` crash report generated during this session's first `ml_train_timeseries` call, after a verified-clean MCP restart (30s-old process, 5/5 env vars present, 40/40 bricks healthy, valid `X_uri`/`y_uri`, valid config).

The crash is reliably reproducible from the first training call against this dataset.

## Root cause — investigation needed

The Bead author has not opened the `.ips` file (owner-restricted to `_analyticsusers` user, mode `rw-------`). The macOS crash report should be the first thing an engineer reads. Likely candidates, in order of suspicion:

1. **Uncaught exception in a thread spawned by the LightGBM training adapter.** LightGBM's `Booster` save path or a numpy dtype mismatch (the can_25 arrays are 20K × 12 float32) could throw something the MCP tool wrapper does not catch, and a daemon thread tear-down could signal the parent. Look for `SystemExit`/`KeyboardInterrupt`/`Aborted` in the crash report.
2. **Model-persistence step in the training adapter.** The call enters the training step with `ML_LIGHTGBM_MODEL_ROOT` set, but the adapter may try to write to a path that is not yet created, or use a permissions model that requires a different env var. The empty `.dataset_store/lightgbm_models/` after the crash suggests the crash happens before persistence — but the first write attempt could itself be the trigger (e.g. trying to mkdir and the parent is not writable).
3. **A `mlflow`/`wandb`/telemetry callback crashing on import.** Some model families auto-import tracking libs. Look for `import mlflow` / `import wandb` traces in the crash report.
4. **A signal handler in the MCP server framework mishandling a `SIGPIPE`/`SIGSEGV` from a child thread.** Less likely but worth checking.

The opencode client side returns a generic `MCP error -32000: Connection closed` because the server's stdio pipe went EOF — the server process is gone. The crash report on disk is the only forensic record of what happened inside the call.

## Workaround (until fixed)

None that does not require a session restart. The user has been working around the crash by:

1. Killing the opencode session entirely.
2. Starting a fresh opencode session.
3. Verifying env vars on the new MCP process.
4. Re-attempting the same call.

The crash reproduces in the new session at the first training call, so this is not a true workaround — it just buys one training attempt per session start. After one crash, the session is dead and the user has to start over.

## Severity argument

P0 because the can-ml pilot cannot produce any training result via the documented MCP path on the data-bearing machine. The `ml_train_timeseries` tool is the only documented way to train the 3 model families end-to-end from the dataset materialization onward. The pilot goal (≥10% failure rate with learnable signal patterns, all 3 model families trained) cannot advance past the first training call without a fix.

## Files / log locations

- `~/Library/Logs/DiagnosticReports/python3.13-2026-08-02-150404.ips` — most recent crash report (94 KB, owner `_analyticsusers`, needs elevated read).
- `~/Library/Logs/DiagnosticReports/python3.13-2026-08-02-110*.ips` — six earlier crash reports from the same day, same root cause.
- `/tmp/companion-x-manual.log` — log from a user's earlier manual `uv run python -m factory.mcp_server.core` start attempt (66 KB, readable).
- `/var/folders/gm/.../T/.5bfaf7fdfedaeef9-00000000.dylib` and similar — process-state snapshots generated at crash time.
- `~/.config/opencode/opencode.jsonc` — config that needs to be re-read on every opencode session start (no in-session reload).
- `.dataset_store/lightgbm_models/` — empty after the crash (crash is pre-persistence).

## Related

- GitHub issue `bannff/python-factory#702` — third comment ("Update — fresh opencode session, env vars landed, but MCP server crashed on first training call") first described this failure mode.
- PR `bannff/python-factory#703` (commit `799457a4`) — fixed the import error (Bug 7) but did not address this crash; the import fix is upstream of the crash and confirmed working.
- `python-factory-ml-import-bug.md` — the import error that this crash sits downstream of. That fix is in place; the crash is in the next code path.
