import random
import pygame
from game.config import (
    SCREEN_HEIGHT, PIPE_WIDTH, PIPE_MIN_TOP, PIPE_MAX_TOP_MARGIN,
    PIPE_SPEED, COLOR_PIPE
)


class Pipe:
    def __init__(self, x, gap_size, gap_center=None):
        self.x = float(x)
        self.gap_size = gap_size
        self.passed = False

        min_center = PIPE_MIN_TOP + gap_size / 2
        max_center = SCREEN_HEIGHT - PIPE_MAX_TOP_MARGIN - gap_size / 2
        if gap_center is None:
            gap_center = random.uniform(min_center, max_center)
        self.gap_center = gap_center

    def update(self):
        self.x -= PIPE_SPEED

    def get_rects(self):
        top_height = self.gap_center - self.gap_size / 2
        bottom_y = self.gap_center + self.gap_size / 2
        top_rect = pygame.Rect(int(self.x), 0, PIPE_WIDTH, int(top_height))
        bottom_rect = pygame.Rect(
            int(self.x), int(bottom_y),
            PIPE_WIDTH, int(SCREEN_HEIGHT - bottom_y)
        )
        return top_rect, bottom_rect

    def off_screen(self):
        return self.x + PIPE_WIDTH < 0

    def draw(self, surface):
        top_rect, bottom_rect = self.get_rects()
        pygame.draw.rect(surface, COLOR_PIPE, top_rect)
        pygame.draw.rect(surface, COLOR_PIPE, bottom_rect)