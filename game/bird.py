import pygame
from game.config import (
    BIRD_X, BIRD_START_Y, BIRD_RADIUS, GRAVITY, JUMP_VELOCITY, COLOR_BIRD
)


class Bird:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = BIRD_X
        self.y = float(BIRD_START_Y)
        self.velocity = 0.0
        self.alive = True

    def jump(self):
        if self.alive:
            self.velocity = JUMP_VELOCITY

    def update(self):
        self.velocity += GRAVITY
        self.y += self.velocity

    def get_rect(self):
        return pygame.Rect(
            self.x - BIRD_RADIUS, self.y - BIRD_RADIUS,
            BIRD_RADIUS * 2, BIRD_RADIUS * 2
        )

    def draw(self, surface):
        pygame.draw.circle(surface, COLOR_BIRD,
                           (int(self.x), int(self.y)), BIRD_RADIUS)
        pygame.draw.circle(surface, (0, 0, 0),
                           (int(self.x) + 5, int(self.y) - 4), 3)