"""FLAPPY ADAPT – main entry point.

Launches with a Home Screen where the player chooses Fixed or Adaptive mode.
The --controller CLI flag is still supported for automated/agent use.
"""
import argparse
from game.game import play_human
from controllers.fixed import FixedController
from controllers.adaptive import AdaptiveController
from controllers.reactive import ReactiveController
from controllers.ml_adaptive import MLAdaptiveController
from controllers.multiattempt import MultiAttemptController


def build_controller(name):
    if name == "fixed":
        return FixedController(gap=165)
    if name == "adaptive":
        return AdaptiveController()
    if name == "reactive":
        return ReactiveController(initial_gap=165, step=12, streak_threshold=3)
    if name == "ml_adaptive":
        return MLAdaptiveController(model_path="data/model.pkl", target_success=0.6)
    if name == "multi_ml":
        return MultiAttemptController(model_path="data/model.pkl")
    raise ValueError(f"Unknown controller: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Flappy Bird with Fixed / Adaptive difficulty."
    )
    parser.add_argument(
        "--controller", default="fixed",
        choices=["fixed", "adaptive", "reactive", "ml_adaptive", "multi_ml"],
        help="Difficulty controller (default: fixed; home screen lets you choose at run-time)."
    )
    parser.add_argument("--session", default=None,
                        help="Optional session ID for log files.")
    args = parser.parse_args()

    controller = build_controller(args.controller)
    play_human(controller, session_id=args.session)