import numpy as np
from controllers.base import DifficultyController
from controllers.streak_gate import StreakGate
from game.config import GAP_MIN, GAP_MAX, GAP_DEFAULT


class MLAdaptiveController(DifficultyController):
    name = "ml_adaptive"

    def __init__(self, model_path="data/model.pkl", target_success=0.6,
                 streak_threshold=5, verbose=True):
        super().__init__(GAP_DEFAULT)
        self.model = None
        self.feature_names = None
        self.target = target_success
        self._history = []
        self.verbose = verbose
        # The model (or fallback) may only adjust the gap when this gate opens.
        self.gate = StreakGate(loss_threshold=streak_threshold,
                               success_threshold=streak_threshold)
        self.last_decision = None   # {"source", "direction", "old_gap", "new_gap"}

        if model_path:
            try:
                import joblib
                bundle = joblib.load(model_path)
                self.model = bundle["model"]
                self.feature_names = bundle.get("feature_names")
                print(f"[MLAdaptive] Loaded model from {model_path}")
            except Exception as e:
                print(f"[MLAdaptive] Could not load model ({e}). Using heuristic fallback.")

    def on_pipe_outcome(self, outcome):
        self._history.append(outcome["success"])     # history is always kept
        direction = self.gate.update(bool(outcome["success"]))

        if direction == StreakGate.HOLD:
            return self.current_gap                  # single events never change the gap

        old_gap = self.current_gap
        if self.model is None:
            source = "RULE_BASED_FALLBACK"
            self._fallback(direction)
        else:
            source = "ML_MODEL"
            self._model_inference(outcome, direction)

        self.last_decision = {"source": source, "direction": direction,
                              "old_gap": old_gap, "new_gap": self.current_gap}
        if self.verbose:
            kind = "easier (failure streak)" if direction == StreakGate.EASIER \
                else "harder (success streak)"
            print(f"[MLAdaptive] streak reached -> {kind} | source={source} | "
                  f"gap {old_gap} -> {self.current_gap}")
        return self.current_gap

    def _fallback(self, direction):
        # Hard-coded rule (NOT machine learning): a fixed 6px step in the
        # direction of the streak.
        if direction == StreakGate.HARDER:
            self.current_gap = max(GAP_MIN, self.current_gap - 6)
        else:
            self.current_gap = min(GAP_MAX, self.current_gap + 6)
        return self.current_gap

    def _model_inference(self, outcome, direction):
        from ml.features import extract_features

        candidates = list(range(GAP_MIN, GAP_MAX + 1, 10))
        best_gap = self.current_gap
        best_distance = float("inf")

        for gap in candidates:
            probe = dict(outcome)
            probe["gap_size"] = gap
            feats = extract_features(probe, self._history[:-1])
            X = np.array([feats])
            prob = float(self.model.predict_proba(X)[0, 1])
            distance = abs(prob - self.target)
            if distance < best_distance:
                best_distance = distance
                best_gap = gap

        delta = best_gap - self.current_gap
        delta = max(-8, min(8, delta))
        # Keep the model consistent with the streak rule: after a failure streak
        # it may only keep or increase the gap, after a success streak only keep
        # or decrease it.
        if direction == StreakGate.EASIER:
            delta = max(0, delta)
        else:
            delta = min(0, delta)
        self.current_gap = int(max(GAP_MIN, min(GAP_MAX, self.current_gap + delta)))
        return self.current_gap

    def reset(self):
        self.current_gap = GAP_DEFAULT
        self._history = []
        self.gate.reset()
        self.last_decision = None
