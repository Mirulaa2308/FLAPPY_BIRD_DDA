"""FLAPPY ADAPT - Day 2 entry point."""
import argparse
from game.game import play_human
from controllers.fixed import FixedController
from controllers.reactive import ReactiveController
from controllers.ml_adaptive import MLAdaptiveController
from controllers.multiattempt import MultiAttemptController


def build_controller(name):
    if name == "fixed":
        return FixedController(gap=165)
    if name == "reactive":
        return ReactiveController(initial_gap=165, step=12, streak_threshold=3)
    if name == "ml_adaptive":
        return MLAdaptiveController(model_path="data/model.pkl", target_success=0.6)
    if name == "multi_ml":
        return MultiAttemptController(model_path="data/model.pkl")
    raise ValueError(f"Unknown controller: {name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller", default="fixed",
                        choices=["fixed", "reactive", "ml_adaptive", "multi_ml"])
    parser.add_argument("--session", default=None)
    args = parser.parse_args()

    controller = build_controller(args.controller)
    play_human(controller, session_id=args.session)