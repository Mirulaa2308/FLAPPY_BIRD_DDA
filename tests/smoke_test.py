"""Headless smoke test – verifies all modules import correctly and key flows work."""
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()

# 1. All imports
from game.config import DIFFICULTY_PRESETS, GAP_MIN, GAP_MAX
from game.background import _sky_colors, _cycle_pos, BackgroundRenderer
from game.bird import Bird
from game.pipe import Pipe
from game.logger import GameLogger
from controllers.fixed import FixedController
from controllers.dda_controller import DataDrivenAdaptiveController

print("✓ All imports OK")

# 2. Difficulty preset sanity
for key, preset in DIFFICULTY_PRESETS.items():
    ctrl = FixedController(gap=preset["gap"]) if key != "maharoga" else \
           DataDrivenAdaptiveController(initial_gap=preset["gap"], model_path="", debug=False)
    ctrl.pipe_speed = preset["pipe_speed"]
    ctrl.spawn_interval = preset["spawn_interval"]
    assert GAP_MIN <= ctrl.current_gap <= GAP_MAX
print("✓ Difficulty presets create valid controllers")

# 3. Sky cycle
for pp in range(0, 125, 5):
    top, bot, ground = _sky_colors(pp)
    assert len(top) == 3 and len(bot) == 3 and len(ground) == 3
    assert all(0 <= v <= 255 for v in top + bot + ground)
print("✓ Sky cycle returns valid RGB colors for all pipe counts 0-120")

# 4. ML fix: estimated_min_gap < initial_gap
ctrl = DataDrivenAdaptiveController(initial_gap=165, model_path="", debug=False)
assert ctrl._estimated_min_gap < 165, "estimated_min_gap must be < initial_gap"
print(f"✓ ML fix: estimated_min_gap = {ctrl._estimated_min_gap} (initial=165)")

# 5. FixedController attributes
fc = FixedController(gap=220)
fc.pipe_speed = 2.2
fc.spawn_interval = 110
assert fc.current_gap == 220
assert fc.pipe_speed == 2.2
print("✓ FixedController accepts preset speed/interval")

# 6. Headless game pass simulation (MAHAROGA controller)
from game.config import SCREEN_WIDTH, SCREEN_HEIGHT, FPS, FIXED_PIPE_SPEED, FIXED_SPAWN_INTERVAL
from game.game import FlappyGame

ctrl = DataDrivenAdaptiveController(initial_gap=165, model_path="data/human_model.pkl", debug=False)
game = FlappyGame(ctrl, session_id="smoke_test", render=False, headless=True)
game.reset_episode()
# Run for up to 2000 frames
for i in range(2000):
    done = game.update(jump=(i % 12 == 0))
    if done:
        game.begin_attempt()

print(f"✓ Headless game loop ran 2000 frames without error. Score: {game.score}")

# 7. Retry preserves ML data
ctrl2 = DataDrivenAdaptiveController(initial_gap=165, model_path="", debug=False)
ctrl2._estimated_min_gap = 120
ctrl2._gap_evidence[115].extend([1, 1, 1, 1])
ctrl2.reset()
assert ctrl2._estimated_min_gap == 120
assert 115 in ctrl2._gap_evidence
print("✓ Retry (reset) preserves ML learning")

print("\n=== All smoke tests PASSED ===")
