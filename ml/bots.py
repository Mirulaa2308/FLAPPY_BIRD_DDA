"""Scripted bot policies for FLAPPY ADAPT.

All bots use the same jump rule (proven to work in testing).
Skill differences come from:
  - target_offset: how far below gap center the bot aims
  - noise: probability of flipping a jump decision
  - reaction_delay: frames of lag before responding
"""
import random
from game.config import SCREEN_HEIGHT, PIPE_WIDTH


class _BaseBot:
    name = "base"
    target_offset = 15
    noise = 0.0
    reaction_delay = 0
    jump_velocity_threshold = -1.0

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.delay_buffer = []

    def _next_pipe(self, bird, pipes):
        for pipe in pipes:
            if not pipe.passed and pipe.x + PIPE_WIDTH > bird.x - 10:
                return pipe
        return None

    def _decide(self, bird, pipes):
        next_pipe = self._next_pipe(bird, pipes)
        if next_pipe is not None:
            target_y = next_pipe.gap_center + self.target_offset
        else:
            target_y = SCREEN_HEIGHT / 2

        # Jump when falling and below target
        if bird.velocity >= self.jump_velocity_threshold and bird.y > target_y:
            return True
        return False

    def __call__(self, bird, pipes):
        raw = self._decide(bird, pipes)

        # Noise
        if self.noise > 0 and self.rng.random() < self.noise:
            raw = not raw

        # Reaction delay: hold decisions in a small queue
        if self.reaction_delay > 0:
            self.delay_buffer.append(raw)
            if len(self.delay_buffer) > self.reaction_delay:
                return self.delay_buffer.pop(0)
            return False

        return raw

    def reset(self):
        self.delay_buffer = []


class BotLowSkill(_BaseBot):
    """Weak: large aim error, noisy decisions, delayed reactions."""
    name = "low"
    target_offset = 40
    noise = 0.12
    reaction_delay = 3


class BotMediumSkill(_BaseBot):
    """Decent: moderate aim error, small noise."""
    name = "medium"
    target_offset = 25
    noise = 0.04
    reaction_delay = 1


class BotHighSkill(_BaseBot):
    """Skilled: precise aim, no noise, immediate response."""
    name = "high"
    target_offset = 15
    noise = 0.0
    reaction_delay = 0