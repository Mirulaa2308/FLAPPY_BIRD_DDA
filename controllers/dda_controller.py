"""Data-Driven Adaptive Difficulty Controller  (DDA).

This is the controller that is activated when the player chooses
"Adaptive Difficulty" from the home screen.

Design
------
The controller separates three distinct concepts:

  current_gap       - gap used for the *next* pipe to spawn.
  estimated_min_gap - narrowest gap the player can reliably navigate,
                      estimated from observed successes/failures.  This is
                      used as the hard lower bound for current_gap.
  max_gap           - configurable upper ceiling.

Gap changes are:
  * Bounded:    always clamped to [estimated_min_gap, max_gap].
  * Gradual:    at most +-GAP_STEP per adjustment.
  * Hysteresis: a cooldown prevents multiple adjustments in quick succession.
  * Evidence-based: require a rolling-window success rate threshold before
    tightening or loosening the gap.

Machine Learning
----------------
After each completed run the controller calls ml.human_trainer.retrain_if_needed()
which (a) collects all real-player session CSVs (adaptive + maharoga),
(b) trains a LogisticRegression model if >= MIN_SAMPLES rows are available,
and (c) saves it to data/human_model.pkl.

During play, if a trained model is available the controller uses it to predict
P(success | gap) for candidate gaps and picks the gap whose predicted success
probability is closest to TARGET_SUCCESS (0.65 by default), then clamps to
bounds and applies hysteresis.

If insufficient data is available, the controller falls back to transparent
rule-based decisions and clearly labels them "RULE_BASED_FALLBACK".

Debug transparency
------------------
set debug=True to print a one-line status after each pipe outcome and a
richer summary after each run.  The in-game HUD already shows Gap and Speed;
extra fields are console-only so the player UI is clean.
"""

import time
from collections import defaultdict, deque
from typing import Optional, Dict, List

import numpy as np

from controllers.base import DifficultyController
from game.config import (
    GAP_MIN, GAP_MAX, ADAPTIVE_GAP_START,
    ADAPTIVE_PIPE_SPEED_START,
    ADAPTIVE_SPEED_MIN, ADAPTIVE_SPEED_MAX,
    ADAPTIVE_SPAWN_INTERVAL_START,
    ADAPTIVE_INTERVAL_MIN, ADAPTIVE_INTERVAL_MAX,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TARGET_SUCCESS      = 0.65   # probability the ML model aims for
GAP_STEP            = 8      # max gap change per adjustment (pixels)
WINDOW_SIZE         = 8      # rolling window for performance evaluation
ADJUSTMENT_COOLDOWN = 4      # min pipes between adjustments
MIN_WINDOW_FOR_ADJUST = 5    # need at least this many observations before adjusting

# Minimum gap evidence thresholds
MIN_EVIDENCE_PASSES = 8      # observations at a given gap before it's "reliable"
MIN_RELIABLE_RATE   = 0.70   # success rate required to lower the min gap
MIN_GAP_HARD_FLOOR  = GAP_MIN  # absolute physics-based floor (from config)

# Improvement / regression thresholds
EASY_THRESHOLD      = 0.80   # success rate above this -> tighten gap
HARD_THRESHOLD      = 0.35   # success rate below this -> widen gap

# Speed / interval adjustments (small, follow gap direction)
SPEED_STEP          = 0.10
INTERVAL_STEP       = 4

HUMAN_MODEL_PATH    = "data/human_model.pkl"


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------
class DataDrivenAdaptiveController(DifficultyController):
    """Adaptive controller that learns from real gameplay and enforces a hard
    minimum gap derived from the player's demonstrated ability.
    """

    name = "adaptive"   # keep same name so home screen / logger work unchanged

    def __init__(self,
                 initial_gap: int = ADAPTIVE_GAP_START,
                 max_gap: int = GAP_MAX,
                 model_path: str = HUMAN_MODEL_PATH,
                 target_success: float = TARGET_SUCCESS,
                 debug: bool = False,
                 preset_pipe_speed: float = ADAPTIVE_PIPE_SPEED_START,
                 preset_spawn_interval: int = int(ADAPTIVE_SPAWN_INTERVAL_START)):

        super().__init__(initial_gap)

        self.max_gap            = max_gap
        self.target_success     = target_success
        self.debug              = debug

        # Store preset so reset() always returns to the correct starting state.
        self._initial_gap           = initial_gap
        self._preset_pipe_speed     = preset_pipe_speed
        self._preset_spawn_interval = int(preset_spawn_interval)

        # --- adaptive knobs (read by game loop) ---
        self.pipe_speed         = preset_pipe_speed
        self.spawn_interval     = int(preset_spawn_interval)

        # --- state ---
        self._outcome_window: deque = deque(maxlen=WINDOW_SIZE)
        self._pipes_since_adj   = 0
        self._session_outcomes: List[int] = []   # 1/0 for current session

        # --- min gap tracking ---
        # Maps gap_size (int) -> deque of recent outcomes at that gap
        self._gap_evidence: Dict[int, deque] = defaultdict(lambda: deque(maxlen=30))
        # Start at GAP_MIN + 20 (not initial_gap) so the ML can lower the gap
        # immediately based on observed performance instead of being blocked by
        # the starting gap value acting as a hard floor.
        self._estimated_min_gap: int = max(MIN_GAP_HARD_FLOOR, GAP_MIN + 20)

        # --- ML model ---
        self._model             = None
        self._model_meta: dict  = {}
        self._model_trained_at: Optional[float] = None
        self._n_samples: int    = 0
        self._try_load_model(model_path)
        self._model_path        = model_path

        # --- debug state ---
        self._last_decision_reason = "init"
        self._last_prob: Optional[float] = None

    # -----------------------------------------------------------------------
    # Public API used by game loop
    # -----------------------------------------------------------------------

    def reset(self):
        """Called at the start of each run (retry or new game).

        Always resets to the configured starting gap and preset speed/interval.
        Does NOT clear cross-session evidence or the trained model.
        The estimated_min_gap is preserved so learned skill carries forward.
        """
        # Always restart from the preset gap, NOT the last adapted gap.
        self.current_gap     = self._clamp(self._initial_gap)
        # Restore preset speed / interval.
        self.pipe_speed      = self._preset_pipe_speed
        self.spawn_interval  = self._preset_spawn_interval
        self._outcome_window.clear()
        self._pipes_since_adj = 0
        self._session_outcomes = []
        self._last_decision_reason = "reset"
        self._last_prob = None

    def on_pipe_outcome(self, outcome: dict) -> int:
        """Called after every pipe pass or collision.

        Updates the rolling window, records evidence for the current gap,
        evaluates whether an adjustment is warranted, and returns the new gap.
        """
        success   = bool(outcome.get("success", False))
        gap_used  = int(outcome.get("gap_size", self.current_gap))

        # --- Record outcome ---
        self._outcome_window.append(int(success))
        self._session_outcomes.append(int(success))
        self._gap_evidence[gap_used].append(int(success))
        self._pipes_since_adj += 1

        # --- Decide whether to adjust ---
        if len(self._outcome_window) < MIN_WINDOW_FOR_ADJUST:
            self._last_decision_reason = "warming_up"
            return self.current_gap

        if self._pipes_since_adj < ADJUSTMENT_COOLDOWN:
            self._last_decision_reason = "cooldown"
            return self.current_gap

        recent_rate = sum(self._outcome_window) / len(self._outcome_window)
        old_gap = self.current_gap

        if self._model is not None:
            new_gap = self._ml_gap(outcome)
            source  = "ML_MODEL"
        else:
            new_gap = self._rule_gap(recent_rate, old_gap)
            source  = "RULE_BASED_FALLBACK"

        # Clamp to hard bounds (estimated_min_gap is a hard floor)
        new_gap = self._clamp(new_gap)

        if new_gap != old_gap:
            self.current_gap    = new_gap
            self._pipes_since_adj = 0
            # Gently nudge speed / interval in the same direction
            self._adjust_secondary(new_gap < old_gap)
            self._last_decision_reason = (
                f"{source}: rate={recent_rate:.2f} gap {old_gap}->{new_gap}"
            )
        else:
            self._last_decision_reason = f"{source}: no change (rate={recent_rate:.2f})"

        if self.debug:
            prob_str = f"  P={self._last_prob:.2f}" if self._last_prob is not None else ""
            print(f"[DDA]{prob_str}  gap={self.current_gap}  min_gap={self._estimated_min_gap}"
                  f"  reason={self._last_decision_reason}")

        return self.current_gap

    def on_run_end(self, died: bool = True):
        """Call this after each run completes (hit or quit).

        Updates the min-gap estimate and triggers model retraining if enough
        new data has accumulated since the last training run.
        """
        self._reestimate_min_gap()

        if self.debug:
            n_ses = len(self._session_outcomes)
            rate  = sum(self._session_outcomes) / max(1, n_ses)
            print(f"[DDA] run ended  died={died}  pipes={n_ses}  rate={rate:.2f}  "
                  f"min_gap={self._estimated_min_gap}")

        # Retrain using BOTH 'adaptive' and 'maharoga' logs so Maharoga
        # gameplay actually feeds back into the ML model.
        # Debounced: at most once every 5 min; needs >= 80 human samples.
        try:
            from ml.human_trainer import retrain_if_needed
            bundle = retrain_if_needed(
                model_path=self._model_path,
                verbose=self.debug,
                controller_filters=("adaptive", "maharoga"),
            )
            if bundle is not None:
                new_model = bundle.get("model")
                if new_model is not None:
                    self._model      = new_model
                    self._model_meta = bundle
                    self._model_trained_at = bundle.get("trained_at")
                    self._n_samples  = bundle.get("n_samples", self._n_samples)
                    if self.debug:
                        print(f"[DDA] model updated: n={bundle.get('n_samples')} "
                              f"trained_at={self._model_trained_at}")
        except Exception as e:
            if self.debug:
                print(f"[DDA] retrain skipped: {e}")

    # -----------------------------------------------------------------------
    # Debug info (read by HUD; safe to call any time)
    # -----------------------------------------------------------------------

    def debug_info(self) -> dict:
        """Return a snapshot of key internal state for the debug HUD."""
        trained_str = "never"
        if self._model_trained_at:
            age = int(time.time() - self._model_trained_at)
            trained_str = f"{age}s ago"

        return {
            "current_gap":      self.current_gap,
            "estimated_min_gap": self._estimated_min_gap,
            "last_prob":        self._last_prob,
            "n_training_samples": self._n_samples,
            "model_trained":    self._model is not None,
            "model_trained_at": trained_str,
            "last_reason":      self._last_decision_reason,
        }

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _clamp(self, gap: int) -> int:
        """Clamp gap to [estimated_min_gap, max_gap]."""
        lo = max(self._estimated_min_gap, MIN_GAP_HARD_FLOOR)
        return int(max(lo, min(self.max_gap, gap)))

    def _ml_gap(self, outcome: dict) -> int:
        """Use the loaded model to pick a gap whose predicted P(success)
        is closest to self.target_success, then clamp to +-GAP_STEP.
        """
        try:
            from ml.features import extract_features

            # Probe candidate gaps in increments of 5 px
            candidates = list(range(MIN_GAP_HARD_FLOOR, self.max_gap + 1, 5))
            best_gap   = self.current_gap
            best_dist  = float("inf")

            history = self._session_outcomes[:-1]   # exclude current event

            for g in candidates:
                probe = dict(outcome)
                probe["gap_size"] = g
                feats  = extract_features(probe, history)
                X      = np.array([feats])
                prob   = float(self._model.predict_proba(X)[0, 1])
                dist   = abs(prob - self.target_success)
                if dist < best_dist:
                    best_dist  = dist
                    best_gap   = g
                    self._last_prob = prob   # store for debug

            # Cap change to +-GAP_STEP
            delta    = best_gap - self.current_gap
            delta    = max(-GAP_STEP, min(GAP_STEP, delta))
            new_gap  = self.current_gap + delta
            return new_gap

        except Exception as e:
            if self.debug:
                print(f"[DDA] ML inference failed ({e}); falling back to rules")
            recent_rate = (sum(self._outcome_window) / len(self._outcome_window)
                           if self._outcome_window else 0.5)
            return self._rule_gap(recent_rate, self.current_gap)

    def _rule_gap(self, recent_rate: float, current_gap: int) -> int:
        """Pure rule-based fallback (explicitly labelled, not ML)."""
        if recent_rate >= EASY_THRESHOLD:
            return current_gap - GAP_STEP
        elif recent_rate <= HARD_THRESHOLD:
            return current_gap + GAP_STEP
        return current_gap

    def _adjust_secondary(self, harder: bool):
        """Nudge speed and spawn interval in the same direction as gap change."""
        if harder:
            self.pipe_speed    = min(ADAPTIVE_SPEED_MAX, self.pipe_speed + SPEED_STEP)
            self.spawn_interval = max(ADAPTIVE_INTERVAL_MIN,
                                      self.spawn_interval - INTERVAL_STEP)
        else:
            self.pipe_speed    = max(ADAPTIVE_SPEED_MIN, self.pipe_speed - SPEED_STEP)
            self.spawn_interval = min(ADAPTIVE_INTERVAL_MAX,
                                      self.spawn_interval + INTERVAL_STEP)

    def _reestimate_min_gap(self):
        """Re-examine accumulated gap evidence and lower estimated_min_gap
        if the player has demonstrated reliable ability at a smaller gap.
        """
        # Aggregate evidence across all gap sizes <= current estimated_min_gap - 5
        candidate_lower = self._estimated_min_gap - 5
        if candidate_lower < MIN_GAP_HARD_FLOOR:
            return   # already at physics floor

        all_obs = []
        for g, hist in self._gap_evidence.items():
            if g <= candidate_lower:
                all_obs.extend(list(hist))

        if len(all_obs) < MIN_EVIDENCE_PASSES:
            return  # not enough evidence

        rate = sum(all_obs) / len(all_obs)
        if rate >= MIN_RELIABLE_RATE:
            new_min = max(MIN_GAP_HARD_FLOOR, candidate_lower)
            if new_min < self._estimated_min_gap:
                if self.debug:
                    print(f"[DDA] min_gap lowered: {self._estimated_min_gap} -> {new_min} "
                          f"(evidence: {len(all_obs)} obs, rate={rate:.2f})")
                self._estimated_min_gap = new_min

    def _try_load_model(self, model_path: str):
        """Load an existing human model from disk at startup."""
        try:
            from ml.human_trainer import _load_model_bundle
            bundle = _load_model_bundle(model_path)
            if bundle:
                self._model           = bundle.get("model")
                self._model_meta      = bundle
                self._model_trained_at = bundle.get("trained_at")
                self._n_samples       = bundle.get("n_samples", 0)
                print(f"[DDA] Loaded human model: "
                      f"n={bundle.get('n_samples')} samples, "
                      f"sessions={bundle.get('n_sessions')}, "
                      f"AUC={bundle.get('test_auc')}")
            else:
                try:
                    from ml.human_trainer import count_human_samples
                    self._n_samples = count_human_samples()
                except Exception:
                    self._n_samples = 0
                print("[DDA] No human model found. Using rule-based fallback.")
        except Exception as e:
            print(f"[DDA] Could not load model ({e}). Using fallback.")
