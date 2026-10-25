"""Simple rule-based adaptive difficulty controller.

Adjusts three knobs based on recent player performance:
  - gap_size   : width of the passage between pipes (larger = easier)
  - pipe_speed : pixels per frame pipes move (faster = harder)
  - spawn_interval : frames between new pipes (shorter = harder)

Rules (evaluated each pipe outcome):
  * Recent success rate (last 5 pipes) > 0.80 for 3+ consecutive
    pipe successes  → tighten difficulty slightly
  * Recent success rate (last 5 pipes) < 0.40 for 2+ consecutive
    pipe failures   → ease difficulty slightly

Changes are bounded and gradual (one step per event, not per frame).
All parameters start at ADAPTIVE_*_START constants from config.
"""
from controllers.base import DifficultyController
from game.config import (
    GAP_MIN, GAP_MAX,
    ADAPTIVE_GAP_START, ADAPTIVE_PIPE_SPEED_START, ADAPTIVE_SPAWN_INTERVAL_START,
    ADAPTIVE_SPEED_MIN, ADAPTIVE_SPEED_MAX,
    ADAPTIVE_INTERVAL_MIN, ADAPTIVE_INTERVAL_MAX,
)

# Step sizes for one difficulty adjustment
_GAP_STEP      = 10     # pixels
_SPEED_STEP    = 0.15   # px/frame
_INTERVAL_STEP = 5      # frames


class AdaptiveController(DifficultyController):
    """Reactive, rule-based adaptive difficulty. Distinct from FixedController."""

    name = "adaptive"

    def __init__(self):
        super().__init__(ADAPTIVE_GAP_START)
        self.pipe_speed = ADAPTIVE_PIPE_SPEED_START
        self.spawn_interval = int(ADAPTIVE_SPAWN_INTERVAL_START)

        self._outcome_window = []   # recent pipe outcomes (1=pass, 0=fail)
        self._window_size    = 5
        self._consec_pass    = 0    # consecutive pipe passes (for hard trigger)
        self._consec_fail    = 0    # consecutive pipe failures (for easy trigger)

    # ------------------------------------------------------------------ #

    def reset(self):
        """Full reset to starting values (called at game start, not per death)."""
        self.current_gap   = ADAPTIVE_GAP_START
        self.pipe_speed    = ADAPTIVE_PIPE_SPEED_START
        self.spawn_interval = int(ADAPTIVE_SPAWN_INTERVAL_START)
        self._outcome_window.clear()
        self._consec_pass  = 0
        self._consec_fail  = 0

    # ------------------------------------------------------------------ #

    def on_pipe_outcome(self, outcome: dict) -> int:
        success = bool(outcome.get("success", False))

        # Update window
        self._outcome_window.append(int(success))
        if len(self._outcome_window) > self._window_size:
            self._outcome_window.pop(0)

        # Update consecutive counters
        if success:
            self._consec_pass += 1
            self._consec_fail = 0
        else:
            self._consec_fail += 1
            self._consec_pass = 0

        recent_rate = (sum(self._outcome_window) / len(self._outcome_window)
                       if self._outcome_window else 0.5)

        # --- Make it harder if player is doing well ---
        if recent_rate > 0.80 and self._consec_pass >= 3:
            self.current_gap   = max(GAP_MIN,                self.current_gap   - _GAP_STEP)
            self.pipe_speed    = min(ADAPTIVE_SPEED_MAX,     self.pipe_speed    + _SPEED_STEP)
            self.spawn_interval = max(ADAPTIVE_INTERVAL_MIN, self.spawn_interval - _INTERVAL_STEP)
            self._consec_pass = 0   # reset so we don't spam adjustments

        # --- Make it easier if player is struggling ---
        elif recent_rate < 0.40 and self._consec_fail >= 2:
            self.current_gap   = min(GAP_MAX,                self.current_gap   + _GAP_STEP)
            self.pipe_speed    = max(ADAPTIVE_SPEED_MIN,     self.pipe_speed    - _SPEED_STEP)
            self.spawn_interval = min(ADAPTIVE_INTERVAL_MAX, self.spawn_interval + _INTERVAL_STEP)
            self._consec_fail = 0

        return self.current_gap
