"""Human-gameplay-driven ML trainer.

Reads real player session logs from data/logs/ and trains (or retrains)
a LogisticRegression success-probability model on that data.

Design decisions
----------------
* Training data comes only from *adaptive* sessions (controller == 'adaptive'),
  ensuring we learn from real human performance, not scripted bots.
* Features are the same 10-value vector defined in ml.features so the model
  is directly usable by the inference path in dda_controller.py.
* Minimum required samples: MIN_SAMPLES_TO_TRAIN (default 80).  Below that the
  function returns None and callers fall back to the rule-based controller.
* Train/test split is done at the *session* level (group-aware) to prevent
  cross-contamination between temporally correlated events.
* The trained bundle is saved to data/human_model.pkl with the same
  {model, feature_names, trained_at, n_samples} schema.
* Call retrain_if_needed() from the game loop; it debounces via a timestamp
  file so it never retrains more than once per game session.
"""

import csv
import os
import time
import warnings
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOG_DIR         = "data/logs"
HUMAN_MODEL_PATH = "data/human_model.pkl"
MIN_SAMPLES_TO_TRAIN = 80      # rows with valid labels (not just successes)
MIN_POSITIVE_RATE    = 0.05    # need at least 5 % success (else data is trivial)
MAX_POSITIVE_RATE    = 0.95    # need at least 5 % failure
RETRAIN_COOLDOWN_S   = 300     # seconds: don't retrain more than once per 5 min
_LAST_RETRAIN_FILE   = "data/.last_human_retrain"

FEATURE_NAMES = [
    "gap_size",
    "bird_y_norm",
    "bird_vel_norm",
    "consecutive_successes",
    "consecutive_failures",
    "success_rate_last3",
    "success_rate_last5",
    "success_rate_last10",
    "trend_success_rate",
    "pipes_since_start_norm",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_human_rows(log_dir: str = LOG_DIR, controller_filter: str = "adaptive"):
    """Read all session CSVs produced with the given controller name.

    Returns a list of dicts (raw CSV rows) with consistent numeric fields.
    Rows with obviously corrupt values (epoch-scale time, missing gap) are
    skipped with a warning counter printed at the end.
    """
    rows = []
    skipped = 0
    log_path = Path(log_dir)
    if not log_path.exists():
        return rows

    for csv_file in sorted(log_path.glob(f"session_*_{controller_filter}.csv")):
        try:
            with open(csv_file, newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    try:
                        gap = float(row["gap_size"])
                        if not (50 <= gap <= 300):          # sanity: reasonable gap
                            skipped += 1
                            continue
                        surv = float(row.get("survival_time", 0))
                        if surv > 3600:                     # epoch-scale timestamp bug
                            skipped += 1
                            continue
                        rows.append(row)
                    except (ValueError, KeyError):
                        skipped += 1
        except Exception:
            pass

    if skipped:
        print(f"[HumanTrainer] Skipped {skipped} malformed rows")
    return rows


def _rows_to_X_y(rows):
    """Convert raw CSV rows to (X, y, session_ids) for model training.

    Uses the same feature definitions as ml/features.py but reads directly
    from the logged values so no re-computation of history is needed.
    """
    X, y, sessions = [], [], []
    for row in rows:
        try:
            gap      = float(row["gap_size"])
            bird_y   = float(row.get("bird_y_at_pass", 320))
            bird_vel = float(row.get("bird_vel_at_pass", 0))
            cons_s   = float(row.get("consecutive_successes_before", 0))
            cons_f   = float(row.get("consecutive_failures_before", 0))
            rate3    = float(row.get("success_rate_last3", 0))
            rate5    = float(row.get("success_rate_last5", 0))
            pipes    = float(row.get("total_pipes_passed", 0))
            success  = int(row["success"])
        except (ValueError, KeyError):
            continue

        # Derive rate10 / trend from rate3 and rate5 (best we can from logged data)
        rate10 = rate5                        # proxy — same bias as training data
        trend  = rate3 - rate5

        feats = [
            gap / 240.0,
            bird_y / 640.0,
            max(-1.0, min(1.0, bird_vel / 10.0)),
            min(cons_s / 10.0, 1.0),
            min(cons_f / 10.0, 1.0),
            rate3,
            rate5,
            rate10,
            trend,
            min(pipes / 20.0, 1.0),
        ]

        X.append(feats)
        y.append(success)
        sessions.append(row.get("session_id", "unknown"))

    return np.array(X, dtype=float), np.array(y, dtype=int), sessions


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_from_human_logs(
    log_dir: str = LOG_DIR,
    model_path: str = HUMAN_MODEL_PATH,
    verbose: bool = True,
) -> Optional[dict]:
    """Load human logs, train a model, save to model_path.

    Returns the saved bundle dict {model, feature_names, trained_at,
    n_samples} or None if insufficient data.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GroupShuffleSplit
    from sklearn.metrics import roc_auc_score
    import joblib

    rows = _load_human_rows(log_dir)
    if not rows:
        if verbose:
            print("[HumanTrainer] No human session logs found.")
        return None

    X, y, sessions = _rows_to_X_y(rows)

    if len(y) < MIN_SAMPLES_TO_TRAIN:
        if verbose:
            print(f"[HumanTrainer] Only {len(y)} samples (need {MIN_SAMPLES_TO_TRAIN}). "
                  "Using fallback controller.")
        return None

    pos_rate = y.mean()
    if not (MIN_POSITIVE_RATE <= pos_rate <= MAX_POSITIVE_RATE):
        if verbose:
            print(f"[HumanTrainer] Degenerate labels (positive rate={pos_rate:.2f}). "
                  "Need more varied gameplay. Using fallback.")
        return None

    # Session-level train/test split (avoids within-session leakage)
    unique_sessions = list(set(sessions))
    if len(unique_sessions) >= 4:
        gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
        train_idx, test_idx = next(gss.split(X, y, groups=sessions))
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]
    else:
        # Too few sessions for held-out split; train on all, skip eval metrics
        X_train, y_train = X, y
        X_test, y_test = None, None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = LogisticRegression(
            max_iter=2000, class_weight="balanced", random_state=42, C=1.0
        )
        model.fit(X_train, y_train)

    auc_str = "n/a (too few sessions for split)"
    if X_test is not None and len(np.unique(y_test)) > 1:
        try:
            auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
            auc_str = f"{auc:.3f}"
        except Exception:
            pass

    bundle = {
        "model": model,
        "feature_names": FEATURE_NAMES,
        "trained_at": time.time(),
        "n_samples": int(len(y)),
        "n_sessions": len(unique_sessions),
        "positive_rate": float(pos_rate),
        "test_auc": auc_str,
    }

    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    joblib.dump(bundle, model_path)

    if verbose:
        print(f"[HumanTrainer] Trained on {len(y)} samples across "
              f"{len(unique_sessions)} sessions.  Test AUC: {auc_str}")
        print(f"[HumanTrainer] Model saved → {model_path}")

    return bundle


# ---------------------------------------------------------------------------
# Debounced retrain helper (called from game loop post-session)
# ---------------------------------------------------------------------------

def retrain_if_needed(
    log_dir: str = LOG_DIR,
    model_path: str = HUMAN_MODEL_PATH,
    verbose: bool = True,
) -> Optional[dict]:
    """Retrain only if the cooldown has elapsed since the last training run.

    Returns the loaded/trained bundle or None.
    """
    # Check cooldown
    last_ts = 0.0
    try:
        with open(_LAST_RETRAIN_FILE) as fh:
            last_ts = float(fh.read().strip())
    except Exception:
        pass

    now = time.time()
    if now - last_ts < RETRAIN_COOLDOWN_S:
        if verbose:
            remaining = int(RETRAIN_COOLDOWN_S - (now - last_ts))
            print(f"[HumanTrainer] Retrain skipped (cooldown: {remaining}s remaining)")
        # Still return existing model if it exists
        return _load_model_bundle(model_path)

    bundle = train_from_human_logs(log_dir=log_dir, model_path=model_path, verbose=verbose)

    # Update timestamp regardless of success so we don't hammer disk on failure
    try:
        os.makedirs(os.path.dirname(_LAST_RETRAIN_FILE) or ".", exist_ok=True)
        with open(_LAST_RETRAIN_FILE, "w") as fh:
            fh.write(str(now))
    except Exception:
        pass

    return bundle


def _load_model_bundle(model_path: str = HUMAN_MODEL_PATH) -> Optional[dict]:
    """Safely load an existing model bundle; return None on any error."""
    if not os.path.exists(model_path):
        return None
    try:
        import joblib
        bundle = joblib.load(model_path)
        if isinstance(bundle, dict) and "model" in bundle:
            return bundle
        return None
    except Exception as e:
        print(f"[HumanTrainer] Could not load model ({e})")
        return None


def count_human_samples(log_dir: str = LOG_DIR) -> int:
    """Return number of valid human-play rows available for training."""
    rows = _load_human_rows(log_dir)
    _, y, _ = _rows_to_X_y(rows)
    return len(y)
