from controllers.base import DifficultyController
from game.config import FIXED_PIPE_SPEED, FIXED_SPAWN_INTERVAL


class FixedController(DifficultyController):
    name = "fixed"

    def __init__(self, gap: int = 165, ml_override: bool = False,
                 max_center_delta: int = 90):
        super().__init__(gap)
        self.gap = gap
        self.ml_override = ml_override           # if False, gap/speed never change
        self.max_center_delta = max_center_delta  # passed to pipe spawner
        # Expose speed/interval so the game loop can read them via getattr.
        # These can be overwritten by the difficulty preset after construction.
        self.pipe_speed     = FIXED_PIPE_SPEED
        self.spawn_interval = FIXED_SPAWN_INTERVAL

    def reset(self):
        """Restore preset gap at the start of each run."""
        self.current_gap = self.gap

    def on_pipe_outcome(self, outcome):
        # Always return the fixed gap; ignore any adaptive signals.
        return self.gap
