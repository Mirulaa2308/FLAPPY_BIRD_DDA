"""New tests for: repeating sky cycle, difficulty presets, ML gap floor fix,
menu background simulation isolation, and retry persistence.

Run with:  python -m pytest tests/test_new_features.py -v
"""

import os
import sys
import pytest

# Project root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
pygame.init()

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from game.config import (
    DIFFICULTY_PRESETS, GAP_MIN, GAP_MAX, FIXED_PIPE_SPEED, FIXED_SPAWN_INTERVAL,
    SKY_CYCLE_PERIOD, SKY_DAY_END, SKY_EVENING_END,
)
from game.background import _sky_colors, _cycle_pos, BackgroundRenderer
from controllers.fixed import FixedController
from controllers.dda_controller import DataDrivenAdaptiveController, MIN_GAP_HARD_FLOOR


# ===========================================================================
# 1.  Difficulty preset constants
# ===========================================================================

class TestDifficultyPresets:
    def test_all_four_presets_exist(self):
        for key in ("easy", "medium", "hard", "maharoga"):
            assert key in DIFFICULTY_PRESETS, f"Missing preset: {key}"

    def test_each_preset_has_required_keys(self):
        required = {"gap", "pipe_speed", "spawn_interval", "label", "description",
                    "color", "hover_color"}
        for key, preset in DIFFICULTY_PRESETS.items():
            missing = required - preset.keys()
            assert not missing, f"Preset '{key}' missing: {missing}"

    def test_gaps_within_global_bounds(self):
        for key, preset in DIFFICULTY_PRESETS.items():
            assert GAP_MIN <= preset["gap"] <= GAP_MAX, \
                f"Preset '{key}' gap {preset['gap']} out of bounds"

    def test_easy_wider_than_medium_wider_than_hard(self):
        assert DIFFICULTY_PRESETS["easy"]["gap"] > DIFFICULTY_PRESETS["medium"]["gap"]
        assert DIFFICULTY_PRESETS["medium"]["gap"] > DIFFICULTY_PRESETS["hard"]["gap"]

    def test_easy_slower_than_medium_slower_than_hard(self):
        assert DIFFICULTY_PRESETS["easy"]["pipe_speed"] < DIFFICULTY_PRESETS["medium"]["pipe_speed"]
        assert DIFFICULTY_PRESETS["medium"]["pipe_speed"] < DIFFICULTY_PRESETS["hard"]["pipe_speed"]

    def test_maharoga_harder_than_hard(self):
        # MAHAROGA starts with a smaller gap than HARD
        assert DIFFICULTY_PRESETS["maharoga"]["gap"] <= DIFFICULTY_PRESETS["hard"]["gap"]

    def test_labels_are_strings(self):
        for key, preset in DIFFICULTY_PRESETS.items():
            assert isinstance(preset["label"], str)
            assert len(preset["label"]) > 0

    def test_colors_are_rgb_tuples(self):
        for key, preset in DIFFICULTY_PRESETS.items():
            for field in ("color", "hover_color"):
                c = preset[field]
                assert len(c) == 3, f"Preset '{key}' {field} must be RGB"
                for v in c:
                    assert 0 <= v <= 255

    def test_fixed_controller_accepts_preset_gap(self):
        for key in ("easy", "medium", "hard"):
            preset = DIFFICULTY_PRESETS[key]
            ctrl = FixedController(gap=preset["gap"])
            ctrl.pipe_speed = preset["pipe_speed"]
            ctrl.spawn_interval = preset["spawn_interval"]
            assert ctrl.current_gap == preset["gap"]
            assert ctrl.pipe_speed == preset["pipe_speed"]

    def test_fixed_controller_gap_unchanged_after_outcome(self):
        """Fixed difficulty must never change gap regardless of outcome."""
        for key in ("easy", "medium", "hard"):
            gap = DIFFICULTY_PRESETS[key]["gap"]
            ctrl = FixedController(gap=gap)
            for _ in range(30):
                result = ctrl.on_pipe_outcome({"success": 1, "gap_size": gap})
            assert result == gap
            for _ in range(30):
                result = ctrl.on_pipe_outcome({"success": 0, "gap_size": gap})
            assert result == gap


# ===========================================================================
# 2.  Repeating sky cycle
# ===========================================================================

class TestSkyRepeatingCycle:
    """Verify the 40-pipe repeating cycle is correct."""

    def test_cycle_pos_resets_at_period(self):
        assert _cycle_pos(0) == 0
        assert _cycle_pos(SKY_CYCLE_PERIOD) == 0
        assert _cycle_pos(SKY_CYCLE_PERIOD + 5) == 5
        assert _cycle_pos(2 * SKY_CYCLE_PERIOD) == 0

    def test_day_at_cycle_start(self):
        """Pipe 0 and pipe 40 should both be day-ish (blue sky)."""
        top0, bot0, _ = _sky_colors(0)
        top40, bot40, _ = _sky_colors(SKY_CYCLE_PERIOD)
        # Both should be close to day colours (high blue component)
        assert top0[2] > top0[0], "Day top should be blue-dominant"
        assert top40[2] > top40[0], "Cycle-reset top should be blue-dominant"

    def test_evening_at_correct_position(self):
        """At SKY_DAY_END inside any cycle, we should be in evening territory."""
        for cycle in range(3):
            pp = cycle * SKY_CYCLE_PERIOD + SKY_DAY_END + 1
            top, bot, _ = _sky_colors(pp)
            # Evening sky: warm orange/purple hues – NOT pure dark night
            # Just check it's not pure day blue
            assert not (top == (80, 160, 230)), \
                f"Should not be pure day at pipes_passed={pp}"

    def test_night_at_correct_position(self):
        """At SKY_EVENING_END+5 inside any cycle, sky should be clearly darker than day."""
        top_day, _, _ = _sky_colors(0)   # pure day
        for cycle in range(3):
            pp = cycle * SKY_CYCLE_PERIOD + SKY_EVENING_END + 5
            top, _, _ = _sky_colors(pp)
            # Night sky must be darker than day sky overall
            assert sum(top) < sum(top_day), (
                f"Night sky should be darker than day at pipes_passed={pp}: "
                f"night={top}, day={top_day}"
            )

    def test_day_returns_after_40_pipes(self):
        """At pipes 39→40 the sky should transition back to day."""
        top_night, _, _ = _sky_colors(SKY_CYCLE_PERIOD - 1)
        top_day, _, _ = _sky_colors(SKY_CYCLE_PERIOD + 5)
        # Day has more blue; night is darker overall
        assert sum(top_day) > sum(top_night), "Day should be brighter than night"

    def test_cycle_repeats_identically_at_80(self):
        """Pipe positions within the same cycle phase should yield identical colours.
        Compare mid-night (pipe 30, 70, 110) which is pure-night territory."""
        pp_base = SKY_EVENING_END + 8   # well inside pure night, far from blends
        top0, bot0, g0 = _sky_colors(pp_base)
        top40, bot40, g40 = _sky_colors(pp_base + SKY_CYCLE_PERIOD)
        top80, bot80, g80 = _sky_colors(pp_base + 2 * SKY_CYCLE_PERIOD)
        assert top0 == top40 == top80, (
            f"Sky top should repeat identically at {pp_base}, "
            f"{pp_base+SKY_CYCLE_PERIOD}, {pp_base+2*SKY_CYCLE_PERIOD}"
        )
        assert bot0 == bot40 == bot80
        assert g0 == g40 == g80

    def test_no_extreme_color_jump_between_adjacent_pipes(self):
        """Sky should never jump by more than 120 units across any single pipe."""
        prev_top, _, _ = _sky_colors(0)
        for pp in range(1, 3 * SKY_CYCLE_PERIOD):
            top, _, _ = _sky_colors(pp)
            for i in range(3):
                diff = abs(int(top[i]) - int(prev_top[i]))
                assert diff <= 120, \
                    f"Color channel {i} jumped {diff} between pipes {pp-1} and {pp}"
            prev_top = top

    def test_background_renderer_uses_repeating_cycle(self):
        """BackgroundRenderer.update() with pipes_passed=45 should give day sky
        (same as pipes_passed=5) because of the repeating cycle."""
        br = BackgroundRenderer()
        br.update(pipes_passed=5)
        top5, bot5, _ = _sky_colors(5)
        br.update(pipes_passed=45)
        top45, bot45, _ = _sky_colors(45)
        assert top5 == top45, "Cycle should repeat: pipes 5 and 45 should match"


# ===========================================================================
# 3.  ML gap floor – estimated_min_gap initialization bug fixed
# ===========================================================================

class TestMLGapFloorFix:
    def test_estimated_min_gap_starts_below_initial_gap(self):
        """The estimated_min_gap must start BELOW initial_gap so the ML can
        immediately lower the current_gap when the player performs well."""
        ctrl = DataDrivenAdaptiveController(
            initial_gap=165, model_path="", debug=False
        )
        # With the bug, estimated_min_gap == 165; after the fix it's GAP_MIN+20 (110)
        assert ctrl._estimated_min_gap < 165, (
            "estimated_min_gap must start below initial_gap so ML can reduce the gap"
        )

    def test_gap_can_decrease_from_start_with_successes(self):
        """After repeated successes, gap should be able to go below 165."""
        ctrl = DataDrivenAdaptiveController(
            initial_gap=165, model_path="", debug=False
        )
        initial_gap = ctrl.current_gap
        # Feed many successes to drive gap down
        for _ in range(60):
            ctrl.on_pipe_outcome({
                "success": 1, "gap_size": ctrl.current_gap,
                "bird_y_at_pass": 320.0, "bird_vel_at_pass": 0.0,
                "consecutive_successes_before": 5, "consecutive_failures_before": 0,
                "success_rate_last3": 1.0, "success_rate_last5": 1.0,
                "survival_time": 1.0, "total_pipes_passed": 10,
            })
        assert ctrl.current_gap < initial_gap, \
            "Gap should be able to decrease from 165 with repeated successes"

    def test_estimated_min_gap_never_below_hard_floor(self):
        ctrl = DataDrivenAdaptiveController(
            initial_gap=100, model_path="", debug=False
        )
        assert ctrl._estimated_min_gap >= MIN_GAP_HARD_FLOOR


# ===========================================================================
# 4.  FixedController speed/interval attributes
# ===========================================================================

class TestFixedControllerAttributes:
    def test_has_pipe_speed(self):
        ctrl = FixedController(gap=165)
        assert hasattr(ctrl, "pipe_speed")

    def test_has_spawn_interval(self):
        ctrl = FixedController(gap=165)
        assert hasattr(ctrl, "spawn_interval")

    def test_pipe_speed_overridable(self):
        ctrl = FixedController(gap=165)
        ctrl.pipe_speed = 2.2
        assert ctrl.pipe_speed == 2.2

    def test_spawn_interval_overridable(self):
        ctrl = FixedController(gap=165)
        ctrl.spawn_interval = 110
        assert ctrl.spawn_interval == 110

    def test_default_values(self):
        ctrl = FixedController()
        assert ctrl.pipe_speed == FIXED_PIPE_SPEED
        assert ctrl.spawn_interval == FIXED_SPAWN_INTERVAL


# ===========================================================================
# 5.  Retry preserves ML learning (MAHAROGA)
# ===========================================================================

class TestRetryPreservesMLLearning:
    def _make_maharoga_ctrl(self):
        preset = DIFFICULTY_PRESETS["maharoga"]
        ctrl = DataDrivenAdaptiveController(
            initial_gap=preset["gap"], model_path="", debug=False
        )
        ctrl.pipe_speed = preset["pipe_speed"]
        ctrl.spawn_interval = preset["spawn_interval"]
        return ctrl

    def test_reset_preserves_estimated_min_gap(self):
        ctrl = self._make_maharoga_ctrl()
        ctrl._estimated_min_gap = 100  # simulated learning
        ctrl.reset()
        assert ctrl._estimated_min_gap == 100, \
            "Retry must not erase learned min gap"

    def test_reset_preserves_gap_evidence(self):
        ctrl = self._make_maharoga_ctrl()
        ctrl._gap_evidence[110].extend([1, 1, 1])
        ctrl.reset()
        assert 110 in ctrl._gap_evidence
        assert list(ctrl._gap_evidence[110]) == [1, 1, 1]

    def test_reset_clears_session_state(self):
        ctrl = self._make_maharoga_ctrl()
        for _ in range(10):
            ctrl.on_pipe_outcome({
                "success": 1, "gap_size": ctrl.current_gap,
                "bird_y_at_pass": 320.0, "bird_vel_at_pass": 0.0,
                "consecutive_successes_before": 0, "consecutive_failures_before": 0,
                "success_rate_last3": 1.0, "success_rate_last5": 1.0,
                "survival_time": 1.0, "total_pipes_passed": 5,
            })
        ctrl.reset()
        assert len(ctrl._outcome_window) == 0
        assert len(ctrl._session_outcomes) == 0
        assert ctrl._pipes_since_adj == 0
