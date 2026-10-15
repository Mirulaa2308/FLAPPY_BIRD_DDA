from controllers.base import DifficultyController


class FixedController(DifficultyController):
    name = "fixed"

    def __init__(self, gap: int = 165):
        super().__init__(gap)
        self.gap = gap

    def on_pipe_outcome(self, outcome):
        return self.gap