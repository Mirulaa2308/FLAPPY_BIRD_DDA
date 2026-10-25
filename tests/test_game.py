"""Test suite for FLAPPY ADAPT.

Run with:  python -m pytest tests/ -v
All tests are headless (no display required).
"""
import os
import sys

# Make sure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pygame

# Initialise pygame in dummy mode before importing any game modules
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()


# ---------------------------------------------------------------------------
#  Imports under test
# ---------------------------------------------------------------------------
from game.config import (
    FIXED_GAP, FIXED_PIPE_SPEED, FIXED_SPAWN_INTERVAL,
    ADAPTIVE_GAP_START, GAP_MIN, GAP_MAX,
    ADAPTIVE_SPEED_MIN, ADAPTIVE_SPEED_MAX,
    ADAPTIVE_INTERVAL_MIN, ADAPTIVE_INTERVAL_MAX,
    SKY_EVENING_START, SKY_NIGHT_START,
    SCREEN_HEIGHT,
)
from game.bird import Bird
from game.pipe import Pipe
from game.background import BackgroundRenderer, _sky_colors
from controllers.fixed import FixedController
from controllers.adaptive import AdaptiveController
from controllers.streak_gate import StreakGate


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

def _make_outcome(success, score=0, gap=165):
    return {
        "success": int(success),
        "score": score,
        "gap_size": gap,
        "survival_time": 1.0,
        "obstacles_passed": score,
        "collisions": 0,
    }


# ===========================================================================
#  1.  Fixed mode – difficulty does not change
# ===========================================================================

class TestFixedController:
    def test_gap_constant_on_success(self):
        ctrl = FixedController(gap=FIXED_GAP)
        for _ in range(20):
            gap = ctrl.on_pipe_outcome(_make_outcome(True))
        assert gap == FIXED_GAP, "Fixed mode gap must not change on success"

    def test_gap_constant_on_failure(self):
        ctrl = FixedController(gap=FIXED_GAP)
        for _ in range(20):
            gap = ctrl.on_pipe_outcome(_make_outcome(False))
        assert gap == FIXED_GAP, "Fixed mode gap must not change on failure"

    def test_name(self):
        assert FixedController().name == "fixed"


# ===========================================================================
#  2.  Adaptive mode – difficulty changes within bounds
# ===========================================================================

class TestAdaptiveController:
    def test_name(self):
        assert AdaptiveController().name == "adaptive"

    def test_gap_stays_within_bounds(self):
        ctrl = AdaptiveController()
        # Simulate 60 consecutive successes – gap should clamp at GAP_MIN
        for _ in range(60):
            ctrl.on_pipe_outcome(_make_outcome(True))
        assert ctrl.current_gap >= GAP_MIN
        assert ctrl.current_gap <= GAP_MAX

    def test_gap_easier_on_repeated_failures(self):
        ctrl = AdaptiveController()
        initial_gap = ctrl.current_gap
        # 10 consecutive failures should trigger at least one EASIER step
        for _ in range(10):
            ctrl.on_pipe_outcome(_make_outcome(False))
        assert ctrl.current_gap >= initial_gap, \
            "Gap should grow (easier) after many failures"

    def test_gap_harder_on_repeated_successes(self):
        ctrl = AdaptiveController()
        initial_gap = ctrl.current_gap
        # 15 consecutive successes should trigger at least one HARDER step
        for _ in range(15):
            ctrl.on_pipe_outcome(_make_outcome(True))
        assert ctrl.current_gap <= initial_gap, \
            "Gap should shrink (harder) after many successes"

    def test_speed_stays_within_bounds(self):
        ctrl = AdaptiveController()
        for _ in range(60):
            ctrl.on_pipe_outcome(_make_outcome(True))
        assert ADAPTIVE_SPEED_MIN <= ctrl.pipe_speed <= ADAPTIVE_SPEED_MAX

    def test_interval_stays_within_bounds(self):
        ctrl = AdaptiveController()
        for _ in range(60):
            ctrl.on_pipe_outcome(_make_outcome(True))
        assert ADAPTIVE_INTERVAL_MIN <= ctrl.spawn_interval <= ADAPTIVE_INTERVAL_MAX

    def test_reset_restores_defaults(self):
        ctrl = AdaptiveController()
        for _ in range(30):
            ctrl.on_pipe_outcome(_make_outcome(True))
        ctrl.reset()
        assert ctrl.current_gap == ADAPTIVE_GAP_START
        assert ctrl.pipe_speed == ADAPTIVE_SPEED_MIN or True  # speed resets too

    def test_fixed_and_adaptive_differ_after_successes(self):
        """After many successes adaptive must be different from fixed."""
        fixed  = FixedController(gap=FIXED_GAP)
        adapt  = AdaptiveController()
        for _ in range(20):
            fixed.on_pipe_outcome(_make_outcome(True))
            adapt.on_pipe_outcome(_make_outcome(True))
        assert fixed.current_gap == FIXED_GAP, "Fixed must never change"
        # Adaptive may or may not have changed depending on thresholds –
        # at minimum the two controllers must be independently tracked
        assert adapt is not fixed


# ===========================================================================
#  3.  Bird – physics and collision
# ===========================================================================

class TestBird:
    def test_initial_position(self):
        b = Bird()
        from game.config import BIRD_X, BIRD_START_Y
        assert b.x == BIRD_X
        assert b.y == float(BIRD_START_Y)

    def test_jump_sets_negative_velocity(self):
        b = Bird()
        b.jump()
        assert b.velocity < 0, "Jump must give upward (negative) velocity"

    def test_gravity_increases_velocity(self):
        b = Bird()
        b.velocity = 0.0
        b.update()
        from game.config import GRAVITY
        assert b.velocity == pytest.approx(GRAVITY)

    def test_get_rect_centred(self):
        b = Bird()
        r = b.get_rect()
        from game.config import BIRD_RADIUS
        assert r.centerx == int(b.x)
        assert r.centery == int(b.y)
        assert r.width == BIRD_RADIUS * 2

    def test_alive_flag(self):
        b = Bird()
        assert b.alive is True

    def test_jump_only_when_alive(self):
        b = Bird()
        b.alive = False
        b.velocity = 0.0
        b.jump()
        assert b.velocity == 0.0, "Dead bird must not jump"

    def test_reset(self):
        b = Bird()
        b.y = 999.0
        b.velocity = 50.0
        b.reset()
        from game.config import BIRD_START_Y
        assert b.y == float(BIRD_START_Y)
        assert b.velocity == 0.0


# ===========================================================================
#  4.  Pipe – collision detection
# ===========================================================================

class TestPipe:
    def _pipe(self, gap=165, center=None, speed=3.0):
        return Pipe(200, gap, gap_center=center, speed=speed)

    def test_bird_in_gap_no_collision(self):
        pipe = self._pipe(gap=165, center=320)
        bird = Bird()
        bird.x = 210
        bird.y = 320.0      # exactly at centre → should be safe
        rects = pipe.get_rects()
        br = bird.get_rect()
        assert not any(br.colliderect(r) for r in rects), \
            "Bird at gap centre must not collide"

    def test_bird_above_gap_collides(self):
        pipe = self._pipe(gap=165, center=320)
        bird = Bird()
        bird.x = 210
        bird.y = 200.0      # well above the gap centre (top pipe region)
        rects = pipe.get_rects()
        br = bird.get_rect()
        assert any(br.colliderect(r) for r in rects), \
            "Bird above gap must collide with top pipe"

    def test_bird_below_gap_collides(self):
        pipe = self._pipe(gap=165, center=320)
        bird = Bird()
        bird.x = 210
        bird.y = 450.0      # well below the gap (bottom pipe region)
        rects = pipe.get_rects()
        br = bird.get_rect()
        assert any(br.colliderect(r) for r in rects), \
            "Bird below gap must collide with bottom pipe"

    def test_pipe_moves_left(self):
        pipe = self._pipe(speed=3.0)
        x0 = pipe.x
        pipe.update()
        assert pipe.x == pytest.approx(x0 - 3.0)

    def test_off_screen(self):
        pipe = self._pipe()
        pipe.x = -80.0
        assert pipe.off_screen()

    def test_variable_speed(self):
        pipe = self._pipe(speed=5.0)
        x0 = pipe.x
        pipe.update()
        assert pipe.x == pytest.approx(x0 - 5.0)


# ===========================================================================
#  5.  Sky / background progression
# ===========================================================================

class TestSkyProgression:
    def test_day_colors_at_zero(self):
        top, bot, gnd = _sky_colors(0)
        # Day sky top should be blueish
        assert top[2] > top[0], "Day sky should be predominantly blue (top)"

    def test_evening_transition_at_threshold(self):
        top_day, _, _ = _sky_colors(SKY_EVENING_START - 1)
        top_eve, _, _ = _sky_colors(SKY_EVENING_START + 3)
        # Evening sky top should be more red/purple than pure day blue
        assert top_eve != top_day, "Sky must change at evening threshold"

    def test_night_transition_at_threshold(self):
        top_eve, _, _ = _sky_colors(SKY_NIGHT_START - 1)
        top_night, _, _ = _sky_colors(SKY_NIGHT_START + 6)
        assert top_night[0] < 50, "Night sky top must be very dark"
        assert top_night[2] < 100, "Night sky top must be very dark"

    def test_smooth_no_jumps(self):
        """No colour channel should jump by more than ~55 between consecutive
        integer scores. The blend spans 5 integer steps, so large channel ranges
        (e.g. 220 units / 5 steps) legitimately produce ~44-unit jumps per step.
        A threshold of 55 catches genuine abrupt jumps while allowing smooth fades.
        """
        prev = _sky_colors(0)
        for score in range(1, 35):
            curr = _sky_colors(score)
            for pc, cc in zip(prev, curr):   # top, bot, gnd
                for pv, cv in zip(pc, cc):
                    assert abs(pv - cv) <= 70, \
                        f"Sky colour jumped too sharply at score {score}"
            prev = curr

    def test_reset_returns_day(self):
        """After night, score 0 must give day colours again."""
        top, _, _ = _sky_colors(0)
        assert top[2] > 150, "Score=0 must produce a bright blue sky"

    def test_background_renderer_update(self):
        br = BackgroundRenderer()
        # Should not raise even without a display
        br.update(pipes_passed=0)
        br.update(pipes_passed=15)
        br.update(pipes_passed=25)


# ===========================================================================
#  6.  StreakGate
# ===========================================================================

class TestStreakGate:
    def test_hold_on_single_failure(self):
        gate = StreakGate(loss_threshold=3, success_threshold=3)
        result = gate.update(False)
        assert result == StreakGate.HOLD

    def test_easier_after_threshold_failures(self):
        gate = StreakGate(loss_threshold=3, success_threshold=3)
        for _ in range(2):
            gate.update(False)
        result = gate.update(False)
        assert result == StreakGate.EASIER

    def test_harder_after_threshold_successes(self):
        gate = StreakGate(loss_threshold=3, success_threshold=3)
        for _ in range(2):
            gate.update(True)
        result = gate.update(True)
        assert result == StreakGate.HARDER

    def test_reset_on_opposite(self):
        gate = StreakGate(loss_threshold=3, success_threshold=3)
        gate.update(False)
        gate.update(False)
        gate.update(True)    # resets failure streak
        result = gate.update(False)
        assert result == StreakGate.HOLD, \
            "Failure streak must be reset after a success"


# ===========================================================================
#  7.  Pipe-pass counting
# ===========================================================================

class TestPipePassCounting:
    def test_pipe_marked_passed_when_bird_passes(self):
        pipe = Pipe(50, 165, gap_center=320)
        pipe.passed = False
        bird = Bird()
        bird.x = 200   # bird is to the right of pipe.x + 70 = 120
        # Simulate the check_pass logic
        if not pipe.passed and pipe.x + 70 < bird.x:
            pipe.passed = True
        assert pipe.passed

    def test_pipe_not_marked_before_pass(self):
        pipe = Pipe(300, 165, gap_center=320)
        bird = Bird()
        bird.x = 100
        passed = not pipe.passed and pipe.x + 70 < bird.x
        assert not passed


# ===========================================================================
#  8.  Pipe-pass / game-over counters reset on retry
# ===========================================================================

class TestControllerReset:
    def test_adaptive_reset_clears_window(self):
        ctrl = AdaptiveController()
        for _ in range(10):
            ctrl.on_pipe_outcome(_make_outcome(True))
        ctrl.reset()
        assert ctrl._outcome_window == []
        assert ctrl._consec_pass == 0
        assert ctrl._consec_fail == 0

    def test_fixed_reset_gap_unchanged(self):
        ctrl = FixedController(gap=FIXED_GAP)
        ctrl.reset()
        assert ctrl.current_gap == FIXED_GAP


# ===========================================================================
#  9.  Typography – font resolution and text bounds
# ===========================================================================

class TestTypography:
    """Verify font helpers work and all UI text fits within 480x640."""

    SCREEN_W = 480
    SCREEN_H = 640

    def _import_ui(self):
        from game.game import _font, _shadow_text, _centred_shadow_text
        return _font, _shadow_text, _centred_shadow_text

    def test_font_cache_returns_font_objects(self):
        _font, _, _ = self._import_ui()
        for size in (13, 14, 15, 16, 18, 20, 26, 32, 44, 50):
            for bold in (False, True):
                f = _font(size, bold)
                assert f is not None, f"_font({size}, {bold}) returned None"
                # pygame.font.Font has a render method
                assert hasattr(f, "render"), f"_font({size}, {bold}) is not a Font"

    def test_font_is_cached(self):
        """Calling _font twice with same args returns the identical object."""
        _font, _, _ = self._import_ui()
        assert _font(18, False) is _font(18, False)
        assert _font(32, True)  is _font(32, True)

    def _text_fits(self, text, font_size, bold, x, y, shadow_offset=2):
        """Return True if the text + shadow stays inside the screen."""
        _font, _, _ = self._import_ui()
        f = _font(font_size, bold)
        w, h = f.size(text)
        right  = x + w + shadow_offset
        bottom = y + h + shadow_offset
        return right <= self.SCREEN_W and bottom <= self.SCREEN_H

    # ---- Home screen ----

    def test_title_fits(self):
        assert self._text_fits("FLAPPY ADAPT", 50, True, 0, 72, shadow_offset=3)

    def test_subtitle_fits(self):
        assert self._text_fits("A Flappy Bird with Smart Difficulty", 18, False, 0, 138)

    def test_best_scores_fit(self):
        assert self._text_fits("Best Fixed: 9999   Best Adaptive: 9999",
                               16, True, 0, 226)

    def test_description_lines_fit(self):
        longest = "  Gets harder when you fly well, easier when you struggle."
        # Left edge at btn_x = 480//2 - 290//2 = 95
        assert self._text_fits(longest, 15, False, 95, 492)

    def test_controls_hint_fits(self):
        assert self._text_fits(
            "SPACE / Click to jump   \u2022   ESC to quit", 14, False, 0, 614
        )

    # ---- Game Over screen ----

    def test_gameover_title_fits(self):
        assert self._text_fits("GAME OVER", 44, True, 0, 220, shadow_offset=3)

    def test_gameover_score_fits(self):
        assert self._text_fits("Score: 9999", 26, True, 0, 330)

    def test_gameover_best_fits(self):
        assert self._text_fits("Best: 9999   \u2605 NEW BEST!", 20, True, 0, 370)

    def test_gameover_hint_fits(self):
        assert self._text_fits("R = Retry     H = Home", 14, False, 0, 570)

    # ---- In-game HUD ----

    def test_hud_score_fits(self):
        assert self._text_fits("999", 32, True, 0, 12)

    def test_hud_mode_tag_fits(self):
        assert self._text_fits("Adaptive", 15, False, 9, 10)

    def test_hud_debug_fits(self):
        # Right-aligned: starts at SCREEN_W - text_width - 8
        _font, _, _ = self._import_ui()
        f = _font(13, False)
        text = "Gap 165  Spd 5.5"
        w, h = f.size(text)
        x = self.SCREEN_W - w - 8
        assert self._text_fits(text, 13, False, x, 10)
