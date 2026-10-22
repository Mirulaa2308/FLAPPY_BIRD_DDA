import os
import time
import pygame
from game.config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS, PIPE_SPAWN_INTERVAL,
    GAP_DEFAULT, COLOR_BG, COLOR_TEXT
)
from game.bird import Bird
from game.pipe import Pipe
from game.logger import GameLogger


class FlappyGame:
    def __init__(self, controller, session_id=None, render=True, headless=False):
        pygame.init()
        self.render_enabled = render and not headless
        if self.render_enabled:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            pygame.display.set_caption(f"FLAPPY ADAPT - {controller.name}")
        else:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            self.screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 24)

        self.controller = controller
        self.session_id = session_id or str(int(time.time()))
        self.logger = GameLogger(self.session_id, controller.name)

        self.bird = Bird()
        self.pipes = []
        self.score = 0
        self.episode = 0
        self.pipe_index = 0
        self.frame_count = 0
        self.episode_start = 0
        self.attempt_collisions = 0
        self.success_history = []
        self.last_pass_time = 0
        self.current_gap = GAP_DEFAULT
        self.running = True

    def reset_episode(self):
        self.bird.reset()
        self.pipes = []
        self.score = 0
        self.pipe_index = 0
        self.frame_count = 0
        self.episode_start = time.time()
        self.last_pass_time = self.episode_start
        self.current_gap = self.controller.current_gap

    def begin_attempt(self):
        self.reset_episode()
        self.success_history = []
        self.attempt_collisions = 0
        begin = getattr(self.controller, "begin_attempt", None)
        if callable(begin):
            self.current_gap = begin()

    def end_attempt(self, outcome):
        end = getattr(self.controller, "end_attempt", None)
        if callable(end):
            end({
                "score": self.score,
                "survival_time": max(0.0, time.time() - self.episode_start),
                "obstacles_passed": self.score,
                "collisions": self.attempt_collisions,
                "outcome": outcome,
            })

    def spawn_pipe(self):
        self.pipes.append(Pipe(SCREEN_WIDTH + 40, self.current_gap))

    def build_outcome_record(self, success, pipe):
        cons_succ = 0
        for s in reversed(self.success_history):
            if s == 1:
                cons_succ += 1
            else:
                break
        cons_fail = 0
        for s in reversed(self.success_history):
            if s == 0:
                cons_fail += 1
            else:
                break

        last3 = self.success_history[-3:]
        last5 = self.success_history[-5:]

        return {
            "episode": self.episode,
            "pipe_index": self.pipe_index,
            "gap_size": self.current_gap,
            "gap_center": pipe.gap_center if pipe else "",
            "bird_y_at_pass": round(self.bird.y, 2),
            "bird_vel_at_pass": round(self.bird.velocity, 2),
            "time_since_last_pass": round(time.time() - self.last_pass_time, 3),
            "success": int(success),
            "consecutive_successes_before": cons_succ,
            "consecutive_failures_before": cons_fail,
            "success_rate_last3": round(sum(last3) / len(last3), 3) if last3 else 0.0,
            "success_rate_last5": round(sum(last5) / len(last5), 3) if last5 else 0.0,
            "survival_time": round(time.time() - self.episode_start, 3),
            "total_pipes_passed": self.score,
        }

    def handle_collision(self, pipe=None):
        self.attempt_collisions += 1
        outcome = self.build_outcome_record(success=False, pipe=pipe)
        self.success_history.append(0)
        self.logger.log(outcome)
        if not callable(getattr(self.controller, "begin_attempt", None)):
            self.current_gap = self.controller.on_pipe_outcome(outcome)
        return True

    def check_pass(self):
        for pipe in self.pipes:
            if not pipe.passed and pipe.x + 70 < self.bird.x:
                pipe.passed = True
                self.score += 1
                self.pipe_index += 1
                outcome = self.build_outcome_record(success=True, pipe=pipe)
                self.success_history.append(1)
                self.logger.log(outcome)
                if not callable(getattr(self.controller, "begin_attempt", None)):
                    self.current_gap = self.controller.on_pipe_outcome(outcome)
                self.last_pass_time = time.time()

    def update(self, jump=False):
        if jump:
            self.bird.jump()

        self.bird.update()
        self.frame_count += 1

        if self.bird.y < 0 or self.bird.y > SCREEN_HEIGHT:
            return self.handle_collision()

        if self.frame_count % PIPE_SPAWN_INTERVAL == 0:
            self.spawn_pipe()

        for pipe in self.pipes:
            pipe.update()
        self.pipes = [p for p in self.pipes if not p.off_screen()]

        bird_rect = self.bird.get_rect()
        for pipe in self.pipes:
            top_rect, bottom_rect = pipe.get_rects()
            if bird_rect.colliderect(top_rect) or bird_rect.colliderect(bottom_rect):
                return self.handle_collision(pipe=pipe)

        self.check_pass()
        return False

    def draw(self):
        if not self.render_enabled:
            return
        self.screen.fill(COLOR_BG)
        for pipe in self.pipes:
            pipe.draw(self.screen)
        self.bird.draw(self.screen)

        score_text = self.font.render(f"Score: {self.score}", True, COLOR_TEXT)
        gap_text = self.font.render(f"Gap: {int(self.current_gap)}", True, COLOR_TEXT)
        ctrl_text = self.font.render(f"Ctrl: {self.controller.name}", True, COLOR_TEXT)
        self.screen.blit(score_text, (10, 10))
        self.screen.blit(gap_text, (10, 40))
        self.screen.blit(ctrl_text, (10, 70))

        pygame.display.flip()

    def run_episode(self, max_frames=10000, agent=None, fps=None):
        if callable(getattr(self.controller, "begin_attempt", None)):
            self.begin_attempt()
        else:
            self.reset_episode()
            self.controller.reset()
            self.success_history = []
            self.attempt_collisions = 0

        for _ in range(max_frames):
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    self.end_attempt("exit")
                    return self.score
                if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                    self.bird.jump()

            jump = agent(self.bird, self.pipes) if agent else False
            done = self.update(jump=jump)

            if self.render_enabled:
                self.draw()
                self.clock.tick(fps or FPS)

            if done:
                self.end_attempt("collision")
                break
        else:
            self.end_attempt("win")

        return self.score

    def quit(self):
        pygame.quit()


def play_human(controller, session_id=None):
    game = FlappyGame(controller, session_id=session_id)
    print(f"Controller: {controller.name}. Press SPACE to jump. Q to quit.")

    def begin_attempt():
        game.begin_attempt()

    begin_attempt()
    while game.running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game.end_attempt("exit")
                game.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    game.bird.jump()
                elif event.key == pygame.K_q:
                    game.end_attempt("exit")
                    game.quit()
                    return

        done = game.update(jump=False)
        game.draw()
        game.clock.tick(FPS)

        if done:
            game.end_attempt("collision")
            game.episode += 1
            print(f"Episode {game.episode} ended. Score: {game.score}")
            begin_attempt()