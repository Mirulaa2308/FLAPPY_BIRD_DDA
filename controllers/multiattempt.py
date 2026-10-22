"""Multi-attempt skill assessment for Flappy Bird DDA.

Difficulty never changes after a single attempt. Metrics from N consecutive
attempts (default 5) are collected; only then is the combined history analysed
(ML model if usable, otherwise a clearly-labelled rule-based fallback).
The new gap is stored as `pending_gap` and applied only in begin_attempt().
"""
import json
import os
import statistics
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional

# ----------------------------- configuration -----------------------------
@dataclass
class AssessmentConfig:
    attempts_per_cycle: int = 5        # configurable: use 3-5
    initial_gap: int = 165             # same default as the existing controllers
    min_gap: int = 120                 # hardest
    max_gap: int = 220                 # easiest
    step: int = 12                     # full adjustment (matches ReactiveController)
    small_step: int = 4                # used when performance is inconsistent
    target_success: float = 0.6        # same target as MLAdaptiveController
    deadband: float = 0.10             # +/- around target -> "unchanged"
    inconsistency_cv: float = 0.60     # coefficient of variation above this = inconsistent
    success_obstacles: int = 5         # an attempt "succeeds" if it passes >= this many pipes
    min_attempt_seconds: float = 2.0   # shorter aborted attempts are ignored
    history_path: str = "data/attempt_history.json"

    def __post_init__(self):
        self.attempts_per_cycle = max(3, min(5, int(self.attempts_per_cycle)))


# ----------------------------- per-attempt record -----------------------------
@dataclass
class AttemptRecord:
    score: int
    survival_time: float
    obstacles_passed: int
    collisions: int
    gap_used: int
    outcome: str = "collision"         # "collision" | "win" | "exit"
    success: bool = False
    timestamp: float = field(default_factory=time.time)


def _slope(ys: List[float]) -> float:
    """Least-squares slope of ys against attempt index (performance trend)."""
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0.0


def aggregate_features(window: List[AttemptRecord]) -> dict:
    """Combine a whole cycle into one robust feature set (median, not single runs)."""
    scores = [a.score for a in window]
    obst = [a.obstacles_passed for a in window]
    surv = [a.survival_time for a in window]
    mean_score = statistics.mean(scores)
    std_score = statistics.pstdev(scores) if len(scores) > 1 else 0.0
    return {
        "median_score": statistics.median(scores),
        "mean_score": mean_score,
        "std_score": std_score,
        "cv_score": std_score / mean_score if mean_score > 0 else 0.0,
        "median_survival": statistics.median(surv),
        "median_obstacles": statistics.median(obst),
        "total_collisions": sum(a.collisions for a in window),
        "success_rate": sum(a.success for a in window) / len(window),
        "score_trend": _slope(scores),
        "survival_trend": _slope(surv),
        "mean_gap": statistics.mean(a.gap_used for a in window),
    }


FEATURE_ORDER = ["median_score", "mean_score", "std_score", "cv_score",
                 "median_survival", "median_obstacles", "total_collisions",
                 "success_rate", "score_trend", "survival_trend", "mean_gap"]


# ----------------------------- controller -----------------------------
class MultiAttemptController:
    """Drop-in difficulty controller. Public surface used by the game loop:

        gap = controller.begin_attempt()        # call at the start of every attempt
        controller.end_attempt(stats_dict)      # call when attempt ends (win/lose/exit)
        controller.current_gap                  # constant for the whole attempt
    """

    name = "multi_ml"

    def __init__(self, config: Optional[AssessmentConfig] = None,
                 model_path: Optional[str] = "data/model.pkl"):
        self.cfg = config or AssessmentConfig()
        self.model, self.model_feature_names = self._load_model(model_path)
        self.current_gap = self.cfg.initial_gap
        self.pending_gap: Optional[int] = None
        self.window: List[AttemptRecord] = []      # current cycle only
        self.history: List[dict] = []              # everything, persisted
        self.decisions: List[dict] = []            # audit log: ML vs fallback
        self._load_history()

    # ---- game-loop API ----
    def begin_attempt(self) -> int:
        if self.pending_gap is not None:           # the ONLY place difficulty changes
            self.current_gap = self.pending_gap
            self.pending_gap = None
        return self.current_gap

    def end_attempt(self, stats: dict) -> None:
        if stats.get("outcome") == "exit" and \
           stats.get("survival_time", 0) < self.cfg.min_attempt_seconds:
            return                                  # accidental quit: ignore entirely
        rec = AttemptRecord(
            score=int(stats.get("score", 0)),
            survival_time=float(stats.get("survival_time", 0.0)),
            obstacles_passed=int(stats.get("obstacles_passed", stats.get("score", 0))),
            collisions=int(stats.get("collisions", 1 if stats.get("outcome") == "collision" else 0)),
            gap_used=self.current_gap,
            outcome=stats.get("outcome", "collision"),
        )
        rec.success = rec.obstacles_passed >= self.cfg.success_obstacles
        self.window.append(rec)
        self.history.append(asdict(rec))
        if len(self.window) >= self.cfg.attempts_per_cycle:
            self._assess_cycle()
            self.window = []                        # start a fresh collection cycle
        self._save_history()

    # ---- assessment ----
    def _assess_cycle(self) -> None:
        feats = aggregate_features(self.window)
        skill, source = self._estimate_skill(feats)
        c = self.cfg
        inconsistent = feats["cv_score"] > c.inconsistency_cv

        if skill > c.target_success + c.deadband:
            direction = -1                          # harder = smaller gap
        elif skill < c.target_success - c.deadband:
            direction = +1                          # easier = larger gap
        else:
            direction = 0

        # inconsistent play -> hold, or only a small nudge when the trend agrees
        if inconsistent and direction != 0:
            trend_agrees = (feats["score_trend"] > 0 and direction == -1) or \
                           (feats["score_trend"] < 0 and direction == +1)
            delta = direction * c.small_step if trend_agrees else 0
        else:
            delta = direction * c.step

        new_gap = max(c.min_gap, min(c.max_gap, self.current_gap + delta))
        self.pending_gap = new_gap                  # applied at next begin_attempt()
        self.decisions.append({
            "time": time.time(), "source": source,   # "ML_MODEL" or "RULE_BASED_FALLBACK"
            "skill": round(skill, 3), "features": feats,
            "inconsistent": inconsistent,
            "old_gap": self.current_gap, "new_gap": new_gap,
            "action": "harder" if new_gap < self.current_gap else
                      "easier" if new_gap > self.current_gap else "unchanged",
        })
        print(f"[DDA] cycle done -> source={source} skill={skill:.2f} "
              f"gap {self.current_gap} -> {new_gap} (applies next attempt)")

    def _estimate_skill(self, feats: dict):
        """Returns (skill in 0..1, source label)."""
        if self.model is not None:
            try:
                feature_names = self.model_feature_names or FEATURE_ORDER
                if feature_names == FEATURE_ORDER:
                    x = [[feats[k] for k in feature_names]]
                else:
                    from ml.features import FEATURE_NAMES
                    if feature_names != FEATURE_NAMES:
                        raise ValueError(
                            f"Unsupported model features: {feature_names}"
                        )
                    x = [self._pipeline_features(feats, self.current_gap)]
                if hasattr(self.model, "predict_proba"):
                    skill = float(self.model.predict_proba(x)[0][-1])
                else:
                    skill = float(self.model.predict(x)[0])
                return max(0.0, min(1.0, skill)), "ML_MODEL"
            except Exception as e:                  # shape mismatch, bad pickle, etc.
                print(f"[DDA] ML model unusable ({e}); using rule-based fallback")
        return self._rule_skill(feats), "RULE_BASED_FALLBACK"

    def _pipeline_features(self, feats: dict, gap: int) -> list:
        """Build the existing per-pipe training schema from attempt history."""
        from ml.features import extract_features

        success_history = [
            int(record.get("success", False)) for record in self.history
        ]
        recent3 = success_history[-3:]
        recent5 = success_history[-5:]
        consecutive_successes = 0
        consecutive_failures = 0
        for success in reversed(success_history):
            if success:
                consecutive_successes += 1
            else:
                break
        for success in reversed(success_history):
            if not success:
                consecutive_failures += 1
            else:
                break

        record = {
            "gap_size": gap,
            "bird_y_at_pass": 320,
            "bird_vel_at_pass": 0,
            "consecutive_successes_before": consecutive_successes,
            "consecutive_failures_before": consecutive_failures,
            "success_rate_last3": sum(recent3) / len(recent3) if recent3 else 0.0,
            "success_rate_last5": sum(recent5) / len(recent5) if recent5 else 0.0,
            "total_pipes_passed": feats["mean_score"],
        }
        return extract_features(record, success_history)

    @staticmethod
    def _rule_skill(f: dict) -> float:
        # Simple, transparent heuristic: success rate dominates, trend nudges.
        s = f["success_rate"] + 0.05 * max(-2, min(2, f["score_trend"]))
        return max(0.0, min(1.0, s))

    # ---- persistence ----
    @staticmethod
    def _load_model(path):
        if not path or not os.path.exists(path):
            return None, None
        try:
            import joblib
            loaded = joblib.load(path)
            if isinstance(loaded, dict) and "model" in loaded:
                names = loaded.get("feature_names")
                return loaded["model"], list(names) if names else None
            return loaded, FEATURE_ORDER
        except Exception as e:
            print(f"[DDA] could not load {path}: {e}")
            return None, None

    def _load_history(self):
        p = self.cfg.history_path
        if os.path.exists(p):
            try:
                with open(p) as fh:
                    d = json.load(fh)
                self.history = d.get("history", [])
                self.decisions = d.get("decisions", [])
                self.current_gap = d.get("current_gap", self.current_gap)
                self.pending_gap = d.get("pending_gap")
                keep = self.cfg.attempts_per_cycle
                self.window = [AttemptRecord(**r) for r in d.get("window", [])][-keep:]
            except Exception as e:
                print(f"[DDA] history unreadable ({e}); starting fresh")

    def _save_history(self):
        os.makedirs(os.path.dirname(self.cfg.history_path) or ".", exist_ok=True)
        with open(self.cfg.history_path, "w") as fh:
            json.dump({"current_gap": self.current_gap, "pending_gap": self.pending_gap,
                       "window": [asdict(a) for a in self.window],
                       "history": self.history, "decisions": self.decisions}, fh, indent=1)