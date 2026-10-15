"""Run the three-condition difficulty experiment using scripted bots.

For each (bot, controller) pair, run N episodes headless.
Record per-episode metrics:
  - pipes_passed (score)
  - survival_time
  - collision_count (implicitly 1 per episode; aggregated)
  - difficulty_changes: total absolute change in gap_size across the episode
  - mean_gap, min_gap, max_gap
  - mean_success_rate

Output: data/experiment_results.csv

Run from project root:
    python -m experiments.run_experiment
"""
import os
import sys
import time
import csv
import statistics

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from game.game import FlappyGame
from controllers.fixed import FixedController
from controllers.reactive import ReactiveController
from controllers.ml_adaptive import MLAdaptiveController
from ml.bots import BotLowSkill, BotMediumSkill, BotHighSkill


EPISODES_PER_PAIR = 10
MAX_FRAMES = 1500   # safety cap
OUT_PATH = "data/experiment_results.csv"


def make_controller(name):
    if name == "fixed":
        return FixedController(gap=165)
    if name == "reactive":
        return ReactiveController(initial_gap=165, step=12, streak_threshold=3)
    if name == "ml_adaptive":
        return MLAdaptiveController(model_path="data/model.pkl", target_success=0.6)
    raise ValueError(name)


def make_bot(name):
    if name == "low":
        return BotLowSkill(seed=42)
    if name == "medium":
        return BotMediumSkill(seed=42)
    if name == "high":
        return BotHighSkill(seed=42)
    raise ValueError(name)


def run_single_episode(bot_name, controller_name, episode_idx):
    """Run one headless episode; return metrics dict."""
    bot = make_bot(bot_name)
    controller = make_controller(controller_name)
    game = FlappyGame(controller,
                      session_id=f"exp_{bot_name}_{controller_name}_{episode_idx}",
                      render=False, headless=True)

    gap_trace = []
    start = time.time()

    game.reset_episode()
    game.controller.reset()
    game.success_history = []
    game.current_gap = controller.current_gap

    # Hook the logger to record gap trace
    original_log = game.logger.log

    def capturing_log(record):
        gap_trace.append(record["gap_size"])
        original_log(record)

    game.logger.log = capturing_log

    for _ in range(MAX_FRAMES):
        jump = bot(game.bird, game.pipes)
        done = game.update(jump=jump)
        if done:
            break

    survival_time = time.time() - start
    score = game.score

    # Difficulty oscillation metric: sum of |Δgap| between decisions
    if len(gap_trace) >= 2:
        oscillation = sum(abs(gap_trace[i] - gap_trace[i - 1])
                          for i in range(1, len(gap_trace)))
    else:
        oscillation = 0.0

    mean_gap = statistics.mean(gap_trace) if gap_trace else controller.current_gap
    min_gap = min(gap_trace) if gap_trace else controller.current_gap
    max_gap = max(gap_trace) if gap_trace else controller.current_gap

    game.quit()

    return {
        "bot": bot_name,
        "controller": controller_name,
        "episode": episode_idx,
        "score": score,
        "survival_time_s": round(survival_time, 3),
        "decisions": len(gap_trace),
        "difficulty_oscillation": round(oscillation, 2),
        "mean_gap": round(mean_gap, 1),
        "min_gap": round(min_gap, 1),
        "max_gap": round(max_gap, 1),
    }


def main():
    print(f"Running experiment: {EPISODES_PER_PAIR} episodes per controller", flush=True)
    print("Using HIGH-skill bot as the standardized player.\n", flush=True)
    rows = []
    total = 3 * EPISODES_PER_PAIR
    done = 0

    bot_name = "high"
    for controller_name in ["fixed", "reactive", "ml_adaptive"]:
        print(f"  controller={controller_name:12s}", flush=True)
        scores = []
        for ep in range(EPISODES_PER_PAIR):
            metrics = run_single_episode(bot_name, controller_name, ep)
            rows.append(metrics)
            scores.append(metrics["score"])
            done += 1
            print(f"    ep {ep+1}/{EPISODES_PER_PAIR}: score={metrics['score']} "
                  f"osc={metrics['difficulty_oscillation']}", flush=True)

            os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
            with open(OUT_PATH, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)

        avg = sum(scores) / len(scores)
        print(f"  -> avg score: {avg:6.2f}  ({done}/{total})\n", flush=True)

    print(f"Saved {len(rows)} episodes to {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()