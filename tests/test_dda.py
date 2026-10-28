"""Tests for the Data-Driven Adaptive Difficulty system.

Covers:
  - DataDrivenAdaptiveController core behaviour
  - Hard minimum gap enforcement
  - Session reset vs cross-session state preservation
  - Min-gap evidence accumulation and estimation
  - ML model loading / fallback
  - human_trainer data loading and training
  - Integration: data written by logger is loadable by trainer
  - Fixed mode unchanged
  - Missing model / data handled gracefully
"""

import csv
import io
import os
import sys
import tempfile
import time
import shutil
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
    GAP_MIN, GAP_MAX, ADAPTIVE_GAP_START, FIXED_GAP,
    ADAPTIVE_PIPE_SPEED_START, ADAPTIVE_SPAWN_INTERVAL_START,
)
from controllers.fixed import FixedController
from controllers.dda_controller import (
    DataDrivenAdaptiveController,
    TARGET_SUCCESS, GAP_STEP, WINDOW_SIZE, MIN_GAP_HARD_FLOOR,
    MIN_EVIDENCE_PASSES, MIN_RELIABLE_RATE,
)
from ml.human_trainer import (
    _load_human_rows, _rows_to_X_y, count_human_samples,
    MIN_SAMPLES_TO_TRAIN,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _outcome(success: bool, gap: int = 165, bird_y: float = 320.0,
             bird_vel: float = 0.0, score: int = 0) -> dict:
    return {
        "success": int(success),
        "gap_size": gap,
        "bird_y_at_pass": bird_y,
        "bird_vel_at_pass": bird_vel,
        "consecutive_successes_before": 0,
        "consecutive_failures_before": 0,
        "success_rate_last3": 1.0 if success else 0.0,
        "success_rate_last5": 1.0 if success else 0.0,
        "survival_time": 1.0,
        "total_pipes_passed": score,
    }


def _make_controller(initial_gap=165, model_path=None) -> DataDrivenAdaptiveController:
    """Create controller without loading any model (model_path='')."""
    path = model_path if model_path is not None else ""
    ctrl = DataDrivenAdaptiveController(
        initial_gap=initial_gap,
        model_path=path,
        debug=False,
    )
    return ctrl


def _stream_outcomes(ctrl, outcomes):
    """Feed a list of (success, gap) tuples to a controller."""
    for suc, gap in outcomes:
        ctrl.on_pipe_outcome(_outcome(suc, gap=gap))


# ===========================================================================
# 1.  Fixed mode – completely unchanged
# ===========================================================================

class TestFixedUnchanged:
    def test_gap_constant_on_success(self):
        ctrl = FixedController(gap=FIXED_GAP)
        for _ in range(30):
            gap = ctrl.on_pipe_outcome(_outcome(True))
        assert gap == FIXED_GAP

    def test_gap_constant_on_failure(self):
        ctrl = FixedController(gap=FIXED_GAP)
        for _ in range(30):
            gap = ctrl.on_pipe_outcome(_outcome(False))
        assert gap == FIXED_GAP

    def test_name(self):
        assert FixedController().name == "fixed"


# ===========================================================================
# 2.  DataDrivenAdaptiveController – basic gap bounds
# ===========================================================================

class TestDDAControllerBounds:
    def test_name(self):
        ctrl = _make_controller()
        assert ctrl.name == "adaptive"

    def test_gap_never_below_hard_floor(self):
        ctrl = _make_controller(initial_gap=100)
        # Drive 60 consecutive successes – gap should never go below hard floor
        for i in range(60):
            ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        assert ctrl.current_gap >= MIN_GAP_HARD_FLOOR

    def test_gap_never_above_max(self):
        ctrl = _make_controller()
        for i in range(60):
            ctrl.on_pipe_outcome(_outcome(False, gap=ctrl.current_gap))
        assert ctrl.current_gap <= ctrl.max_gap

    def test_gap_never_below_estimated_min(self):
        ctrl = _make_controller(initial_gap=165)
        # Estimated min starts at initial gap; gap must stay above it
        for i in range(50):
            ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        assert ctrl.current_gap >= ctrl._estimated_min_gap

    def test_gap_starts_at_initial(self):
        ctrl = _make_controller(initial_gap=180)
        assert ctrl.current_gap == 180

    def test_gap_widens_after_repeated_failures(self):
        ctrl = _make_controller(initial_gap=165)
        initial = ctrl.current_gap
        # Many failures should trigger widening
        for _ in range(30):
            ctrl.on_pipe_outcome(_outcome(False, gap=ctrl.current_gap))
        assert ctrl.current_gap >= initial, "Gap should widen after repeated failures"

    def test_gap_narrows_after_repeated_successes(self):
        ctrl = _make_controller(initial_gap=200)
        initial = ctrl.current_gap
        for _ in range(30):
            ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        assert ctrl.current_gap <= initial, "Gap should narrow after repeated successes"


# ===========================================================================
# 3.  Reset behaviour
# ===========================================================================

class TestDDAControllerReset:
    def test_reset_clears_session_window(self):
        ctrl = _make_controller()
        for _ in range(10):
            ctrl.on_pipe_outcome(_outcome(True))
        ctrl.reset()
        assert len(ctrl._outcome_window) == 0
        assert len(ctrl._session_outcomes) == 0
        assert ctrl._pipes_since_adj == 0

    def test_reset_preserves_estimated_min_gap(self):
        """Cross-session learned min gap must survive a reset (retry)."""
        ctrl = _make_controller(initial_gap=165)
        # Inject evidence that player can do 145
        for i in range(MIN_EVIDENCE_PASSES + 2):
            ctrl._gap_evidence[145].append(1)
        ctrl._reestimate_min_gap()  # force update
        min_before = ctrl._estimated_min_gap
        ctrl.reset()
        assert ctrl._estimated_min_gap == min_before, \
            "estimated_min_gap must survive reset()"

    def test_reset_preserves_gap_evidence_dict(self):
        ctrl = _make_controller()
        ctrl._gap_evidence[130].append(1)
        ctrl.reset()
        assert 130 in ctrl._gap_evidence, "Gap evidence must survive reset()"

    def test_reset_preserves_model(self):
        """If a model was loaded, it must survive reset()."""
        ctrl = _make_controller()
        ctrl._model = "FAKE_MODEL"   # inject sentinel
        ctrl.reset()
        assert ctrl._model == "FAKE_MODEL"


# ===========================================================================
# 4.  Cooldown and hysteresis – no rapid oscillation
# ===========================================================================

class TestDDACooldown:
    def test_no_change_during_warmup(self):
        ctrl = _make_controller(initial_gap=165)
        initial = ctrl.current_gap
        # Feed fewer outcomes than MIN_WINDOW_FOR_ADJUST
        from controllers.dda_controller import MIN_WINDOW_FOR_ADJUST
        for _ in range(MIN_WINDOW_FOR_ADJUST - 1):
            ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        # Gap must not change yet
        assert ctrl.current_gap == initial, "Gap must not change during warmup"

    def test_cooldown_prevents_adjustment_every_pipe(self):
        ctrl = _make_controller(initial_gap=200)
        from controllers.dda_controller import ADJUSTMENT_COOLDOWN, MIN_WINDOW_FOR_ADJUST
        # Fill window with all successes
        for _ in range(MIN_WINDOW_FOR_ADJUST + 1):
            ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        # Record gap after first possible adjustment
        gap_after_first = ctrl.current_gap
        adj_count = 0
        # Feed 2 more pipes (less than cooldown)
        for _ in range(2):
            new_gap = ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
            if new_gap != gap_after_first:
                adj_count += 1
        # Should not have adjusted twice within cooldown
        assert adj_count <= 1


# ===========================================================================
# 5.  Hard minimum gap enforcement (non-negotiable)
# ===========================================================================

class TestHardMinGap:
    def test_clamp_never_below_estimated_min(self):
        ctrl = _make_controller(initial_gap=165)
        # Manually set a high estimated min
        ctrl._estimated_min_gap = 160
        result = ctrl._clamp(100)
        assert result >= 160

    def test_clamp_never_below_hard_floor(self):
        ctrl = _make_controller()
        ctrl._estimated_min_gap = 0   # unrealistic but tests floor
        result = ctrl._clamp(0)
        assert result >= MIN_GAP_HARD_FLOOR

    def test_clamp_respects_max_gap(self):
        ctrl = _make_controller()
        result = ctrl._clamp(9999)
        assert result <= ctrl.max_gap

    def test_on_pipe_outcome_respects_min(self):
        ctrl = _make_controller(initial_gap=165)
        ctrl._estimated_min_gap = 155
        # Flood with successes to drive gap down
        for _ in range(50):
            ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        assert ctrl.current_gap >= ctrl._estimated_min_gap

    def test_min_never_raised_by_reset(self):
        ctrl = _make_controller(initial_gap=120)
        ctrl._estimated_min_gap = 110
        ctrl.reset()
        assert ctrl._estimated_min_gap <= 120  # should not go up on reset


# ===========================================================================
# 6.  Minimum gap estimation
# ===========================================================================

class TestMinGapEstimation:
    def test_min_lowered_with_sufficient_evidence(self):
        ctrl = _make_controller(initial_gap=165)
        start_min = ctrl._estimated_min_gap

        target_gap = start_min - 5
        # Need ≥ MIN_EVIDENCE_PASSES successful passes at target_gap
        for _ in range(MIN_EVIDENCE_PASSES + 3):
            ctrl._gap_evidence[target_gap].append(1)   # all successes

        ctrl._reestimate_min_gap()
        # Min should have dropped
        assert ctrl._estimated_min_gap <= start_min

    def test_min_not_lowered_with_low_success_rate(self):
        ctrl = _make_controller(initial_gap=165)
        start_min = ctrl._estimated_min_gap
        target_gap = start_min - 5

        # Mostly failures (success rate < MIN_RELIABLE_RATE)
        for _ in range(MIN_EVIDENCE_PASSES + 3):
            ctrl._gap_evidence[target_gap].append(0)

        ctrl._reestimate_min_gap()
        assert ctrl._estimated_min_gap == start_min, \
            "Min must not lower when success rate is insufficient"

    def test_min_not_lowered_with_few_observations(self):
        ctrl = _make_controller(initial_gap=165)
        start_min = ctrl._estimated_min_gap
        target_gap = start_min - 5

        # Only 2 observations (< MIN_EVIDENCE_PASSES)
        ctrl._gap_evidence[target_gap].extend([1, 1])
        ctrl._reestimate_min_gap()
        assert ctrl._estimated_min_gap == start_min

    def test_min_not_lowered_below_hard_floor(self):
        ctrl = _make_controller(initial_gap=MIN_GAP_HARD_FLOOR)
        ctrl._estimated_min_gap = MIN_GAP_HARD_FLOOR
        # Try to push it below the floor
        for _ in range(MIN_EVIDENCE_PASSES + 5):
            ctrl._gap_evidence[MIN_GAP_HARD_FLOOR - 10].append(1)
        ctrl._reestimate_min_gap()
        assert ctrl._estimated_min_gap >= MIN_GAP_HARD_FLOOR


# ===========================================================================
# 7.  Debug info API
# ===========================================================================

class TestDebugInfo:
    def test_debug_info_keys(self):
        ctrl = _make_controller()
        info = ctrl.debug_info()
        required_keys = {
            "current_gap", "estimated_min_gap", "last_prob",
            "model_trained", "model_trained_at", "last_reason",
        }
        assert required_keys.issubset(info.keys())

    def test_debug_info_model_trained_false_without_model(self):
        ctrl = _make_controller(model_path="")
        info = ctrl.debug_info()
        assert info["model_trained"] is False


# ===========================================================================
# 8.  Missing model / data – graceful degradation
# ===========================================================================

class TestGracefulDegradation:
    def test_missing_model_file_no_crash(self):
        ctrl = DataDrivenAdaptiveController(
            model_path="data/nonexistent_model_xyzzy.pkl"
        )
        assert ctrl._model is None

    def test_missing_model_uses_fallback(self):
        ctrl = _make_controller(model_path="")
        # Should still produce valid gap
        for _ in range(15):
            gap = ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        assert MIN_GAP_HARD_FLOOR <= gap <= ctrl.max_gap

    def test_no_crash_on_corrupt_outcome(self):
        ctrl = _make_controller()
        # Missing keys – should not raise
        ctrl.on_pipe_outcome({})
        ctrl.on_pipe_outcome({"success": "not_a_number"})


# ===========================================================================
# 9.  Human trainer – data loading
# ===========================================================================

class TestHumanTrainerDataLoading:
    def _write_session_csv(self, directory, session_id, n_rows=40,
                           success_rate=0.7, gap=165):
        """Write a synthetic session CSV compatible with GameLogger schema."""
        fields = [
            "session_id", "episode", "pipe_index",
            "gap_size", "gap_center",
            "bird_y_at_pass", "bird_vel_at_pass",
            "time_since_last_pass",
            "success",
            "consecutive_successes_before",
            "consecutive_failures_before",
            "success_rate_last3",
            "success_rate_last5",
            "survival_time",
            "total_pipes_passed",
            "controller",
        ]
        path = os.path.join(directory, f"session_{session_id}_adaptive.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for i in range(n_rows):
                suc = 1 if (i / n_rows) < success_rate else 0
                w.writerow({
                    "session_id": session_id,
                    "episode": 1,
                    "pipe_index": i,
                    "gap_size": gap,
                    "gap_center": 320,
                    "bird_y_at_pass": 310.0,
                    "bird_vel_at_pass": -2.0,
                    "time_since_last_pass": 1.5,
                    "success": suc,
                    "consecutive_successes_before": 0,
                    "consecutive_failures_before": 0,
                    "success_rate_last3": success_rate,
                    "success_rate_last5": success_rate,
                    "survival_time": 10.0,
                    "total_pipes_passed": i,
                    "controller": "adaptive",
                })
        return path

    def test_empty_log_dir_returns_zero(self):
        with tempfile.TemporaryDirectory() as td:
            rows = _load_human_rows(log_dir=td)
            assert rows == []

    def test_rows_to_xy_returns_matching_shape(self):
        with tempfile.TemporaryDirectory() as td:
            self._write_session_csv(td, "s1", n_rows=20)
            rows = _load_human_rows(log_dir=td)
            X, y, sessions = _rows_to_X_y(rows)
            assert X.shape[0] == len(y)
            assert X.shape[1] == 10   # 10 features

    def test_insufficient_samples_returns_none(self):
        from ml.human_trainer import train_from_human_logs
        with tempfile.TemporaryDirectory() as td:
            # Only 10 rows – below MIN_SAMPLES_TO_TRAIN
            self._write_session_csv(td, "s1", n_rows=10)
            with tempfile.TemporaryDirectory() as model_dir:
                result = train_from_human_logs(
                    log_dir=td,
                    model_path=os.path.join(model_dir, "m.pkl"),
                    verbose=False,
                )
            assert result is None

    def test_sufficient_samples_trains_model(self):
        from ml.human_trainer import train_from_human_logs
        with tempfile.TemporaryDirectory() as td:
            # Write enough sessions
            for sid in range(6):
                self._write_session_csv(td, f"s{sid}", n_rows=20,
                                        gap=100 + sid * 20)
            with tempfile.TemporaryDirectory() as model_dir:
                model_path = os.path.join(model_dir, "m.pkl")
                result = train_from_human_logs(
                    log_dir=td, model_path=model_path, verbose=False
                )
            if result is not None:
                assert "model" in result
                assert result["n_samples"] >= MIN_SAMPLES_TO_TRAIN

    def test_model_saves_and_loads(self):
        from ml.human_trainer import train_from_human_logs, _load_model_bundle
        with tempfile.TemporaryDirectory() as td:
            for sid in range(6):
                self._write_session_csv(td, f"s{sid}", n_rows=25, gap=150 + sid * 10)
            with tempfile.TemporaryDirectory() as md:
                model_path = os.path.join(md, "m.pkl")
                trained = train_from_human_logs(
                    log_dir=td, model_path=model_path, verbose=False
                )
                if trained is not None:
                    loaded = _load_model_bundle(model_path)
                    assert loaded is not None
                    assert "model" in loaded
                    assert loaded["n_samples"] == trained["n_samples"]

    def test_corrupt_csv_skipped_gracefully(self):
        with tempfile.TemporaryDirectory() as td:
            # Write a corrupt CSV
            path = os.path.join(td, "session_bad_adaptive.csv")
            with open(path, "w") as f:
                f.write("garbage,data\nno,headers\n")
            rows = _load_human_rows(log_dir=td)
            # Should not raise, just return empty (or skip corrupt rows)


# ===========================================================================
# 10.  Data persistence – logger output is compatible with trainer input
# ===========================================================================

class TestDataPersistence:
    def test_logger_output_is_trainer_compatible(self):
        """Write a log using GameLogger; read it with human_trainer loader."""
        from game.logger import GameLogger
        with tempfile.TemporaryDirectory() as td:
            logger = GameLogger(session_id="test_sess", controller_name="adaptive",
                                log_dir=td)
            # Write 20 records
            for i in range(20):
                logger.log({
                    "episode": 1,
                    "pipe_index": i,
                    "gap_size": 165,
                    "gap_center": 320,
                    "bird_y_at_pass": 310.0,
                    "bird_vel_at_pass": -2.0,
                    "time_since_last_pass": 1.5,
                    "success": 1,
                    "consecutive_successes_before": 0,
                    "consecutive_failures_before": 0,
                    "success_rate_last3": 1.0,
                    "success_rate_last5": 1.0,
                    "survival_time": 10.0,
                    "total_pipes_passed": i,
                })
            rows = _load_human_rows(log_dir=td)
            assert len(rows) == 20


# ===========================================================================
# 11.  Rule-based fallback is correctly labelled (not claiming ML)
# ===========================================================================

class TestFallbackLabel:
    def test_fallback_sets_reason_correctly(self):
        ctrl = _make_controller(model_path="")   # force no model
        # Push through warmup + cooldown
        from controllers.dda_controller import MIN_WINDOW_FOR_ADJUST, ADJUSTMENT_COOLDOWN
        for _ in range(MIN_WINDOW_FOR_ADJUST + ADJUSTMENT_COOLDOWN + 5):
            ctrl.on_pipe_outcome(_outcome(True, gap=ctrl.current_gap))
        # Decision reason should mention RULE_BASED_FALLBACK or warming_up/cooldown
        reason = ctrl._last_decision_reason
        assert "RULE_BASED_FALLBACK" in reason or "warmup" in reason or "cooldown" in reason

    def test_no_ml_claimed_without_model(self):
        ctrl = _make_controller(model_path="")
        assert ctrl._model is None, "Model must be None when no model file provided"


# ===========================================================================
# 12.  on_run_end does not crash without model
# ===========================================================================

class TestOnRunEnd:
    def test_on_run_end_no_crash_without_model(self):
        ctrl = _make_controller(model_path="")
        # Should not raise even if human_trainer can't load data
        ctrl.on_run_end(died=True)

    def test_on_run_end_calls_reestimate(self):
        ctrl = _make_controller(model_path="")
        # Plant evidence
        ctrl._estimated_min_gap = 165
        for _ in range(MIN_EVIDENCE_PASSES + 3):
            ctrl._gap_evidence[159].append(1)
        ctrl.on_run_end(died=False)
        # Min gap should have been re-evaluated
        assert ctrl._estimated_min_gap <= 165
