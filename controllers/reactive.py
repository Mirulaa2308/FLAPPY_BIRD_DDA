from controllers.base import DifficultyController
from controllers.streak_gate import StreakGate
from game.config import GAP_MIN, GAP_MAX


class ReactiveController(DifficultyController):
    name = "reactive"

    def __init__(self, initial_gap=165, step=12, streak_threshold=5):
        super().__init__(initial_gap)
        self.step = step
        self.streak = streak_threshold
        # The gap only changes after `streak_threshold` consecutive failures
        # (easier) or consecutive successes (harder). Never on a single event.
        self.gate = StreakGate(loss_threshold=streak_threshold,
                               success_threshold=streak_threshold)

    def on_pipe_outcome(self, outcome):
        decision = self.gate.update(bool(outcome["success"]))

        if decision == StreakGate.EASIER:
            self.current_gap = min(GAP_MAX, self.current_gap + self.step)
        elif decision == StreakGate.HARDER:
            self.current_gap = max(GAP_MIN, self.current_gap - self.step)

        return self.current_gap

    def reset(self):
        # Unchanged from the original: reset() did nothing, so streaks and the
        # gap carry across attempts.
        pass
