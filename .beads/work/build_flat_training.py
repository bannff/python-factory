"""Per-CAN-ID flat training arrays for ml_train_timeseries.

The synthesized data has non-sequential timestamps (SDV preserves
donor timestamps, not a continuous timeline), so windowing doesn't
produce useful samples. Switch to per-frame classification:
each record's decoded_signals is one feature vector, label is
is_failure. Less powerful than windowed classification but
works with the data we have and matches the can_ml_train.py format.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np

SRC = Path('/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M.jsonl')
OUT_DIR = Path('/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-flat')
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOP_N_CAN = 10
MAX_PER_CAN = 50_000  # per-class cap to balance classes

print('counting...')
counts = Counter()
with open(SRC) as f:
    for line in f:
        rec = json.loads(line)
        if rec.get('decoded_signals'):
            counts[rec.get('arbitration_id')] += 1
top_cans = [aid for aid, _ in counts.most_common(TOP_N_CAN)]
print(f'top: {[(a, counts[a]) for a in top_cans]}')

# Collect per-CAN: failure and normal records separately
fails_by_can = defaultdict(list)
norms_by_can = defaultdict(list)
with open(SRC) as f:
    for line in f:
        rec = json.loads(line)
        aid = rec.get('arbitration_id')
        if aid not in top_cans:
            continue
        sigs = rec.get('decoded_signals')
        if not sigs:
            continue
        if rec.get('is_failure') == 1:
            fails_by_can[aid].append(sigs)
        else:
            norms_by_can[aid].append(sigs)

# Build feature columns from first record
first = next(iter(norms_by_can.values() or fails_by_can.values()))[0]
feature_columns = sorted(first.keys())
n_features = len(feature_columns)
print(f'{n_features} features: {feature_columns}')

# Balance and write
results = {}
for aid in top_cans:
    fails = fails_by_can[aid]
    norms = norms_by_can[aid]
    n_pos = min(len(fails), MAX_PER_CAN)
    n_neg = min(len(norms), n_pos * 4)  # 4:1 normal:fail ratio
    import random
    random.seed(42)
    random.shuffle(fails)
    random.shuffle(norms)
    sample = fails[:n_pos] + norms[:n_neg]
    random.shuffle(sample)
    X = np.zeros((len(sample), n_features), dtype=np.float32)
    y = np.zeros(len(sample), dtype=np.int8)
    y[:n_pos] = 1  # first n_pos are failures
    for i, sigs in enumerate(sample):
        for j, fname in enumerate(feature_columns):
            v = sigs.get(fname)
            if v is not None:
                X[i, j] = float(v)
    aid_clean = aid.replace('0x', '')
    out_path = OUT_DIR / f'can_{aid_clean}'
    out_path.mkdir(parents=True, exist_ok=True)
    np.save(out_path / 'X.npy', X)
    np.save(out_path / 'y.npy', y)
    results[aid] = {
        'n_samples': len(sample),
        'n_features': n_features,
        'n_failures': int(y.sum()),
        'n_normal': int(len(y) - y.sum()),
        'X_path': str(out_path / 'X.npy'),
        'y_path': str(out_path / 'y.npy'),
    }
    print(f'  {aid}: {len(sample)} samples ({int(y.sum())} fails), X={X.shape}')

(OUT_DIR / 'feature_columns.txt').write_text('\n'.join(feature_columns) + '\n')
(OUT_DIR / 'metadata.json').write_text(json.dumps({
    'top_n_can': TOP_N_CAN,
    'max_per_can': MAX_PER_CAN,
    'n_features': n_features,
    'features': feature_columns,
    'per_can_results': results,
}, indent=2))
print(f'written to {OUT_DIR}/')
