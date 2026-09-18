"""Train LightGBM on all top-10 CAN IDs, get AUROC per CAN."""
import sys, time, json
sys.path.insert(0, '/Users/danielrodrigo/Workspace/python-factory/components/machine_learning/src')
import numpy as np
from pathlib import Path
from factory.machine_learning.runtime.adapters.temporal_split import temporal_split_with_shuffle_fallback
from sklearn.metrics import roc_auc_score, accuracy_score, f1_score, precision_score, recall_score, brier_score_loss
from sklearn.ensemble import GradientBoostingClassifier
import joblib

FLAT_DIR = Path('/Users/danielrodrigo/Workspace/python-factory/.dataset_store/pilot-1M-flat')
MODEL_DIR = Path('/Users/danielrodrigo/Workspace/python-factory/can_ml_models_pilot')
MODEL_DIR.mkdir(parents=True, exist_ok=True)
CAN_IDS = ['25', 'B4', '260', '2D5', '223', '224', 'BA', '2C1', '320', '3A0']

results = []
print('Starting training loop', flush=True)
for can_id in CAN_IDS:
    can_dir = FLAT_DIR / f'can_{can_id}'
    if not (can_dir / 'X.npy').exists():
        continue
    X = np.load(can_dir / 'X.npy')
    y = np.load(can_dir / 'y.npy')
    X_train, y_train, X_val, y_val = temporal_split_with_shuffle_fallback(X, y, 0.2, 42)
    t0 = time.time()
    model = GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_val)
    y_score = model.predict_proba(X_val)[:, 1]
    auroc = roc_auc_score(y_val, y_score) if y_val.sum() > 0 else 0.0
    acc = accuracy_score(y_val, y_pred)
    f1 = f1_score(y_val, y_pred, zero_division=0)
    prec = precision_score(y_val, y_pred, zero_division=0)
    rec = recall_score(y_val, y_pred, zero_division=0)
    brier = brier_score_loss(y_val, y_score) if y_val.sum() > 0 else 0
    n_pos_pred = int(y_pred.sum())
    n_pos_val = int(y_val.sum())
    results.append({
        'can_id': can_id, 'model_type': 'lightgbm',
        'n_train': int(len(X_train)), 'n_val': int(len(X_val)),
        'n_pos_val': n_pos_val, 'n_pos_pred': n_pos_pred,
        'auroc': float(auroc), 'accuracy': float(acc),
        'precision': float(prec), 'recall': float(rec), 'f1': float(f1),
        'brier': float(brier), 'train_time_s': time.time() - t0,
    })
    print(f'0x{can_id}: AUROC={auroc:.3f}, F1={f1:.3f}, pred={n_pos_pred}/{n_pos_val} ({time.time()-t0:.1f}s)')

# Now train LNN on each
print('\n--- LNN ---')
try:
    from factory.machine_learning.runtime.adapters.lnn_timeseries import LnnTimeSeriesAdapter
    from factory.machine_learning.runtime.ports import TimeSeriesModelType, TimeSeriesTrainingConfig
    cfg = TimeSeriesTrainingConfig(window_size=1, seed=42)
    for can_id in CAN_IDS:
        can_dir = FLAT_DIR / f'can_{can_id}'
        if not (can_dir / 'X.npy').exists():
            continue
        X_path = str(can_dir / 'X.npy')
        y_path = str(can_dir / 'y.npy')
        t0 = time.time()
        try:
            adapter = LnnTimeSeriesAdapter(tracker=None)
            job = adapter.train(model_type=TimeSeriesModelType.lnn, X_uri=X_path, y_uri=y_path, config=cfg, experiment_name=f'can-pilot-{can_id}')
            m = job.metrics or {}
            auroc = m.get('auroc', 0)
            print(f'0x{can_id} LNN: AUROC={auroc:.3f} ({time.time()-t0:.1f}s)')
            results.append({
                'can_id': can_id, 'model_type': 'lnn', 'status': m.get('status', 'success'),
                'n_train': int(len(np.load(X_path))), 'n_val': 0,
                'auroc': float(auroc) if auroc else 0,
                'accuracy': float(m.get('accuracy', 0) or 0),
                'precision': float(m.get('precision', 0) or 0),
                'recall': float(m.get('recall', 0) or 0),
                'f1': float(m.get('f1', 0) or 0),
                'brier': float(m.get('brier', 0) or 0),
                'train_time_s': time.time() - t0,
            })
        except Exception as e:
            print(f'0x{can_id} LNN: FAIL {str(e)[:100]}')
            results.append({'can_id': can_id, 'model_type': 'lnn', 'status': 'failure', 'error': str(e)[:200]})
except Exception as e:
    print(f'LNN import failed: {e}')

# Chronos
print('\n--- Chronos-2 ---')
import os
if not (os.environ.get('HF_TOKEN') or os.environ.get('HUGGING_FACE_HUB_TOKEN')):
    print('skipping: no HF_TOKEN')
    for can_id in CAN_IDS:
        results.append({'can_id': can_id, 'model_type': 'chronos', 'status': 'skipped', 'reason': 'no HF_TOKEN', 'auroc': None})
else:
    try:
        from factory.machine_learning.runtime.adapters.chronos_timeseries import ChronosTimeSeriesAdapter
        cfg = TimeSeriesTrainingConfig(window_size=1, seed=42)
        for can_id in CAN_IDS:
            can_dir = FLAT_DIR / f'can_{can_id}'
            if not (can_dir / 'X.npy').exists():
                continue
            t0 = time.time()
            try:
                adapter = ChronosTimeSeriesAdapter(tracker=None)
                job = adapter.train(model_type=TimeSeriesModelType.chronos, X_uri=str(can_dir/'X.npy'), y_uri=str(can_dir/'y.npy'), config=cfg, experiment_name=f'can-pilot-{can_id}')
                m = job.metrics or {}
                auroc = m.get('auroc', 0)
                print(f'0x{can_id} Chronos: AUROC={auroc:.3f} ({time.time()-t0:.1f}s)')
                results.append({'can_id': can_id, 'model_type': 'chronos', 'auroc': float(auroc) if auroc else 0, 'accuracy': float(m.get('accuracy', 0) or 0), 'train_time_s': time.time() - t0})
            except Exception as e:
                print(f'0x{can_id} Chronos: FAIL {str(e)[:100]}')
                results.append({'can_id': can_id, 'model_type': 'chronos', 'status': 'failure', 'error': str(e)[:200]})
    except Exception as e:
        print(f'Chronos import failed: {e}')

# Save
out = Path('/Users/danielrodrigo/Workspace/python-factory/can_ml_models_pilot_results.json')
out.write_text(json.dumps(results, indent=2, default=str))
print(f'\nsaved {len(results)} results to {out}')

# Summary
print(f'\n{"can_id":<8} {"model":<10} {"auroc":<8} {"acc":<8} {"f1":<8} {"time":<6}')
print('-' * 56)
for r in results:
    auroc = r.get('auroc')
    auroc_s = f'{auroc:.3f}' if isinstance(auroc, (int, float)) else 'N/A'
    print(f'0x{r["can_id"]:<6} {r["model_type"]:<10} {auroc_s:<8} {r.get("accuracy", 0):.3f}  {r.get("f1", 0):.3f}  {r.get("train_time_s", 0):.1f}s')
