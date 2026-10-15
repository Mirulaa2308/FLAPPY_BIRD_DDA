"""Sanity check: verify each bot can survive at reasonable difficulty.

Run from project root:
    python -m ml.sanity_check
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from game.game import FlappyGame
from controllers.fixed import FixedController
from ml.bots import BotLowSkill, BotMediumSkill, BotHighSkill


def test_bot(bot, gap, episodes=5, max_frames=3000):
    scores = []
    for ep in range(episodes):
        controller = FixedController(gap=gap)
        game = FlappyGame(controller,
                          session_id=f"sanity_{bot.name}_{gap}_{ep}",
                          render=False, headless=True)
        game.reset_episode()
        game.controller.reset()
        game.success_history = []
        game.current_gap = controller.current_gap

        for _ in range(max_frames):
            jump = bot(game.bird, game.pipes)
            done = game.update(jump=jump)
            if done:
                break
        scores.append(game.score)
        game.quit()
    return scores


def main():
    print("Sanity check: bot scores at gap=200 (wide, easy) and gap=150 (moderate)\n")

    bots = [BotLowSkill(seed=1), BotMediumSkill(seed=2), BotHighSkill(seed=3)]

    print(f"{'Bot':8s} {'gap=200 avg':>14s} {'gap=150 avg':>14s}")
    print("-" * 42)
    for bot in bots:
        s200 = test_bot(bot, gap=200, episodes=5)
        s150 = test_bot(bot, gap=150, episodes=5)
        print(f"{bot.name:8s} {sum(s200)/len(s200):14.1f} {sum(s150)/len(s150):14.1f}")

    print("\nExpected pattern:")
    print("  low    -> low scores at both gaps")
    print("  medium -> moderate scores, better at gap=200 than 150")
    print("  high   -> high scores (should survive 10+ pipes at gap=200)")


if __name__ == "__main__":
    main()