"""Pipe game object – supports per-instance speed for adaptive mode."""
import random
import pygame
from game.config import (
    SCREEN_HEIGHT, PIPE_WIDTH, PIPE_MIN_TOP, PIPE_MAX_TOP_MARGIN,
    PIPE_SPEED, COLOR_PIPE, COLOR_PIPE_HIGHLIGHT
)

PIPE_CAP_HEIGHT = 14   # little cap drawn on pipe ends


class Pipe:
    def __init__(self, x, gap_size, gap_center=None, speed=None):
        self.x = float(x)
        self.gap_size = gap_size
        self.passed = False
        self.speed = speed if speed is not None else PIPE_SPEED

        min_center = PIPE_MIN_TOP + gap_size / 2
        max_center = SCREEN_HEIGHT - PIPE_MAX_TOP_MARGIN - gap_size / 2
        if gap_center is None:
            gap_center = random.uniform(min_center, max_center)
        self.gap_center = gap_center

    def update(self):
        self.x -= self.speed

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

        # Main body
        pygame.draw.rect(surface, COLOR_PIPE, top_rect)
        pygame.draw.rect(surface, COLOR_PIPE, bottom_rect)

        # Highlight stripe (left edge shine)
        highlight_w = 8
        if top_rect.height > 0:
            pygame.draw.rect(
                surface, COLOR_PIPE_HIGHLIGHT,
                (top_rect.x + 4, top_rect.y, highlight_w, top_rect.height)
            )
        if bottom_rect.height > 0:
            pygame.draw.rect(
                surface, COLOR_PIPE_HIGHLIGHT,
                (bottom_rect.x + 4, bottom_rect.y, highlight_w, bottom_rect.height)
            )

        # Caps (wider bar at gap edge)
        cap_x = int(self.x) - 4
        cap_w = PIPE_WIDTH + 8

        # Top pipe cap (bottom edge of top pipe)
        if top_rect.height > 0:
            cap_y = top_rect.bottom - PIPE_CAP_HEIGHT
            pygame.draw.rect(surface, COLOR_PIPE, (cap_x, cap_y, cap_w, PIPE_CAP_HEIGHT))

        # Bottom pipe cap (top edge of bottom pipe)
        pygame.draw.rect(surface, COLOR_PIPE, (cap_x, bottom_rect.y, cap_w, PIPE_CAP_HEIGHT))