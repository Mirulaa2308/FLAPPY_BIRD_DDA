"""Generate training data using scripted bots, then train and save an ML model.

Run from the project root:
    python -m ml.train
"""
import os
import sys
import time
import csv
import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, classification_report

# Allow running as script
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from game.game import FlappyGame
from controllers.fixed import FixedController
from ml.bots import BotLowSkill, BotMediumSkill, BotHighSkill
from ml.features import extract_features, FEATURE_NAMES


GAP_VALUES = [90, 110, 130, 150, 170, 190, 210, 240]
EPISODES_PER_BOT_PER_GAP = 40
DATASET_PATH = "data/training_data.csv"
MODEL_PATH = "data/model.pkl"


def collect_dataset():
    print("Collecting training data via scripted bots...")
    rows = []

    bots = [
        BotHighSkill(seed=3),
    ]

    for gap in GAP_VALUES:
        for bot in bots:
            print(f"  Bot={bot.name:6s}  gap={gap}", end="", flush=True)
            successes = 0
            total_pipes = 0

            for ep in range(EPISODES_PER_BOT_PER_GAP):
                controller = FixedController(gap=gap)
                game = FlappyGame(controller, session_id=f"train_{bot.name}_{gap}",
                                  render=False, headless=True)
                # Inline training loop instead of run_episode, so we can capture
                # the feature vector at each pipe event.
                game.reset_episode()
                game.controller.reset()
                game.success_history = []
                game.current_gap = controller.current_gap

                # We must run frames manually and hook the logger.
                # Simplest approach: replace game.logger.log with a capturing wrapper
                captured = []

                original_log = game.logger.log

                def capturing_log(record, captured=captured, game=game):
                    feats = extract_features(record, game.success_history + [record["success"]])
                    rows.append({
                        "features": feats,
                        "success": record["success"],
                        "gap": record["gap_size"],
                        "bot": bot.name,
                    })
                    original_log(record)

                game.logger.log = capturing_log

                max_frames = 1200
                for _ in range(max_frames):
                    jump = bot(game.bird, game.pipes)
                    done = game.update(jump=jump)
                    if done:
                        break

                total_pipes += game.score
                successes += game.score

            print(f"  -> avg pipes: {successes/max(1, EPISODES_PER_BOT_PER_GAP):.1f}")

    print(f"\nTotal training samples: {len(rows)}")

    os.makedirs(os.path.dirname(DATASET_PATH), exist_ok=True)
    with open(DATASET_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(FEATURE_NAMES + ["success", "gap", "bot"])
        for r in rows:
            writer.writerow(r["features"] + [r["success"], r["gap"], r["bot"]])

    print(f"Saved dataset to {DATASET_PATH}")
    return rows


def train_model(rows):
    print("\nTraining logistic regression model...")
    X = np.array([r["features"] for r in rows])
    y = np.array([r["success"] for r in rows])

    print(f"  X shape: {X.shape}, positive rate: {y.mean():.3f}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = LogisticRegression(max_iter=1000, class_weight="balanced")
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    print(f"  Test accuracy: {accuracy_score(y_test, y_pred):.4f}")
    print(f"  Test ROC-AUC:  {roc_auc_score(y_test, y_prob):.4f}")
    print("\n  Classification report:")
    print(classification_report(y_test, y_pred, digits=3))

    print("\n  Feature coefficients (positive = predicts success):")
    for name, coef in sorted(zip(FEATURE_NAMES, model.coef_[0]),
                              key=lambda x: -abs(x[1])):
        print(f"    {name:32s} {coef:+.4f}")

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump({"model": model, "feature_names": FEATURE_NAMES}, MODEL_PATH)
    print(f"\nSaved model to {MODEL_PATH}")
    return model


if __name__ == "__main__":
    start = time.time()
    rows = collect_dataset()
    train_model(rows)
    print(f"\nDone in {time.time() - start:.1f}s")