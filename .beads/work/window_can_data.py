"""Fast windowing using two-pointer sliding window."""
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
import time

SRC = Path('/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M.jsonl')
OUT_DIR = Path('/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-windowed')
OUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_MS = 1000
STEP_MS = 500
MIN_FRAMES = 3
TOP_N_CAN = 10
MAX_WINDOWS_PER_CAN = 5000

t0 = time.time()

# Pass 1: count CAN IDs (lightweight)
print('counting...')
counts = Counter()
n_total = 0
with open(SRC) as f:
    for line in f:
        n_total += 1
        rec = json.loads(line)
        if rec.get('decoded_signals'):
            counts[rec.get('arbitration_id')] += 1
print(f'counted {n_total} in {time.time()-t0:.1f}s')

top_cans = [aid for aid, _ in counts.most_common(TOP_N_CAN)]
print(f'top: {[(a, counts[a]) for a in top_cans]}')

# Pass 2: collect top-CAN records (timestamps + signals only)
print('collecting...')
records_by_can = defaultdict(list)
with open(SRC) as f:
    for line in f:
        rec = json.loads(line)
        aid = rec.get('arbitration_id')
        if aid not in top_cans:
            continue
        sigs = rec.get('decoded_signals')
        if not sigs:
            continue
        records_by_can[aid].append((rec.get('timestamp_ns', 0), sigs, rec.get('is_failure', 0)))
print(f'collected {sum(len(v) for v in records_by_can.values())} in {time.time()-t0:.1f}s')

# Build feature columns
first = next(iter(records_by_can.values()))[0][1]
feature_columns = sorted(first.keys())
n_features = len(feature_columns)
print(f'{n_features} features')

# Window each CAN with two-pointer
results = {}
for aid in top_cans:
    recs = records_by_can[aid]
    if len(recs) < MIN_FRAMES:
        continue
    recs.sort(key=lambda r: r[0])
    timestamps = np.array([r[0] for r in recs], dtype=np.int64)
    failures = np.array([r[2] for r in recs], dtype=np.int8)
    matrix = np.zeros((len(recs), n_features), dtype=np.float32)
    for i, (_, sigs, _) in enumerate(recs):
        for j, fname in enumerate(feature_columns):
            v = sigs.get(fname)
            if v is not None:
                matrix[i, j] = float(v)
    # Forward-fill: replace 0s with the last non-zero value (per column)
    for j in range(n_features):
        col = matrix[:, j]
        last = 0.0
        for i in range(len(col)):
            if col[i] != 0.0:
                last = col[i]
            else:
                col[i] = last
    # Two-pointer window
    start_ns = int(timestamps[0])
    end_ns = int(timestamps[-1])
    windows = []
    y_win = []
    win_starts = []
    t = start_ns
    while t + WINDOW_MS * 1_000_000 <= end_ns and len(windows) < MAX_WINDOWS_PER_CAN:
        lo = int(np.searchsorted(timestamps, t, side='left'))
        hi = int(np.searchsorted(timestamps, t + WINDOW_MS * 1_000_000, side='left'))
        if hi - lo >= MIN_FRAMES:
            win = matrix[lo:hi]
            label = int(failures[lo:hi].max())
            windows.append(win)
            y_win.append(label)
            win_starts.append(t)
        t += STEP_MS * 1_000_000
    if not windows:
        continue
    lengths = np.array([w.shape[0] for w in windows])
    L = int(np.median(lengths))
    X = np.zeros((len(windows), L, n_features), dtype=np.float32)
    for i, w in enumerate(windows):
        X[i, :min(w.shape[0], L)] = w[:L]
    aid_clean = aid.replace('0x', '')
    out_path = OUT_DIR / f'can_{aid_clean}'
    out_path.mkdir(parents=True, exist_ok=True)
    np.save(out_path / 'X_3d.npy', X)
    np.save(out_path / 'X_flat.npy', X.reshape(len(X), -1))
    np.save(out_path / 'y.npy', np.array(y_win, dtype=np.int8))
    results[aid] = {
        'n_windows': len(windows),
        'window_len': int(L),
        'n_failures': int(sum(y_win)),
        'failure_rate': float(sum(y_win)) / len(y_win),
        'X_3d_path': str(out_path / 'X_3d.npy'),
        'y_path': str(out_path / 'y.npy'),
    }
    print(f'  {aid}: {len(windows)} windows ({sum(y_win)} failures, {100*sum(y_win)/len(y_win):.1f}%), shape={X.shape}')

(OUT_DIR / 'feature_columns.txt').write_text('\n'.join(feature_columns) + '\n')
(OUT_DIR / 'metadata.json').write_text(json.dumps({
    'window_size_ms': WINDOW_MS, 'step_size_ms': STEP_MS,
    'top_n_can': TOP_N_CAN, 'max_windows_per_can': MAX_WINDOWS_PER_CAN,
    'n_features': n_features, 'features': feature_columns,
    'per_can_results': results,
    'windowing_time_seconds': time.time() - t0,
}, indent=2))
print(f'\ntotal: {sum(r["n_windows"] for r in results.values())} windows in {time.time()-t0:.1f}s')
print(f'written to {OUT_DIR}/')
