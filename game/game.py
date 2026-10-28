"""Core game module.

FlappyGame  – headless/agent-compatible game engine (unchanged API surface).
play_human  – full human-playable loop with Main Menu → Difficulty → Game → GameOver.
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
    DIFFICULTY_PRESETS,
    GAP_MIN, GAP_MAX,
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
#  Maharoga record  –  best score  +  gap at that pipe pass
# ---------------------------------------------------------------------------
_MAHAROGA_RECORD_FILE = "data/maharoga_record.json"


def _load_maharoga_record():
    """Return {best_score, gap_at_best} or defaults."""
    try:
        import json
        with open(_MAHAROGA_RECORD_FILE) as f:
            rec = json.load(f)
        return {
            "best_score":   int(rec.get("best_score", 0)),
            "gap_at_best":  int(rec.get("gap_at_best", 0)),
        }
    except Exception:
        return {"best_score": 0, "gap_at_best": 0}


def _save_maharoga_record(score, gap_at_best):
    """Persist the Maharoga best score and the gap active at that pipe."""
    os.makedirs(os.path.dirname(_MAHAROGA_RECORD_FILE), exist_ok=True)
    try:
        import json
        with open(_MAHAROGA_RECORD_FILE, "w") as f:
            json.dump({"best_score": score, "gap_at_best": gap_at_best}, f)
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

# ---------------------------------------------------------------------------
#  Animated menu background simulation
#  Runs a decoupled Bird + Pipes simulation ONLY for visual decoration.
#  Writes NO score, NO training labels, NO log records.
# ---------------------------------------------------------------------------

class _MenuBgSim:
    """Minimal headless bird+pipe simulator used only for menu background visuals.
    No data is collected; this object is completely separate from the game."""
    SPAWN_INTERVAL = 90

    def __init__(self):
        self._bird  = Bird()
        self._pipes = []
        self._frame = 0
        self._reset_bird()

    def _reset_bird(self):
        self._bird.reset()
        self._bird.velocity = -4.0  # small upward nudge so it doesn't fall immediately

    def update(self):
        self._frame += 1

        # Flap logic: keep bird in the middle 40 % of the screen vertically
        if self._bird.y > SCREEN_HEIGHT * 0.65:
            self._bird.jump()
        if self._bird.y < SCREEN_HEIGHT * 0.20:
            pass  # let gravity pull it down

        self._bird.update()

        # Spawn pipes
        if self._frame % self.SPAWN_INTERVAL == 0:
            from game.pipe import Pipe as _Pipe
            self._pipes.append(_Pipe(SCREEN_WIDTH + 40, 180, speed=2.5))

        for p in self._pipes:
            p.update()
        self._pipes = [p for p in self._pipes if not p.off_screen()]

        # Reset bird if it escapes vertically (keep the animation going)
        if self._bird.y < 0 or self._bird.y > SCREEN_HEIGHT:
            self._reset_bird()
            self._pipes.clear()

    def draw(self, surface):
        # Draw pipes with slight transparency to keep them subtle
        pipe_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        for p in self._pipes:
            p.draw(pipe_surf)
        # 50 % alpha overlay
        pipe_surf.set_alpha(128)
        surface.blit(pipe_surf, (0, 0))

        # Draw bird
        self._bird.draw(surface)


# ---------------------------------------------------------------------------
#  Screen: Main Menu  (PLAY / SETTINGS / CREDITS / QUIT)
# ---------------------------------------------------------------------------

def _main_menu_screen(screen, clock):
    """Polished main menu.  Returns: 'play', 'settings', 'credits', 'quit'."""
    W, H = SCREEN_WIDTH, SCREEN_HEIGHT
    bg   = BackgroundRenderer()
    sim  = _MenuBgSim()

    btn_w, btn_h = 190, 46
    btn_x = 28              # left-aligned column

    # Button vertical band starts at 40 % from the top
    btn_top = int(H * 0.42)
    GAP = 12

    btn_play     = _Button((btn_x, btn_top,                   btn_w, btn_h), "PLAY",
                            (40, 180, 70),  (70, 220, 110))
    btn_settings = _Button((btn_x, btn_top + (btn_h + GAP),   btn_w, btn_h), "SETTINGS",
                            (45, 110, 200), (75, 150, 240))
    btn_credits  = _Button((btn_x, btn_top + 2 * (btn_h + GAP), btn_w, btn_h), "CREDITS",
                            (140, 60, 180), (180, 90, 220))
    btn_quit     = _Button((btn_x, btn_top + 3 * (btn_h + GAP), btn_w, btn_h), "QUIT",
                            (180, 45, 45),  (220, 80, 80))

    buttons = [btn_play, btn_settings, btn_credits, btn_quit]
    bg_frame = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return "quit"
            if btn_play.is_clicked(event):     return "play"
            if btn_settings.is_clicked(event): return "settings"
            if btn_credits.is_clicked(event):  return "credits"
            if btn_quit.is_clicked(event):     return "quit"

        # Animate background
        sim.update()
        bg.update(pipes_passed=bg_frame // 30)  # slow sky progression on menu
        bg.draw(screen)
        bg_frame += 1

        # Draw animated bird+pipes behind everything
        sim.draw(screen)

        # ---- Dark left-side card for readability -------------------------
        card_w = btn_w + 56
        card_h = H - 20
        card_surf = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        card_surf.fill((8, 12, 30, 200))
        screen.blit(card_surf, (0, 10))
        # Subtle right border on the card
        pygame.draw.line(screen, (80, 120, 200, 120),
                         (card_w, 10), (card_w, H - 10), 2)

        # ---- Title -------------------------------------------------------
        _shadow_text(screen, "FLAPPY",
                     _font(42, bold=True), (255, 235, 70), (18, 28), shadow_offset=2)
        _shadow_text(screen, "ADAPT",
                     _font(42, bold=True), (100, 200, 255), (18, 76), shadow_offset=2)

        # ---- Thin accent rule under title --------------------------------
        pygame.draw.line(screen, (80, 160, 255), (18, 128), (card_w - 18, 128), 2)

        # ---- Tagline -----------------------------------------------------
        tag_f = _font(12, bold=False)
        _shadow_text(screen, "Smart Difficulty · Adaptive ML",
                     tag_f, (180, 215, 255), (18, 136), shadow_offset=1)

        # ---- Buttons -----------------------------------------------------
        for btn in buttons:
            btn.draw(screen)

        # ---- Controls hint at the bottom of the card --------------------
        hint_f = _font(11)
        _shadow_text(screen, "SPACE / Click to flap",
                     hint_f, (160, 190, 230), (18, H - 40), shadow_offset=1)
        _shadow_text(screen, "ESC to quit",
                     hint_f, (160, 190, 230), (18, H - 24), shadow_offset=1)

        pygame.display.flip()
        clock.tick(FPS)


# ---------------------------------------------------------------------------
#  Screen: Settings
# ---------------------------------------------------------------------------

def _settings_screen(screen, clock):
    """Simple settings stub – returns when the player presses Back."""
    W, H = SCREEN_WIDTH, SCREEN_HEIGHT
    btn_back = _Button((W // 2 - 80, H - 90, 160, 46), "BACK",
                       (70, 100, 180), (100, 140, 220))
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                return
            if btn_back.is_clicked(event):
                return

        screen.fill((10, 14, 32))
        _centred_shadow_text(screen, "SETTINGS", _font(38, bold=True),
                             (200, 230, 255), 60, shadow_offset=2)
        _centred_shadow_text(screen, "(Coming soon)", _font(18),
                             (160, 180, 210), 130, shadow_offset=1)
        btn_back.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)


# ---------------------------------------------------------------------------
#  Screen: Credits
# ---------------------------------------------------------------------------

def _credits_screen(screen, clock):
    """Credits screen – returns when the player presses Back."""
    W, H = SCREEN_WIDTH, SCREEN_HEIGHT
    btn_back = _Button((W // 2 - 80, H - 90, 160, 46), "BACK",
                       (70, 100, 180), (100, 140, 220))
    lines = [
        ("FLAPPY ADAPT",   _font(34, bold=True), (255, 235, 70)),
        ("Version 2.0",     _font(16),            (200, 220, 255)),
        ("",               None,                  None),
        ("Design & ML",    _font(16, bold=True),  (160, 200, 255)),
        ("Dynamic Difficulty Adaptation", _font(14), (200, 220, 255)),
        ("",               None,                  None),
        ("MAHAROGA mode inspired by", _font(14),   (180, 140, 230)),
        ("Jujutsu Kaisen \u2014 Domain Expansion", _font(14), (200, 160, 255)),
        ("",               None,                  None),
        ("Built with Python + pygame-ce", _font(13), (160, 185, 215)),
        ("scikit-learn  ·  numpy  ·  joblib", _font(13), (160, 185, 215)),
    ]
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                return
            if btn_back.is_clicked(event):
                return

        screen.fill((10, 14, 32))
        y = 40
        for text, font, color in lines:
            if font is None:
                y += 12
                continue
            w = font.size(text)[0]
            x = W // 2 - w // 2
            _shadow_text(screen, text, font, color, (x, y), shadow_offset=1)
            y += font.size(text)[1] + 6

        btn_back.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)


# ---------------------------------------------------------------------------
#  Screen: Difficulty Selection
# ---------------------------------------------------------------------------

# Maharoga particle effect (floating purple/gold sparks behind the card)
class _MaharogaParticle:
    def __init__(self, x, y):
        import random
        self.x = float(x)
        self.y = float(y)
        self.vx = random.uniform(-0.6, 0.6)
        self.vy = random.uniform(-1.4, -0.4)
        self.life = random.randint(30, 80)
        self.max_life = self.life
        self.size = random.randint(2, 4)
        c = random.choice([(200, 80, 255), (255, 200, 80), (120, 40, 220)])
        self.color = c

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1

    def alive(self):
        return self.life > 0

    def draw(self, surface):
        alpha = int(255 * (self.life / self.max_life))
        s = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color, alpha), (self.size, self.size), self.size)
        surface.blit(s, (int(self.x - self.size), int(self.y - self.size)))


def _difficulty_screen(screen, clock):
    """Four-card difficulty selection.  Returns the chosen key or 'back'."""
    import random
    W, H = SCREEN_WIDTH, SCREEN_HEIGHT
    bg   = BackgroundRenderer()
    sim  = _MenuBgSim()

    difficulties = ["easy", "medium", "hard", "maharoga"]
    selected = "medium"    # default highlight

    # Card layout: 2x2 grid
    CARD_W, CARD_H = 200, 158
    H_GAP, V_GAP = 16, 14
    grid_w = 2 * CARD_W + H_GAP
    grid_h = 2 * CARD_H + V_GAP
    grid_x = W // 2 - grid_w // 2
    grid_y = 110

    card_rects = {}
    for i, key in enumerate(difficulties):
        col = i % 2
        row = i // 2
        cx = grid_x + col * (CARD_W + H_GAP)
        cy = grid_y + row * (CARD_H + V_GAP)
        card_rects[key] = pygame.Rect(cx, cy, CARD_W, CARD_H)

    btn_play = _Button((W // 2 - 100, grid_y + grid_h + 18, 200, 48),
                       "PLAY!", (60, 200, 90), (90, 240, 130))
    btn_back = _Button((W // 2 - 100, grid_y + grid_h + 76, 200, 40),
                       "BACK", (90, 90, 120), (120, 120, 160))

    maharoga_particles = []
    _mrg_spawn_timer = 0
    bg_frame = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return "back"
                if event.key == pygame.K_RETURN:
                    return selected
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                for key, rect in card_rects.items():
                    if rect.collidepoint(pos):
                        selected = key
                        break
                else:
                    if btn_play.is_clicked(event):
                        return selected
                    if btn_back.is_clicked(event):
                        return "back"

        # Animate background
        sim.update()
        bg.update(pipes_passed=bg_frame // 30)
        bg.draw(screen)
        bg_frame += 1
        sim.draw(screen)

        # Dark overlay to settle the background
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((5, 8, 22, 180))
        screen.blit(ov, (0, 0))

        # ---- Title -------------------------------------------------------
        _centred_shadow_text(screen, "SELECT DIFFICULTY",
                             _font(28, bold=True), (230, 245, 255), 62, shadow_offset=2)
        _centred_shadow_text(screen, "Choose your challenge",
                             _font(14), (160, 195, 240), 98, shadow_offset=1)

        # ---- MAHAROGA particles ------------------------------------------
        _mrg_spawn_timer += 1
        if selected == "maharoga" and _mrg_spawn_timer % 3 == 0:
            r = card_rects["maharoga"]
            maharoga_particles.append(
                _MaharogaParticle(random.uniform(r.left, r.right),
                                  random.uniform(r.top, r.bottom))
            )
        maharoga_particles = [p for p in maharoga_particles if p.alive()]
        for p in maharoga_particles:
            p.update()
            p.draw(screen)

        # ---- Difficulty cards --------------------------------------------
        for key in difficulties:
            preset = DIFFICULTY_PRESETS[key]
            rect   = card_rects[key]
            is_sel = (key == selected)
            is_mrg = (key == "maharoga")

            # Card background
            card_bg = preset["color"] if is_sel else (22, 28, 52)
            card_border = preset["hover_color"] if is_sel else (
                (160, 40, 220) if is_mrg else (50, 65, 110)
            )
            border_w = 3 if is_sel else 1

            _pill(screen, rect.x, rect.y, rect.w, rect.h,
                  bg_color=(*card_bg, 230 if is_sel else 200),
                  border_color=(*card_border, 255 if is_sel else 150),
                  radius=14, border_width=border_w)

            # MAHAROGA: extra glowing purple ring when selected
            if is_mrg and is_sel:
                glow_surf = pygame.Surface((rect.w + 20, rect.h + 20), pygame.SRCALPHA)
                pygame.draw.rect(glow_surf, (160, 40, 255, 60),
                                 (0, 0, rect.w + 20, rect.h + 20), border_radius=18)
                screen.blit(glow_surf, (rect.x - 10, rect.y - 10))

            # Label
            lbl_font = _font(17, bold=True)
            lbl_color = (255, 255, 255) if is_sel else (
                (210, 140, 255) if is_mrg else (180, 200, 240))
            _centred_shadow_text_rect(screen, preset["label"], lbl_font,
                                      lbl_color, rect, y_offset=14)

            # JJK flash for MAHAROGA label
            if is_mrg and is_sel:
                import math as _math
                t_off = _math.sin(time.time() * 4) * 2
                _centred_shadow_text_rect(screen, "\u5c55開",  # 展開 kanji
                                          _font(11, bold=True),
                                          (255, 220, 80), rect, y_offset=2,
                                          shadow_offset=1)

            # Description
            desc_font = _font(11)
            desc_color = (240, 245, 255) if is_sel else (140, 165, 210)
            _centred_shadow_text_rect(screen, preset["description"],
                                      desc_font, desc_color, rect, y_offset=44)

            # Stats row
            stats_str = (f"Gap {preset['gap']}  \u2022  Spd {preset['pipe_speed']:.1f}")
            sf = _font(11)
            sc = (230, 255, 220) if is_sel else (120, 150, 200)
            _centred_shadow_text_rect(screen, stats_str, sf, sc, rect, y_offset=62)

            # MAHAROGA record row (best score + gap)
            if is_mrg:
                mrec = _load_maharoga_record()
                if mrec["best_score"] > 0:
                    rec_str = f"BEST {mrec['best_score']}  •  GAP {mrec['gap_at_best']} px"
                else:
                    rec_str = "No record yet"
                rc = (255, 220, 80) if is_sel else (160, 130, 200)
                _centred_shadow_text_rect(screen, rec_str, _font(10, bold=True),
                                          rc, rect, y_offset=80)

            # Selected checkmark badge
            if is_sel:
                badge_txt = "\u2714 SELECTED"
                bf = _font(10, bold=True)
                bw, bh = bf.size(badge_txt)
                bx = rect.centerx - bw // 2 - 8
                by = rect.bottom - bh - 14
                _pill(screen, bx, by, bw + 16, bh + 6,
                      bg_color=(10, 10, 10, 200),
                      border_color=(255, 255, 255, 160), radius=8)
                _shadow_text(screen, badge_txt, bf, (200, 255, 200),
                             (bx + 8, by + 3), shadow_offset=1)

        # ---- Action buttons ---------------------------------------------
        btn_play.draw(screen)
        btn_back.draw(screen)

        # ---- Current selection label ------------------------------------
        sel_str = f"Selected: {DIFFICULTY_PRESETS[selected]['label']}"
        _centred_shadow_text(screen, sel_str, _font(13, bold=True),
                             (220, 235, 255), grid_y + grid_h + 8, shadow_offset=1)

        pygame.display.flip()
        clock.tick(FPS)


def _centred_shadow_text_rect(surface, text, font, color, rect,
                               y_offset=0, shadow_offset=1):
    """Centre text within a pygame.Rect at rect.top + y_offset."""
    w = font.size(text)[0]
    x = rect.centerx - w // 2
    y = rect.top + y_offset
    _shadow_text(surface, text, font, color, (x, y), shadow_offset, _SHADOW_DARK)


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

        # Maharoga: show gap at best-scoring run
        if mode_name == "maharoga":
            mrec = _load_maharoga_record()
            if mrec["best_score"] > 0:
                gap_lbl = f"Gap at best: {mrec['gap_at_best']} px"
                _centred_shadow_text(screen, gap_lbl,
                                     _font(13, bold=True), (200, 170, 255),
                                     panel_y + 178, shadow_offset=1)

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

def _draw_hud(screen, score, current_gap, mode_name, pipe_speed=None,
              debug_info: dict = None):
    """Draw score, mode tag, and optional adaptive debug info.

    All elements are placed in clean, semi-transparent rounded pill backings
    with subtle borders so they are 100% readable across every sky phase
    and never obscured when pipes scroll through the upper screen.

    debug_info – dict returned by DataDrivenAdaptiveController.debug_info().
                 When present, renders a compact dev panel in the bottom-right
                 corner (not visible in fixed mode).
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

    # ---- Developer debug panel (bottom-right corner, Maharoga only) --------
    if debug_info:
        min_g    = debug_info.get("estimated_min_gap", "?")
        n_samp   = debug_info.get("n_training_samples", 0)
        trained  = debug_info.get("model_trained", False)
        prob     = debug_info.get("last_prob")
        t_at     = debug_info.get("model_trained_at", "never")
        reason   = debug_info.get("last_reason", "")

        src_lbl  = f"ML({t_at})" if trained else "FALLBACK"
        prob_lbl = f"  P={prob:.2f}" if prob is not None else ""
        # Truncate reason to fit comfortably
        reason_short = reason[:38] + "…" if len(reason) > 38 else reason
        lines = [
            f"Gap:{int(current_gap)}  MinGap:{min_g}  {src_lbl}",
            f"Samples:{n_samp}{prob_lbl}",
            f"{reason_short}",
        ]
        df2 = _font(11, bold=True)
        line_h = df2.size("A")[1] + 2
        panel_w = max(df2.size(l)[0] for l in lines) + 20
        panel_h = len(lines) * line_h + 8
        panel_x = SCREEN_WIDTH - panel_w - 6
        panel_y = SCREEN_HEIGHT - panel_h - 6
        _pill(screen, panel_x, panel_y, panel_w, panel_h,
              bg_color=(10, 18, 32, 200), border_color=(60, 120, 200, 120), radius=7)
        for i, line in enumerate(lines):
            col = (160, 220, 255) if i == 0 else (180, 200, 240)
            _shadow_text(screen, line, df2, col,
                         (panel_x + 8, panel_y + 4 + i * line_h), shadow_offset=1)


# ---------------------------------------------------------------------------
#  Maharoga 100-point Domain Expansion event
# ---------------------------------------------------------------------------
MAHAROGA_100_ENABLED        = True   # set False to disable the event
MAHAROGA_100_EXTRA_NARROWING = 10    # extra px subtracted from gap after event
MAHAROGA_100_CHALLENGE_LABEL = "DOMAIN EXPANSION"  # on-screen announcement


def _maharoga_100_event(screen, clock, bg, pipes_passed):
    """Play a short in-game animation when the player hits 100 pipes in Maharoga.

    Visual sequence (takes ~2.5 s at 60 FPS):
      Frame 0-30:   Screen flashes purple → fades to dark overlay
      Frame 30-90:  Expanding purple ring + "DOMAIN EXPANSION" text bounces in
      Frame 90-150: Subtitle "Mahoraga has adapted…" fades in, ring shrinks
      Frame 150+:   Returns

    Returns when the animation completes or the player presses SPACE/click to skip.
    """
    W, H = SCREEN_WIDTH, SCREEN_HEIGHT
    PURPLE1 = (130, 20, 190)
    PURPLE2 = (200, 60, 255)
    GOLD    = (255, 215, 60)

    total_frames = 180  # 3 s at 60 fps
    title_font   = _font(38, bold=True)
    sub_font     = _font(17, bold=True)
    hint_font    = _font(13, bold=False)

    for frame in range(total_frames):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_SPACE, pygame.K_ESCAPE, pygame.K_RETURN):
                    return "continue"
            if event.type == pygame.MOUSEBUTTONDOWN:
                return "continue"

        # --- Draw background (frozen sky) ---
        bg.update(pipes_passed=pipes_passed)
        bg.draw(screen)

        # --- Dark vignette overlay (ramps from 0 → 200) ---
        dark_a = min(200, int(frame * 200 / 60))
        vignette = pygame.Surface((W, H), pygame.SRCALPHA)
        vignette.fill((5, 0, 20, dark_a))
        screen.blit(vignette, (0, 0))

        # --- Expanding ring ---
        t = frame / total_frames
        ring_r = int(30 + t * W * 0.8)
        ring_a = max(0, int(220 * (1 - t * 1.4)))
        if ring_a > 0:
            ring_surf = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (*PURPLE2, ring_a), (ring_r + 2, ring_r + 2), ring_r, 4)
            screen.blit(ring_surf, (W // 2 - ring_r - 2, H // 2 - ring_r - 2))

        # --- Inner glow pulse ---
        glow_r = int(60 + 20 * abs(0.5 - (frame % 60) / 60))
        glow_s = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_s, (*PURPLE1, 80), (glow_r, glow_r), glow_r)
        screen.blit(glow_s, (W // 2 - glow_r, H // 2 - glow_r))

        # --- DOMAIN EXPANSION title (scales in over frames 20-60) ---
        if frame >= 20:
            title_t = min(1.0, (frame - 20) / 40)
            title_a = int(255 * title_t)
            title_surf = title_font.render(MAHAROGA_100_CHALLENGE_LABEL, True, GOLD)
            alpha_surf = pygame.Surface(title_surf.get_size(), pygame.SRCALPHA)
            alpha_surf.blit(title_surf, (0, 0))
            alpha_surf.set_alpha(title_a)
            screen.blit(alpha_surf, (W // 2 - alpha_surf.get_width() // 2, H // 2 - 60))

            # Sub-label
            if frame >= 80:
                sub_a = min(255, int(255 * (frame - 80) / 40))
                sub_surf = sub_font.render("Mahoraga has adapted  •  The trial continues", True, (200, 170, 255))
                sub_surf.set_alpha(sub_a)
                screen.blit(sub_surf, (W // 2 - sub_surf.get_width() // 2, H // 2 + 10))

        # --- 100 badge ---
        if frame >= 30:
            badge_a = min(255, int(255 * (frame - 30) / 30))
            badge_font = _font(28, bold=True)
            badge_surf = badge_font.render("100", True, (255, 100, 60))
            badge_surf.set_alpha(badge_a)
            screen.blit(badge_surf, (W // 2 - badge_surf.get_width() // 2, H // 2 - 110))

        # --- Skip hint ---
        if frame > 60:
            hint_surf = hint_font.render("Press SPACE to continue", True, (180, 150, 220))
            hint_surf.set_alpha(min(255, int(255 * (frame - 60) / 30)))
            screen.blit(hint_surf, (W // 2 - hint_surf.get_width() // 2, H - 44))

        pygame.display.flip()
        clock.tick(FPS)

    return "continue"


# ---------------------------------------------------------------------------
#  Single play_session  (one run until collision or quit)
#  Returns (score, action, gap_at_last_pipe) where action is 'gameover', 'quit'
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
    show_debug_hud = False   # toggled with D key during play

    current_gap    = controller.current_gap
    pipe_speed     = getattr(controller, "pipe_speed", FIXED_PIPE_SPEED)
    spawn_interval = int(getattr(controller, "spawn_interval", FIXED_SPAWN_INTERVAL))
    # Read per-preset delta cap from the controller (FixedController stores it;
    # DataDrivenAdaptiveController falls back to None -> no clamping).
    max_center_delta = getattr(controller, "max_center_delta", None)
    prev_pipe_center = None   # updated each time a pipe is spawned
    gap_at_last_pipe = current_gap   # tracks gap at the most-recently-passed pipe
    _100_event_fired = False          # Maharoga 100-point event fires at most once

    def _sync_controller():
        nonlocal current_gap, pipe_speed, spawn_interval
        current_gap    = controller.current_gap
        pipe_speed     = getattr(controller, "pipe_speed", pipe_speed)
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
                return score, "quit", gap_at_last_pipe
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return score, "quit", gap_at_last_pipe
                if event.key == pygame.K_SPACE:
                    bird.jump()
                if event.key == pygame.K_d:
                    show_debug_hud = not show_debug_hud  # toggle dev overlay
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
            new_pipe = Pipe(
                SCREEN_WIDTH + 40, current_gap,
                speed=pipe_speed,
                prev_center=prev_pipe_center,
                max_center_delta=max_center_delta,
            )
            prev_pipe_center = new_pipe.gap_center
            pipes.append(new_pipe)

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
                gap_at_last_pipe = current_gap   # record gap at this pipe pass
                rec = _outcome(True, p)
                success_history.append(1)
                logger.log(rec)
                controller.on_pipe_outcome(rec)
                _sync_controller()
                last_pass_time = time.time()

                # Maharoga 100-point Domain Expansion event (fires once per run)
                if (mode_name == "maharoga" and score == 100
                        and not _100_event_fired
                        and MAHAROGA_100_ENABLED):
                    _100_event_fired = True
                    ev_result = _maharoga_100_event(screen, clock, bg, score)
                    if ev_result == "quit":
                        return score, "quit", gap_at_last_pipe
                    # Apply challenge-phase narrowing to the ML controller
                    if hasattr(controller, "current_gap"):
                        controller.current_gap = max(
                            getattr(controller, "_estimated_min_gap",
                                    controller.current_gap),
                            controller.current_gap - MAHAROGA_100_EXTRA_NARROWING,
                        )
                        _sync_controller()

        # --- Draw ---
        bg.update(pipes_passed=score)
        bg.draw(screen)
        for p in pipes:
            p.draw(screen)
        bird.draw(screen)
        _dbg = (getattr(controller, "debug_info", lambda: None)()
                if mode_name == "maharoga" else None)
        _draw_hud(screen, score, current_gap, mode_name,
                  pipe_speed if mode_name in ("maharoga", "adaptive") else None,
                  debug_info=_dbg)

        # --- Dev diagnostic overlay (toggle with D) ---
        if show_debug_hud:
            from game.config import BIRD_RADIUS, GRAVITY, JUMP_VELOCITY
            diag_lines = [
                f"Mode: {mode_name.upper()}",
                f"Gap: {int(current_gap)}  Speed: {pipe_speed:.2f}  Interval: {spawn_interval}",
                f"Gravity: {GRAVITY}  Jump: {JUMP_VELOCITY}  Hitbox r: {BIRD_RADIUS}",
                f"Delta cap: {max_center_delta}  ML override: {getattr(controller, 'ml_override', '?')}",
                f"Bird y: {bird.y:.1f}  vel: {bird.velocity:.2f}",
            ]
            df3 = _font(12, bold=True)
            lh = df3.size("A")[1] + 2
            pw = max(df3.size(l)[0] for l in diag_lines) + 16
            ph = len(diag_lines) * lh + 8
            _pill(screen, 6, SCREEN_HEIGHT - ph - 6, pw, ph,
                  bg_color=(0, 0, 0, 210), border_color=(255, 200, 0, 180), radius=7)
            for i, line in enumerate(diag_lines):
                _shadow_text(screen, line, df3, (255, 240, 120),
                             (14, SCREEN_HEIGHT - ph + i * lh), shadow_offset=1)

        pygame.display.flip()
        clock.tick(FPS)

    return score, "gameover", gap_at_last_pipe


# ---------------------------------------------------------------------------
#  play_human  – main entry point for human play
# ---------------------------------------------------------------------------

def play_human(controller, session_id=None):
    """Full human-play loop: Main Menu → Difficulty → Game → GameOver → loop.

    The `controller` argument is kept for CLI compatibility but is ignored when
    the player chooses a difficulty from the GUI (the GUI creates its own
    controller per selected difficulty).
    """
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("FLAPPY ADAPT")
    clock = pygame.time.Clock()

    from controllers.fixed import FixedController
    from controllers.dda_controller import DataDrivenAdaptiveController

    session_id = session_id or str(int(time.time()))
    bg = BackgroundRenderer()

    state = "menu"
    episode = 0
    active_ctrl = None
    mode_name = "medium"       # tracks selected difficulty key
    last_score = 0
    _maharoga_ctrl = None      # reused across sessions to preserve ML learning

    while True:
        # ------------------------------------------------------------------ #
        if state == "menu":
            choice = _main_menu_screen(screen, clock)
            if choice == "quit":
                break
            elif choice == "play":
                state = "difficulty"
            elif choice == "settings":
                _settings_screen(screen, clock)
                # returns to menu
            elif choice == "credits":
                _credits_screen(screen, clock)
                # returns to menu

        # ------------------------------------------------------------------ #
        elif state == "difficulty":
            chosen = _difficulty_screen(screen, clock)
            if chosen == "quit":
                break
            elif chosen == "back":
                state = "menu"
            else:
                mode_name = chosen
                preset = DIFFICULTY_PRESETS[mode_name]
                if mode_name == "maharoga":
                    # Reuse the ML controller across runs to preserve learned state
                    # (cross-session evidence and model weights persist).
                    if _maharoga_ctrl is None:
                        _maharoga_ctrl = DataDrivenAdaptiveController(
                            initial_gap=preset["gap"],
                            preset_pipe_speed=preset["pipe_speed"],
                            preset_spawn_interval=preset["spawn_interval"],
                            debug=True,  # enable console DDA diagnostics
                        )
                        # Store delta cap so _play_session can read it
                        _maharoga_ctrl.max_center_delta = preset.get("max_center_delta")
                    active_ctrl = _maharoga_ctrl
                else:
                    active_ctrl = FixedController(
                        gap=preset["gap"],
                        ml_override=preset.get("ml_override", False),
                        max_center_delta=preset.get("max_center_delta", 90),
                    )
                    active_ctrl.pipe_speed    = preset["pipe_speed"]
                    active_ctrl.spawn_interval = preset["spawn_interval"]
                active_ctrl.reset()
                logger = GameLogger(session_id, mode_name)
                state = "game"

        # ------------------------------------------------------------------ #
        elif state == "game":
            episode += 1
            score, action, gap_at_pipe = _play_session(
                screen, clock, active_ctrl, mode_name, logger, episode, bg
            )

            # Notify ML controller that the run ended (triggers retraining)
            if mode_name == "maharoga" and hasattr(active_ctrl, "on_run_end"):
                active_ctrl.on_run_end(died=(action == "gameover"))

            if action == "quit":
                break

            # Update best score (keyed by difficulty)
            best = _load_best(mode_name)
            if score > best:
                _save_best(mode_name, score)
                # For Maharoga, also persist gap at the best-scoring pipe
                if mode_name == "maharoga":
                    _save_maharoga_record(score, gap_at_pipe)

            state = "gameover"
            last_score = score

        # ------------------------------------------------------------------ #
        elif state == "gameover":
            best = _load_best(mode_name)
            action = _gameover_screen(
                screen, clock, last_score, best, mode_name, bg, last_score
            )
            if action == "quit":
                break
            elif action == "retry":
                # Reset per-run stats but preserve ML learning for MAHAROGA
                active_ctrl.reset()
                state = "game"
            elif action == "home":
                state = "menu"

    pygame.quit()