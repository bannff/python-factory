"""Per-CAN-ID training with per-CAN signal columns.

Previous version used first record's signal names globally, which was
wrong because each CAN ID has its own signal set. This version
builds per-CAN X matrices using only that CAN's signals.
"""
import sys, time, json
sys.path.insert(0, '/Users/danielrodrigo/Workspace/python-factory/components/machine_learning/src')
import numpy as np
from pathlib import Path
from factory.machine_learning.runtime.adapters.temporal_split import temporal_split_with_shuffle_fallback
from sklearn.metrics import roc_auc_score, accuracy_score, f1_score, precision_score, recall_score, brier_score_loss
from sklearn.ensemble import GradientBoostingClassifier

SRC = Path('/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M.jsonl')
OUT_DIR = Path('/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-percan')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Pass 1: count CANs + signal sets
print('scanning...', flush=True)
records_by_can = {}
import collections
for can_id in ['25', 'B4', '260', '2D5', '223', '224', 'BA', '2C1', '320', '3A0']:
    records_by_can[can_id] = {'fails': [], 'norms': [], 'signals': None}

with open(SRC) as f:
    for line in f:
        rec = json.loads(line)
        aid = rec.get('arbitration_id', '').replace('0x', '')
        if aid not in records_by_can:
            continue
        sigs = rec.get('decoded_signals') or {}
        if not sigs:
            continue
        if rec.get('is_failure') == 1:
            records_by_can[aid]['fails'].append(sigs)
        else:
            records_by_can[aid]['norms'].append(sigs)

results = []
for can_id, data in records_by_can.items():
    fails = data['fails']
    norms = data['norms']
    if len(fails) < 50 or len(norms) < 50:
        continue
    # Per-CAN signal columns: union of fail+norm signal sets
    all_signals = set()
    for s in fails + norms:
        all_signals.update(s.keys())
    feature_columns = sorted(all_signals)
    n_features = len(feature_columns)

    def to_row(sigs):
        return [float(sigs.get(f, 0.0)) for f in feature_columns]

    MAX_PER_CAN = 20_000
    import random
    random.seed(42)
    random.shuffle(fails); random.shuffle(norms)
    n_pos = min(len(fails), MAX_PER_CAN // 5)  # balance 1:4
    n_neg = min(len(norms), n_pos * 4)
    sample = fails[:n_pos] + norms[:n_neg]
    random.shuffle(sample)
    X = np.array([to_row(s) for s in sample], dtype=np.float32)
    y = np.array([1]*n_pos + [0]*n_neg, dtype=np.int8)
    # Shuffle y to match sample shuffle
    y_perm = np.zeros(len(sample), dtype=np.int8)
    y_perm[:n_pos] = 1
    random.shuffle(list(zip(X, y_perm)))
    X = np.array([r[0] for r in zip(X, y_perm)], dtype=np.float32)
    y = np.array([r[1] for r in zip(X, y_perm)], dtype=np.int8)

    # Save
    can_dir = OUT_DIR / f'can_{can_id}'
    can_dir.mkdir(parents=True, exist_ok=True)
    np.save(can_dir / 'X.npy', X)
    np.save(can_dir / 'y.npy', y)
    (can_dir / 'feature_columns.txt').write_text('\n'.join(feature_columns) + '\n')

    # Train
    X_train, y_train, X_val, y_val = temporal_split_with_shuffle_fallback(X, y, 0.2, 42)
    t0 = time.time()
    model = GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)
    y_score = model.predict_proba(X_val)[:, 1]
    auroc = roc_auc_score(y_val, y_score) if y_val.sum() > 0 else 0
    acc = accuracy_score(y_val, y_pred)
    f1 = f1_score(y_val, y_pred, zero_division=0)
    prec = precision_score(y_val, y_pred, zero_division=0)
    rec = recall_score(y_val, y_pred, zero_division=0)
    brier = brier_score_loss(y_val, y_score) if y_val.sum() > 0 else 0
    results.append({
        'can_id': can_id, 'n_signals': n_features, 'n_samples': len(X),
        'n_train': len(X_train), 'n_val': len(X_val),
        'n_pos_val': int(y_val.sum()), 'n_pos_pred': int(y_pred.sum()),
        'auroc': float(auroc), 'accuracy': float(acc),
        'precision': float(prec), 'recall': float(rec), 'f1': float(f1),
        'brier': float(brier), 'train_time_s': time.time() - t0,
    })
    print(f'0x{can_id}: {n_features} signals, {len(X)} samples, AUROC={auroc:.3f}, F1={f1:.3f}, pred={int(y_pred.sum())}/{int(y_val.sum())}', flush=True)

(OUT_DIR / 'results.json').write_text(json.dumps(results, indent=2))
print(f'\n=== Summary: {len(results)} CANs trained ===')
print(f'{"can":<6} {"sig":<4} {"n":<6} {"AUROC":<7} {"acc":<7} {"F1":<7} {"prec":<7} {"rec":<7} {"brier":<7}')
for r in results:
    print(f'0x{r["can_id"]:<4} {r["n_signals"]:<4} {r["n_samples"]:<6} '
          f'{r["auroc"]:.3f}   {r["accuracy"]:.3f}   {r["f1"]:.3f}   '
          f'{r["precision"]:.3f}   {r["recall"]:.3f}   {r["brier"]:.3f}')
