import numpy as np
from controllers.base import DifficultyController
from game.config import GAP_MIN, GAP_MAX, GAP_DEFAULT


class MLAdaptiveController(DifficultyController):
    name = "ml_adaptive"

    def __init__(self, model_path="data/model.pkl", target_success=0.6):
        super().__init__(GAP_DEFAULT)
        self.model = None
        self.feature_names = None
        self.target = target_success
        self._history = []

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
        self._history.append(outcome["success"])
        if self.model is None:
            return self._fallback(outcome)
        return self._model_inference(outcome)

    def _fallback(self, outcome):
        rate3 = outcome["success_rate_last3"]
        if rate3 >= 0.66:
            self.current_gap = max(GAP_MIN, self.current_gap - 6)
        elif rate3 <= 0.33:
            self.current_gap = min(GAP_MAX, self.current_gap + 6)
        return self.current_gap

    def _model_inference(self, outcome):
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
        self.current_gap = int(max(GAP_MIN, min(GAP_MAX, self.current_gap + delta)))
        return self.current_gap

    def reset(self):
        self.current_gap = GAP_DEFAULT
        self._history = []