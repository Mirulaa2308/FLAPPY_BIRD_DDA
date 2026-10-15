"""Diagnose each bot on gap=200. Print first 200 frames."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from game.game import FlappyGame
from controllers.fixed import FixedController
from ml.bots import BotLowSkill, BotMediumSkill, BotHighSkill


def run(bot, gap=200, frames=300, verbose=False):
    controller = FixedController(gap=gap)
    game = FlappyGame(controller, session_id="diag", render=False, headless=True)
    game.reset_episode()
    game.controller.reset()
    game.success_history = []
    game.current_gap = controller.current_gap

    died_at = None
    for f in range(frames):
        jump = bot(game.bird, game.pipes)
        if verbose and (f < 5 or f % 20 == 0):
            p = game.pipes[0] if game.pipes else None
            pinfo = f"px={p.x:5.0f} gap_c={p.gap_center:5.0f}" if p else "no pipe"
            print(f"  f={f:3d} y={game.bird.y:6.1f} v={game.bird.velocity:5.1f} "
                  f"jump={int(jump)} pipes={len(game.pipes)} {pinfo}")
        done = game.update(jump=jump)
        if done:
            died_at = f
            break

    score = game.score
    game.quit()
    return score, died_at


def main():
    bots = [
        ("low", BotLowSkill(seed=1)),
        ("medium", BotMediumSkill(seed=2)),
        ("high", BotHighSkill(seed=3)),
    ]
    print("Scores over 300 frames, gap=200:")
    for name, bot in bots:
        score, died = run(bot, gap=200, frames=300)
        print(f"  {name:8s} score={score}  died_at_frame={died}")

    print("\nVerbose trace for LOW bot (first 200 frames):")
    run(BotLowSkill(seed=1), gap=200, frames=200, verbose=True)

    print("\nVerbose trace for MEDIUM bot (first 200 frames):")
    run(BotMediumSkill(seed=2), gap=200, frames=200, verbose=True)


if __name__ == "__main__":
    main()