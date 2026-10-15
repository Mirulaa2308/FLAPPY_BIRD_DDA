from abc import ABC, abstractmethod


class DifficultyController(ABC):
    name = "base"

    def __init__(self, initial_gap: int):
        self.current_gap = initial_gap

    @abstractmethod
    def on_pipe_outcome(self, outcome: dict) -> int:
        raise NotImplementedError

    def reset(self):
        pass