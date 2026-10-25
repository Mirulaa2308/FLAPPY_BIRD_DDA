"""Bird game object – supports custom sprite with fallback circle."""
import os
import pygame
from game.config import (
    BIRD_X, BIRD_START_Y, BIRD_RADIUS, GRAVITY, JUMP_VELOCITY,
    COLOR_BIRD, BIRD_SPRITE, BIRD_SPRITE_SIZE
)

# Try to load sprite once at module import so it is shared across instances.
_sprite_image = None


def _load_sprite():
    global _sprite_image
    if _sprite_image is not None:
        return _sprite_image
    try:
        img = pygame.image.load(BIRD_SPRITE).convert_alpha()
        img = pygame.transform.smoothscale(img, BIRD_SPRITE_SIZE)
        _sprite_image = img
    except Exception:
        _sprite_image = None
    return _sprite_image


class Bird:
    def __init__(self):
        self.sprite = None          # loaded lazily after pygame.init()
        self.reset()

    # ------------------------------------------------------------------ #
    #  State helpers                                                       #
    # ------------------------------------------------------------------ #

    def reset(self):
        self.x = BIRD_X
        self.y = float(BIRD_START_Y)
        self.velocity = 0.0
        self.alive = True
        self.sprite = None          # force sprite reload on next draw

    def jump(self):
        if self.alive:
            self.velocity = JUMP_VELOCITY

    def update(self):
        self.velocity += GRAVITY
        self.y += self.velocity

    # ------------------------------------------------------------------ #
    #  Collision rectangle                                                 #
    # ------------------------------------------------------------------ #

    def get_rect(self):
        """Conservative collision rect centred on the bird position."""
        r = BIRD_RADIUS
        return pygame.Rect(self.x - r, self.y - r, r * 2, r * 2)

    # ------------------------------------------------------------------ #
    #  Drawing                                                             #
    # ------------------------------------------------------------------ #

    def _ensure_sprite(self):
        if self.sprite is None:
            self.sprite = _load_sprite()

    def _tilt_angle(self):
        """Return a tilt angle (degrees) based on velocity for visual feedback."""
        angle = -self.velocity * 3.0           # nose-down when falling
        return max(-40.0, min(20.0, angle))    # clamp so it never spins

    def draw(self, surface):
        self._ensure_sprite()

        cx, cy = int(self.x), int(self.y)

        if self.sprite is not None:
            angle = self._tilt_angle()
            rotated = pygame.transform.rotate(self.sprite, angle)
            rect = rotated.get_rect(center=(cx, cy))
            surface.blit(rotated, rect.topleft)
        else:
            # Fallback: yellow circle with eye
            pygame.draw.circle(surface, COLOR_BIRD, (cx, cy), BIRD_RADIUS)
            pygame.draw.circle(surface, (0, 0, 0), (cx + 5, cy - 4), 3)