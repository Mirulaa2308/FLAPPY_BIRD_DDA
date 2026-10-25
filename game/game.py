"""Core game module.

FlappyGame  – headless/agent-compatible game engine (unchanged API surface).
play_human  – full human-playable loop with Home / Game / GameOver screens.
"""
import os
import time
import pygame
from game.config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, FPS,
    GAP_DEFAULT,
    FIXED_GAP, FIXED_PIPE_SPEED, FIXED_SPAWN_INTERVAL,
    COLOR_TEXT, COLOR_PIPE,
    BEST_SCORE_FILE,
)
from game.bird import Bird
from game.pipe import Pipe
from game.logger import GameLogger
from game.background import BackgroundRenderer


# ---------------------------------------------------------------------------
#  Best-score persistence
# ---------------------------------------------------------------------------

def _load_best(mode_key):
    """Load best score for a given mode key from disk."""
    path = BEST_SCORE_FILE + f".{mode_key}"
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def _save_best(mode_key, score):
    """Persist best score for a given mode key."""
    os.makedirs(os.path.dirname(BEST_SCORE_FILE), exist_ok=True)
    path = BEST_SCORE_FILE + f".{mode_key}"
    try:
        with open(path, "w") as f:
            f.write(str(score))
    except Exception:
        pass


# ---------------------------------------------------------------------------
#  FlappyGame  (headless / agent-compatible – existing API preserved)
# ---------------------------------------------------------------------------

class FlappyGame:
    def __init__(self, controller, session_id=None, render=True, headless=False):
        pygame.init()
        self.render_enabled = render and not headless
        if self.render_enabled:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            pygame.display.set_caption(f"FLAPPY ADAPT – {controller.name}")
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

        # Pipe speed / interval (used by adaptive controller)
        self._pipe_speed = getattr(controller, "pipe_speed", FIXED_PIPE_SPEED)
        self._spawn_interval = getattr(controller, "spawn_interval", FIXED_SPAWN_INTERVAL)

    def reset_episode(self):
        self.bird.reset()
        self.pipes = []
        self.score = 0
        self.pipe_index = 0
        self.frame_count = 0
        self.episode_start = time.time()
        self.last_pass_time = self.episode_start
        self.current_gap = self.controller.current_gap
        self._pipe_speed = getattr(self.controller, "pipe_speed", FIXED_PIPE_SPEED)
        self._spawn_interval = getattr(self.controller, "spawn_interval", FIXED_SPAWN_INTERVAL)

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
        self.pipes.append(Pipe(SCREEN_WIDTH + 40, self.current_gap,
                               speed=self._pipe_speed))

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
            new_gap = self.controller.on_pipe_outcome(outcome)
            self.current_gap = new_gap
            # Sync adaptive knobs
            self._pipe_speed = getattr(self.controller, "pipe_speed", self._pipe_speed)
            self._spawn_interval = int(getattr(self.controller, "spawn_interval",
                                               self._spawn_interval))
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
                    new_gap = self.controller.on_pipe_outcome(outcome)
                    self.current_gap = new_gap
                    self._pipe_speed = getattr(self.controller, "pipe_speed", self._pipe_speed)
                    self._spawn_interval = int(getattr(self.controller, "spawn_interval",
                                                       self._spawn_interval))
                self.last_pass_time = time.time()

    def update(self, jump=False):
        if jump:
            self.bird.jump()

        self.bird.update()
        self.frame_count += 1

        if self.bird.y < 0 or self.bird.y > SCREEN_HEIGHT:
            return self.handle_collision()

        if self.frame_count % self._spawn_interval == 0:
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
        self.screen.fill((113, 197, 207))    # fallback (overdrawn by bg)
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


# ===========================================================================
#  Full human-playable flow  (Home → Game → GameOver → Home)
# ===========================================================================

# ---------------------------------------------------------------------------
#  Typography helpers
#
#  Font preference chain (all built into Windows; all have good screen hinting):
#    Segoe UI → Calibri → Arial → pygame bitmap fallback
#
#  _shadow_text  – renders text with a 4-offset outline shadow for strong
#                  contrast on ANY background colour (sky, panel, dark overlay).
#  _centred_text – measures width and centres horizontally, returns the rect.
# ---------------------------------------------------------------------------

_FONT_CACHE = {}

# Preferred font names in priority order.  Tahoma / Verdana / Trebuchet MS / Arial
# provide crisp hinting, open counters, and avoid ultra-thin/condensed variants.
_FONT_NAMES = "tahoma, verdana, trebuchetms, arial, sans-serif"


def _font(size, bold=False):
    """Return a cached SysFont at the requested size / weight."""
    key = (size, bold)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = pygame.font.SysFont(_FONT_NAMES, size, bold=bold)
        except Exception:
            _FONT_CACHE[key] = pygame.font.Font(None, size)
    return _FONT_CACHE[key]


# Colours used for the outline shadow (pure black, no alpha channel needed)
_SHADOW_DARK  = (0,   0,   0)
_SHADOW_MID   = (30,  30,  30)


def _pill(surface, x, y, w, h, bg_color=(0, 0, 0, 160), border_color=(255, 255, 255, 60), radius=8, border_width=1):
    """Draw a semi-transparent rounded backing panel or pill badge."""
    pill_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(pill_surf, bg_color, (0, 0, w, h), border_radius=radius)
    if border_color and border_width > 0:
        pygame.draw.rect(pill_surf, border_color, (0, 0, w, h), border_width, border_radius=radius)
    surface.blit(pill_surf, (x, y))


def _shadow_text(surface, text, font, color, pos, shadow_offset=1, shadow_color=_SHADOW_DARK):
    """Render anti-aliased text with a subtle outline / drop shadow.

    The shadow is drawn at diagonal offsets for crisp, high-contrast glyphs
    without blobby distortion at smaller point sizes.
    Returns the pygame.Rect of the foreground glyph.
    """
    if shadow_offset > 0:
        shadow_surf = font.render(text, True, shadow_color)
        o = shadow_offset
        for dx, dy in ((-o, -o), (o, -o), (-o, o), (o, o)):
            surface.blit(shadow_surf, (pos[0] + dx, pos[1] + dy))
    fg = font.render(text, True, color)
    surface.blit(fg, pos)
    return fg.get_rect(topleft=pos)


def _centred_shadow_text(surface, text, font, color, cy, shadow_offset=1, shadow_color=_SHADOW_DARK):
    """Centre text horizontally at vertical position cy; return its Rect."""
    w = font.size(text)[0]
    x = SCREEN_WIDTH // 2 - w // 2
    return _shadow_text(surface, text, font, color, (x, cy), shadow_offset, shadow_color)


# ---------------------------------------------------------------------------
#  Button
# ---------------------------------------------------------------------------

class _Button:
    """Simple rectangular button with hover feedback and legible label."""

    def __init__(self, rect, text, color, hover_color, text_color=(255, 255, 255)):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.color = color
        self.hover_color = hover_color
        self.text_color = text_color
        self._hovered = False

    def draw(self, surface):
        self._hovered = self.rect.collidepoint(pygame.mouse.get_pos())
        c = self.hover_color if self._hovered else self.color

        pygame.draw.rect(surface, c, self.rect, border_radius=10)
        pygame.draw.rect(surface, (255, 255, 255), self.rect, 2, border_radius=10)

        # Bold 19 pt label with subtle 1px outline for crisp legibility
        font = _font(19, bold=True)
        shadow_surf = font.render(self.text, True, _SHADOW_DARK)
        cx = self.rect.centerx - shadow_surf.get_width() // 2
        cy = self.rect.centery - shadow_surf.get_height() // 2
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            surface.blit(shadow_surf, (cx + dx, cy + dy))
        label = font.render(self.text, True, self.text_color)
        surface.blit(label, (cx, cy))

    def is_clicked(self, event):
        return (event.type == pygame.MOUSEBUTTONDOWN and
                event.button == 1 and
                self.rect.collidepoint(event.pos))


# ---------------------------------------------------------------------------
#  Screen: Home / Mode selection
# ---------------------------------------------------------------------------

def _home_screen(screen, clock, best_fixed, best_adaptive):
    """Returns 'fixed', 'adaptive', or 'quit'."""
    bg = BackgroundRenderer()

    W, H = SCREEN_WIDTH, SCREEN_HEIGHT

    btn_w, btn_h = 300, 52
    btn_x = W // 2 - btn_w // 2

    btn_fixed    = _Button((btn_x, 212, btn_w, btn_h),
                           "Play Fixed Difficulty",
                           (35, 110, 205), (65, 150, 255))
    btn_adaptive = _Button((btn_x, 276, btn_w, btn_h),
                           "Play Adaptive Difficulty",
                           (35, 155, 80), (60, 200, 110))

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "quit"
            if btn_fixed.is_clicked(event):
                return "fixed"
            if btn_adaptive.is_clicked(event):
                return "adaptive"

        bg.update(pipes_passed=0)
        bg.draw(screen)

        # ---- Title -------------------------------------------------------
        _centred_shadow_text(screen, "FLAPPY ADAPT",
                             _font(48, bold=True), (255, 235, 70), 55, shadow_offset=2)

        # ---- Subtitle in pill --------------------------------------------
        sub_text = "A Flappy Bird with Smart Difficulty"
        sub_font = _font(16, bold=True)
        sub_w, sub_h = sub_font.size(sub_text)
        _pill(screen, W // 2 - sub_w // 2 - 14, 114, sub_w + 28, sub_h + 8,
              bg_color=(12, 20, 42, 170), border_color=(90, 140, 230, 140), radius=10)
        _centred_shadow_text(screen, sub_text, sub_font, (225, 245, 255), 118, shadow_offset=1)

        # ---- Best scores row in pill -------------------------------------
        best_w = 360
        best_h = 36
        best_x = W // 2 - best_w // 2
        _pill(screen, best_x, 156, best_w, best_h,
              bg_color=(12, 20, 42, 190), border_color=(80, 130, 215, 150), radius=12)

        bf_str  = f"Best Fixed: {best_fixed}"
        ba_str  = f"Best Adaptive: {best_adaptive}"
        sf16    = _font(15, bold=True)
        bf_w    = sf16.size(bf_str)[0]
        ba_w    = sf16.size(ba_str)[0]
        pad     = max(12, (best_w - bf_w - ba_w) // 3)
        _shadow_text(screen, bf_str,  sf16, (255, 225, 90),  (best_x + pad, 165), shadow_offset=1)
        _shadow_text(screen, ba_str,  sf16, (100, 255, 175), (best_x + pad * 2 + bf_w, 165), shadow_offset=1)

        # ---- Buttons -----------------------------------------------------
        btn_fixed.draw(screen)
        btn_adaptive.draw(screen)

        # ---- Mode descriptions in backing card --------------------------
        card_w = 420
        card_h = 216
        card_x = W // 2 - card_w // 2
        card_y = 348
        _pill(screen, card_x, card_y, card_w, card_h,
              bg_color=(14, 22, 45, 220), border_color=(85, 135, 220, 160), radius=14, border_width=2)

        hdr_font  = _font(15, bold=True)
        body_font = _font(14)
        line_h    = 21

        fixed_desc = [
            "Fixed Difficulty:",
            "  Pipe gap, speed, and spawn rate never change.",
            "  Same challenge from start to finish.",
        ]
        adaptive_desc = [
            "Adaptive Difficulty:",
            "  Watches your pass rate over the last 5 pipes.",
            "  Gets harder when you fly well, easier when you struggle.",
        ]

        desc_top = card_y + 14
        for i, line in enumerate(fixed_desc):
            col = (255, 230, 100) if i == 0 else (225, 240, 255)
            font_to_use = hdr_font if i == 0 else body_font
            _shadow_text(screen, line, font_to_use, col,
                         (card_x + 18, desc_top + i * line_h), shadow_offset=1)

        adaptive_top = desc_top + len(fixed_desc) * line_h + 10
        for i, line in enumerate(adaptive_desc):
            col = (110, 255, 175) if i == 0 else (225, 240, 255)
            font_to_use = hdr_font if i == 0 else body_font
            _shadow_text(screen, line, font_to_use, col,
                         (card_x + 18, adaptive_top + i * line_h), shadow_offset=1)

        # ---- Controls hint in pill ---------------------------------------
        hint_str = "SPACE / Click to jump   \u2022   ESC to quit"
        hf = _font(14, bold=True)
        hw, hh = hf.size(hint_str)
        _pill(screen, W // 2 - hw // 2 - 14, H - 36, hw + 28, hh + 8,
              bg_color=(10, 18, 32, 200), border_color=(80, 130, 200, 130), radius=10)
        _centred_shadow_text(screen, hint_str, hf, (235, 245, 255), H - 32, shadow_offset=1)

        pygame.display.flip()
        clock.tick(FPS)


# ---------------------------------------------------------------------------
#  Screen: Game Over
# ---------------------------------------------------------------------------

def _gameover_screen(screen, clock, score, best_score, mode_name, bg, pipes_passed):
    """Shows game-over modal with clean typography, buttons, and shortcuts."""
    W, H = SCREEN_WIDTH, SCREEN_HEIGHT

    panel_w, panel_h = 370, 310
    panel_x = W // 2 - panel_w // 2
    panel_y = H // 2 - panel_h // 2 - 15

    btn_w, btn_h = 150, 48
    btn_retry = _Button((panel_x + 24, panel_y + 196, btn_w, btn_h),
                        "Retry (R)",  (195, 65, 40), (235, 100, 70))
    btn_home  = _Button((panel_x + panel_w - 24 - btn_w, panel_y + 196, btn_w, btn_h),
                        "Home (H)",   (40,  95, 205), (70, 140, 245))

    new_best = score >= best_score and score > 0
    overlay_alpha = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    return "retry"
                if event.key == pygame.K_h:
                    return "home"
                if event.key == pygame.K_ESCAPE:
                    return "home"
            if btn_retry.is_clicked(event):
                return "retry"
            if btn_home.is_clicked(event):
                return "home"

        bg.update(pipes_passed=pipes_passed)
        bg.draw(screen)

        # Dark overlay fades in
        overlay_alpha = min(185, overlay_alpha + 6)
        overlay = pygame.Surface((W, H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, overlay_alpha))
        screen.blit(overlay, (0, 0))

        # Main panel card
        _pill(screen, panel_x, panel_y, panel_w, panel_h,
              bg_color=(16, 22, 45, 235), border_color=(100, 150, 255, 180), radius=16, border_width=2)

        # "GAME OVER" title
        _centred_shadow_text(screen, "GAME OVER",
                             _font(44, bold=True), (255, 80, 80),
                             panel_y + 18, shadow_offset=2)

        # Mode badge
        mode_label = f"Mode: {mode_name.title()}"
        ml_font = _font(15, bold=True)
        ml_w, ml_h = ml_font.size(mode_label)
        _pill(screen, W // 2 - ml_w // 2 - 12, panel_y + 74, ml_w + 24, ml_h + 8,
              bg_color=(25, 40, 75, 190), border_color=(100, 150, 240, 140), radius=8)
        _centred_shadow_text(screen, mode_label, ml_font, (220, 240, 255), panel_y + 78, shadow_offset=1)

        # Score
        _centred_shadow_text(screen, f"Score: {score}",
                             _font(28, bold=True), (255, 235, 90),
                             panel_y + 114, shadow_offset=1)

        # Best score (with clear highlight on new best)
        best_color = (100, 255, 170) if new_best else (210, 225, 240)
        best_label = f"Best: {best_score}" + ("  (NEW BEST!)" if new_best else "")
        _centred_shadow_text(screen, best_label,
                             _font(19, bold=True), best_color,
                             panel_y + 152, shadow_offset=1)

        # Buttons inside panel
        btn_retry.draw(screen)
        btn_home.draw(screen)

        # Keyboard hint inside the card
        hint_str = "Press R to Retry   \u2022   Press H for Home"
        _centred_shadow_text(screen, hint_str,
                             _font(13, bold=True), (180, 205, 235), panel_y + 264, shadow_offset=1)

        pygame.display.flip()
        clock.tick(FPS)


# ---------------------------------------------------------------------------
#  In-game HUD
# ---------------------------------------------------------------------------

def _draw_hud(screen, score, current_gap, mode_name, pipe_speed=None):
    """Draw score, mode tag, and optional adaptive debug info.

    All elements are placed in clean, semi-transparent rounded pill backings
    with subtle borders so they are 100% readable across every sky phase
    and never obscured when pipes scroll through the upper screen.
    """
    # Large score in top-centre pill badge
    score_str = str(score)
    score_f = _font(34, bold=True)
    sw, sh = score_f.size(score_str)
    pill_w = max(68, sw + 32)
    pill_h = sh + 10
    _pill(screen, SCREEN_WIDTH // 2 - pill_w // 2, 6, pill_w, pill_h,
          bg_color=(12, 20, 40, 195), border_color=(255, 255, 255, 130), radius=12, border_width=2)
    _centred_shadow_text(screen, score_str, score_f, (255, 255, 255), 10, shadow_offset=1)

    # Mode badge in top-left pill
    mode_str = f"{mode_name.title()} Mode"
    mf = _font(14, bold=True)
    mw, mh = mf.size(mode_str)
    _pill(screen, 10, 8, mw + 20, mh + 10,
          bg_color=(12, 20, 40, 190), border_color=(80, 145, 235, 140), radius=8)
    _shadow_text(screen, mode_str, mf, (220, 240, 255), (20, 13), shadow_offset=1)

    # Adaptive debug info in top-right pill (only shown in adaptive mode)
    if pipe_speed is not None:
        dbg_str = f"Gap {int(current_gap)}  \u2022  Spd {pipe_speed:.1f}"
        df = _font(13, bold=True)
        dw, dh = df.size(dbg_str)
        dbg_x = SCREEN_WIDTH - dw - 28
        _pill(screen, dbg_x - 2, 8, dw + 20, dh + 10,
              bg_color=(10, 28, 20, 195), border_color=(60, 180, 110, 140), radius=8)
        _shadow_text(screen, dbg_str, df, (130, 255, 190), (dbg_x + 8, 13), shadow_offset=1)


# ---------------------------------------------------------------------------
#  Single play_session  (one run until collision or quit)
#  Returns (score, action) where action is 'gameover', 'quit'
# ---------------------------------------------------------------------------

def _play_session(screen, clock, controller, mode_name, logger, episode, bg):
    bird = Bird()
    pipes = []
    score = 0
    pipe_index = 0
    frame_count = 0
    episode_start = time.time()
    last_pass_time = episode_start
    success_history = []
    attempt_collisions = 0
    collision_handled = False

    current_gap = controller.current_gap
    pipe_speed = getattr(controller, "pipe_speed", FIXED_PIPE_SPEED)
    spawn_interval = int(getattr(controller, "spawn_interval", FIXED_SPAWN_INTERVAL))

    def _sync_controller():
        nonlocal current_gap, pipe_speed, spawn_interval
        current_gap = controller.current_gap
        pipe_speed = getattr(controller, "pipe_speed", pipe_speed)
        spawn_interval = int(getattr(controller, "spawn_interval", spawn_interval))

    def _outcome(success, pipe):
        cons_s = cons_f = 0
        for s in reversed(success_history):
            if s == 1:
                cons_s += 1
            else:
                break
        for s in reversed(success_history):
            if s == 0:
                cons_f += 1
            else:
                break
        last3 = success_history[-3:]
        last5 = success_history[-5:]
        return {
            "episode": episode,
            "pipe_index": pipe_index,
            "gap_size": current_gap,
            "gap_center": pipe.gap_center if pipe else "",
            "bird_y_at_pass": round(bird.y, 2),
            "bird_vel_at_pass": round(bird.velocity, 2),
            "time_since_last_pass": round(time.time() - last_pass_time, 3),
            "success": int(success),
            "consecutive_successes_before": cons_s,
            "consecutive_failures_before": cons_f,
            "success_rate_last3": round(sum(last3) / len(last3), 3) if last3 else 0.0,
            "success_rate_last5": round(sum(last5) / len(last5), 3) if last5 else 0.0,
            "survival_time": round(time.time() - episode_start, 3),
            "total_pipes_passed": score,
        }

    running = True
    while running:
        # --- Events ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return score, "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return score, "quit"
                if event.key == pygame.K_SPACE:
                    bird.jump()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                bird.jump()

        # --- Update physics ---
        bird.update()
        frame_count += 1

        # --- Boundary collision ---
        if (bird.y < 0 or bird.y > SCREEN_HEIGHT) and not collision_handled:
            collision_handled = True
            rec = _outcome(False, None)
            success_history.append(0)
            attempt_collisions += 1
            logger.log(rec)
            controller.on_pipe_outcome(rec)
            _sync_controller()
            running = False
            break

        # --- Spawn pipes ---
        if frame_count % spawn_interval == 0:
            pipes.append(Pipe(SCREEN_WIDTH + 40, current_gap, speed=pipe_speed))

        # --- Move pipes & remove off-screen ---
        for p in pipes:
            p.update()
        pipes = [p for p in pipes if not p.off_screen()]

        # --- Pipe collision ---
        bird_rect = bird.get_rect()
        hit = False
        for p in pipes:
            tr, br = p.get_rects()
            if bird_rect.colliderect(tr) or bird_rect.colliderect(br):
                hit = True
                if not collision_handled:
                    collision_handled = True
                    rec = _outcome(False, p)
                    success_history.append(0)
                    attempt_collisions += 1
                    logger.log(rec)
                    controller.on_pipe_outcome(rec)
                    _sync_controller()
                break
        if hit:
            running = False
            break

        # --- Check pipe pass ---
        for p in pipes:
            if not p.passed and p.x + 70 < bird.x:
                p.passed = True
                score += 1
                pipe_index += 1
                rec = _outcome(True, p)
                success_history.append(1)
                logger.log(rec)
                controller.on_pipe_outcome(rec)
                _sync_controller()
                last_pass_time = time.time()

        # --- Draw ---
        bg.update(pipes_passed=score)
        bg.draw(screen)
        for p in pipes:
            p.draw(screen)
        bird.draw(screen)
        _draw_hud(screen, score, current_gap, mode_name,
                  pipe_speed if mode_name == "adaptive" else None)

        pygame.display.flip()
        clock.tick(FPS)

    return score, "gameover"


# ---------------------------------------------------------------------------
#  play_human  – main entry point for human play
# ---------------------------------------------------------------------------

def play_human(controller, session_id=None):
    """Full human-play loop: Home → Game → GameOver → loop."""
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("FLAPPY ADAPT")
    clock = pygame.time.Clock()

    mode_name = controller.name     # "fixed" or "adaptive"
    session_id = session_id or str(int(time.time()))
    logger = GameLogger(session_id, mode_name)
    bg = BackgroundRenderer()

    best = _load_best(mode_name)

    from controllers.fixed import FixedController
    from controllers.adaptive import AdaptiveController

    state = "home"
    episode = 0

    best_fixed    = _load_best("fixed")
    best_adaptive = _load_best("adaptive")

    while True:
        if state == "home":
            choice = _home_screen(screen, clock, best_fixed, best_adaptive)
            if choice == "quit":
                break
            if choice == "fixed":
                active_ctrl = FixedController(gap=FIXED_GAP)
                mode_name = "fixed"
            else:
                active_ctrl = AdaptiveController()
                mode_name = "adaptive"
            active_ctrl.reset()
            logger = GameLogger(session_id, mode_name)
            state = "game"

        elif state == "game":
            episode += 1
            score, action = _play_session(
                screen, clock, active_ctrl, mode_name, logger, episode, bg
            )
            if action == "quit":
                break

            best = _load_best(mode_name)
            if score > best:
                best = score
                _save_best(mode_name, best)
                if mode_name == "fixed":
                    best_fixed = best
                else:
                    best_adaptive = best

            state = "gameover"
            last_score = score

        elif state == "gameover":
            best = _load_best(mode_name)
            action = _gameover_screen(
                screen, clock, last_score, best, mode_name, bg, last_score
            )
            if action == "quit":
                break
            elif action == "retry":
                if mode_name == "fixed":
                    active_ctrl = FixedController(gap=FIXED_GAP)
                else:
                    active_ctrl = AdaptiveController()
                active_ctrl.reset()
                state = "game"
            elif action == "home":
                state = "home"

    pygame.quit()