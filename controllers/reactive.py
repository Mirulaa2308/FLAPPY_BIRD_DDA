from controllers.base import DifficultyController
from game.config import GAP_MIN, GAP_MAX


class ReactiveController(DifficultyController):
    name = "reactive"

    def __init__(self, initial_gap=165, step=12, streak_threshold=3):
        super().__init__(initial_gap)
        self.step = step
        self.streak = streak_threshold

    def on_pipe_outcome(self, outcome):
        cons_success = outcome["consecutive_successes_before"]
        cons_failure = outcome["consecutive_failures_before"]

        if outcome["success"] and cons_success >= self.streak:
            self.current_gap = max(GAP_MIN, self.current_gap - self.step)
        elif (not outcome["success"]) and cons_failure >= self.streak:
            self.current_gap = min(GAP_MAX, self.current_gap + self.step)

        return self.current_gap

    def reset(self):
        pass