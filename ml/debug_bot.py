"""Debug: print bot decisions."""
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from game.game import FlappyGame
from controllers.fixed import FixedController
from ml.bots import BotHighSkill


def main():
    controller = FixedController(gap=200)
    game = FlappyGame(controller, session_id="debug", render=False, headless=True)
    bot = BotHighSkill(seed=1)

    game.reset_episode()
    game.controller.reset()
    game.success_history = []
    game.current_gap = controller.current_gap

    for frame in range(300):
        jump = bot(game.bird, game.pipes)
        pipe_info = ""
        if game.pipes:
            p = game.pipes[0]
            pipe_info = f"  pipe_x={p.x:6.1f}  gap_center={p.gap_center:5.1f}"

        if frame % 5 == 0 or frame > 200:
            print(f"f={frame:3d}  y={game.bird.y:6.1f}  v={game.bird.velocity:6.2f}  "
                  f"pipes={len(game.pipes)}  jump={jump}{pipe_info}")

        done = game.update(jump=jump)
        if done:
            print(f"DIED at frame {frame}, y={game.bird.y:.1f}, v={game.bird.velocity:.1f}")
            break

    game.quit()


if __name__ == "__main__":
    main()