"""Audit script – inspect ML data and model status."""
import os, csv, time
from pathlib import Path

log_dir = Path("data/logs")
adaptive_logs = list(log_dir.glob("session_*_adaptive.csv"))
print(f"Total adaptive session logs: {len(adaptive_logs)}")

# Count rows
total_rows = 0
for f in adaptive_logs:
    with open(f) as fh:
        rows = list(csv.DictReader(fh))
        total_rows += len(rows)
        
print(f"Total data rows across all adaptive logs: {total_rows}")

# Check human_model.pkl
hm_path = "data/human_model.pkl"
print(f"\nhuman_model.pkl exists: {os.path.exists(hm_path)}")
if os.path.exists(hm_path):
    print(f"human_model.pkl size: {os.path.getsize(hm_path)} bytes")
    try:
        import joblib
        bundle = joblib.load(hm_path)
        print(f"Bundle keys: {list(bundle.keys())}")
        print(f"n_samples: {bundle.get('n_samples')}")
        print(f"n_sessions: {bundle.get('n_sessions')}")
        print(f"test_auc: {bundle.get('test_auc')}")
        ts = bundle.get('trained_at')
        if ts:
            age_s = time.time() - ts
            print(f"trained_at: {ts} ({age_s/3600:.1f} hours ago)")
    except Exception as e:
        print(f"Error loading: {e}")

# Check last_human_retrain.txt
lrt = "data/last_human_retrain.txt"
if os.path.exists(lrt):
    with open(lrt) as f:
        ts_str = f.read().strip()
    try:
        ts = float(ts_str)
        age_s = time.time() - ts
        print(f"\nlast_human_retrain.txt: {ts_str} ({age_s/60:.1f} min ago)")
    except:
        print(f"\nlast_human_retrain.txt: {ts_str}")

# Count valid training samples via human_trainer
print("\n--- Running human_trainer count ---")
try:
    from ml.human_trainer import count_human_samples, MIN_SAMPLES_TO_TRAIN
    n = count_human_samples()
    print(f"Valid human samples: {n} / {MIN_SAMPLES_TO_TRAIN} needed to train")
except Exception as e:
    print(f"Error: {e}")

# Check a sample of recent gap values from logs to see if gaps change
print("\n--- Checking gap variation in recent adaptive logs ---")
recent = sorted(adaptive_logs)[-5:]
for f in recent:
    with open(f) as fh:
        rows = list(csv.DictReader(fh))
    gaps = [float(r["gap_size"]) for r in rows if r.get("gap_size")]
    if gaps:
        print(f"  {f.name}: {len(gaps)} rows, gap range [{min(gaps):.0f}, {max(gaps):.0f}]")
