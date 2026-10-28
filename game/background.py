"""Sky and background rendering with repeating Day → Evening → Night cycle.

Phase is driven by pipes_passed using a repeating 40-pipe cycle:
  cycle_pos = pipes_passed % SKY_CYCLE_PERIOD
   0 – 9   → Day       (blue sky, white clouds, sun)
  10 – 19  → Evening   (orange/pink/purple sunset)
  20 – 39  → Night     (dark blue, stars, moon)

The cycle repeats every 40 pipes (configurable via SKY_CYCLE_PERIOD).
Smooth cross-fades happen across 5-pipe blend zones at each threshold.
Parallax cloud/star layers scroll at different speeds to add depth.
"""
import math
import random
import pygame
from game.config import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    SKY_CYCLE_PERIOD, SKY_DAY_END, SKY_EVENING_END,
)


# ---------------------------------------------------------------------------
# Sky colour key-frames  (top, bottom)
# ---------------------------------------------------------------------------
_DAY_TOP    = (80,  160, 230)
_DAY_BOT    = (170, 220, 255)

_EVENING_TOP = (120,  60, 140)
_EVENING_BOT = (240, 140,  60)

_NIGHT_TOP  = (10,  10,  40)
_NIGHT_BOT  = (30,  30,  80)

# Ground colours per phase
_GROUND_DAY     = (120, 200,  80)
_GROUND_EVENING = (180, 100,  40)
_GROUND_NIGHT   = ( 30,  60,  20)

GROUND_HEIGHT = 20    # height of the ground strip at the bottom


def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _smooth(t):
    """Smoothstep for silky cross-fades."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _cycle_pos(pipes_passed):
    """Return position within the current 40-pipe cycle [0, SKY_CYCLE_PERIOD)."""
    return pipes_passed % SKY_CYCLE_PERIOD


def _sky_colors(pipes_passed):
    """Return (top_color, bottom_color, ground_color) for pipes_passed.

    Uses a repeating SKY_CYCLE_PERIOD-pipe cycle:
      0..SKY_DAY_END-1     → Day
      SKY_DAY_END..SKY_EVENING_END-1 → Evening / Sunset
      SKY_EVENING_END..end → Night
    Cross-fades happen over BLEND_RANGE pipes at each boundary.
    """
    BLEND = 5   # cross-fade width in pipes
    cp = _cycle_pos(pipes_passed)   # 0..39

    if cp < SKY_DAY_END:
        # Pure day (or blend back from night at cycle boundary handled below)
        top    = _DAY_TOP
        bottom = _DAY_BOT
        ground = _GROUND_DAY
        # Blend from night at the very start of a new cycle (cp 0..BLEND)
        if cp < BLEND and pipes_passed >= SKY_CYCLE_PERIOD:
            t = _smooth(1.0 - cp / BLEND)
            top    = _lerp_color(_DAY_TOP,    _NIGHT_TOP,    t)
            bottom = _lerp_color(_DAY_BOT,    _NIGHT_BOT,    t)
            ground = _lerp_color(_GROUND_DAY, _GROUND_NIGHT, t)
    elif cp < SKY_DAY_END + BLEND:
        # Day → Evening blend
        t = _smooth((cp - SKY_DAY_END) / BLEND)
        top    = _lerp_color(_DAY_TOP,    _EVENING_TOP,    t)
        bottom = _lerp_color(_DAY_BOT,    _EVENING_BOT,    t)
        ground = _lerp_color(_GROUND_DAY, _GROUND_EVENING, t)
    elif cp < SKY_EVENING_END:
        # Pure evening
        top    = _EVENING_TOP
        bottom = _EVENING_BOT
        ground = _GROUND_EVENING
    elif cp < SKY_EVENING_END + BLEND:
        # Evening → Night blend
        t = _smooth((cp - SKY_EVENING_END) / BLEND)
        top    = _lerp_color(_EVENING_TOP,    _NIGHT_TOP,    t)
        bottom = _lerp_color(_EVENING_BOT,    _NIGHT_BOT,    t)
        ground = _lerp_color(_GROUND_EVENING, _GROUND_NIGHT, t)
    else:
        # Pure night
        top    = _NIGHT_TOP
        bottom = _NIGHT_BOT
        ground = _GROUND_NIGHT

    return top, bottom, ground


# ---------------------------------------------------------------------------
# Cloud sprites (generated procedurally)
# ---------------------------------------------------------------------------
class _Cloud:
    def __init__(self, x=None, y=None, scale=1.0, speed=0.4):
        self.x = x if x is not None else random.randint(0, SCREEN_WIDTH)
        self.y = y if y is not None else random.randint(40, SCREEN_HEIGHT // 3)
        self.scale = scale
        self.speed = speed
        self.alpha = random.randint(160, 220)

    def update(self):
        self.x -= self.speed
        if self.x + 100 * self.scale < 0:
            self.x = SCREEN_WIDTH + 20
            self.y = random.randint(40, SCREEN_HEIGHT // 3)

    def draw(self, surface, opacity):
        if opacity <= 0:
            return
        s = self.scale
        cx, cy = int(self.x), int(self.y)
        a = int(self.alpha * opacity)
        color = (255, 255, 255, a)

        # Draw as a temporary surface with per-pixel alpha
        w = int(90 * s)
        h = int(45 * s)
        cloud_surf = pygame.Surface((w + 20, h + 20), pygame.SRCALPHA)
        pygame.draw.ellipse(cloud_surf, color, (10, 12, int(70 * s), int(28 * s)))
        pygame.draw.ellipse(cloud_surf, color, (int(5 * s), int(6 * s), int(40 * s), int(30 * s)))
        pygame.draw.ellipse(cloud_surf, color, (int(30 * s), 2, int(50 * s), int(34 * s)))
        surface.blit(cloud_surf, (cx - w // 2, cy - h // 2))


# ---------------------------------------------------------------------------
# Star sprites (night only)
# ---------------------------------------------------------------------------
class _Star:
    def __init__(self):
        self.x = random.randint(0, SCREEN_WIDTH)
        self.y = random.randint(0, int(SCREEN_HEIGHT * 0.65))
        self.size = random.randint(1, 3)
        self.twinkle = random.uniform(0, math.pi * 2)
        self.speed = random.uniform(0.003, 0.008)

    def update(self):
        self.twinkle += self.speed

    def brightness(self):
        return 0.6 + 0.4 * math.sin(self.twinkle)

    def draw(self, surface, opacity):
        if opacity <= 0:
            return
        b = int(255 * self.brightness() * opacity)
        color = (b, b, min(255, b + 40))
        pygame.draw.circle(surface, color, (self.x, self.y), self.size)


# ---------------------------------------------------------------------------
# Background manager
# ---------------------------------------------------------------------------
class BackgroundRenderer:
    """Owns all background state. Call update(pipes_passed) then draw(surface)."""

    NUM_CLOUDS = 6
    NUM_STARS  = 80

    def __init__(self):
        # Two layers of clouds at different speeds for parallax
        self.clouds_far  = [_Cloud(speed=0.3, scale=random.uniform(0.6, 0.9))
                            for _ in range(self.NUM_CLOUDS)]
        self.clouds_near = [_Cloud(speed=0.7, scale=random.uniform(0.9, 1.3))
                            for _ in range(self.NUM_CLOUDS // 2 + 1)]
        self.stars = [_Star() for _ in range(self.NUM_STARS)]
        self._pipes_passed = 0

        # Pre-built gradient surface cache
        self._gradient_cache = {}

    # ------------------------------------------------------------------ #
    def update(self, pipes_passed):
        self._pipes_passed = pipes_passed
        for c in self.clouds_far:
            c.update()
        for c in self.clouds_near:
            c.update()
        for s in self.stars:
            s.update()

    # ------------------------------------------------------------------ #
    def _build_gradient(self, top_color, bot_color):
        """Draw a vertical gradient into a surface."""
        key = (top_color, bot_color)
        if key in self._gradient_cache:
            return self._gradient_cache[key]

        surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        for y in range(SCREEN_HEIGHT):
            t = y / SCREEN_HEIGHT
            c = _lerp_color(top_color, bot_color, t)
            pygame.draw.line(surf, c, (0, y), (SCREEN_WIDTH, y))
        self._gradient_cache[key] = surf
        return surf

    # ------------------------------------------------------------------ #
    def _cloud_opacity(self):
        """Clouds fade out as night approaches (cycle-aware)."""
        cp = _cycle_pos(self._pipes_passed)
        if cp < SKY_DAY_END:
            return 1.0
        if cp < SKY_EVENING_END:
            return 1.0 - _smooth((cp - SKY_DAY_END) / (SKY_EVENING_END - SKY_DAY_END)) * 0.7
        return 0.3

    def _star_opacity(self):
        """Stars fade in starting at evening (cycle-aware)."""
        cp = _cycle_pos(self._pipes_passed)
        if cp < SKY_DAY_END:
            return 0.0
        if cp < SKY_EVENING_END:
            return _smooth((cp - SKY_DAY_END) / (SKY_EVENING_END - SKY_DAY_END)) * 0.5
        return min(1.0, _smooth((cp - SKY_EVENING_END) / 5))

    # ------------------------------------------------------------------ #
    def draw(self, surface):
        top, bottom, ground = _sky_colors(self._pipes_passed)

        # Sky gradient
        grad = self._build_gradient(top, bottom)
        surface.blit(grad, (0, 0))

        # Stars (night layer)
        star_op = self._star_opacity()
        for s in self.stars:
            s.draw(surface, star_op)

        # Moon (appears at night – cycle-aware)
        cp = _cycle_pos(self._pipes_passed)
        night_start = SKY_EVENING_END - 2
        if cp >= night_start:
            moon_op = min(1.0, _smooth((cp - night_start) / 5))
            self._draw_moon(surface, moon_op)

        # Sun / evening glow (cycle-aware)
        if cp < SKY_EVENING_END:
            if cp < SKY_DAY_END:
                self._draw_sun(surface, 1.0)
            else:
                sun_fade = 1.0 - _smooth((cp - SKY_DAY_END) /
                                         (SKY_EVENING_END - SKY_DAY_END))
                self._draw_sun(surface, sun_fade)

        # Clouds (far layer first, then near for depth)
        cloud_op = self._cloud_opacity()
        for c in self.clouds_far:
            c.draw(surface, cloud_op * 0.7)
        for c in self.clouds_near:
            c.draw(surface, cloud_op)

        # Ground strip
        ground_y = SCREEN_HEIGHT - GROUND_HEIGHT
        pygame.draw.rect(surface, ground, (0, ground_y, SCREEN_WIDTH, GROUND_HEIGHT))
        # Ground highlight line
        light_ground = _lerp_color(ground, (255, 255, 255), 0.25)
        pygame.draw.line(surface, light_ground, (0, ground_y), (SCREEN_WIDTH, ground_y), 2)

    def _draw_sun(self, surface, opacity):
        if opacity <= 0:
            return
        sx, sy = SCREEN_WIDTH - 60, 70
        alpha = int(255 * opacity)
        # Glow halo
        for r in range(30, 10, -4):
            glow_a = int(alpha * (1 - r / 32) * 0.4)
            glow_surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 240, 100, glow_a), (r, r), r)
            surface.blit(glow_surf, (sx - r, sy - r))
        sun_surf = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(sun_surf, (255, 248, 80, alpha), (12, 12), 12)
        surface.blit(sun_surf, (sx - 12, sy - 12))

    def _draw_moon(self, surface, opacity):
        if opacity <= 0:
            return
        mx, my = SCREEN_WIDTH - 70, 65
        alpha = int(220 * opacity)
        moon_surf = pygame.Surface((40, 40), pygame.SRCALPHA)
        pygame.draw.circle(moon_surf, (230, 230, 200, alpha), (20, 20), 18)
        # Crescent shadow
        pygame.draw.circle(moon_surf, (25, 25, 60, alpha), (28, 16), 14)
        surface.blit(moon_surf, (mx - 20, my - 20))
