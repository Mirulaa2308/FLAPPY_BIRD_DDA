import os
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
pygame.init()

from game.config import SCREEN_WIDTH, SCREEN_HEIGHT
from game.background import BackgroundRenderer
from game.bird import Bird
from game.pipe import Pipe

# Preferred font list using Tahoma / Verdana / Trebuchet MS / Arial
_FONT_NAMES = "tahoma, verdana, trebuchetms, arial"
_FONT_CACHE = {}

def _font(size, bold=False):
    key = (size, bold)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = pygame.font.SysFont(_FONT_NAMES, size, bold=bold)
        except Exception:
            _FONT_CACHE[key] = pygame.font.Font(None, size)
    return _FONT_CACHE[key]

def _pill(surface, x, y, w, h, bg_color=(0, 0, 0, 160), border_color=(255, 255, 255, 60), radius=8, border_width=1):
    """Draw a semi-transparent rounded backing panel/pill."""
    pill_surf = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(pill_surf, bg_color, (0, 0, w, h), border_radius=radius)
    if border_color and border_width > 0:
        pygame.draw.rect(pill_surf, border_color, (0, 0, w, h), border_width, border_radius=radius)
    surface.blit(pill_surf, (x, y))

def _shadow_text(surface, text, font, color, pos, shadow_offset=1, shadow_color=(0, 0, 0)):
    """Crisp text with subtle outline/drop shadow."""
    if shadow_offset > 0:
        shadow_surf = font.render(text, True, shadow_color)
        o = shadow_offset
        for dx, dy in ((-o, -o), (o, -o), (-o, o), (o, o)):
            surface.blit(shadow_surf, (pos[0] + dx, pos[1] + dy))
    fg = font.render(text, True, color)
    surface.blit(fg, pos)
    return fg.get_rect(topleft=pos)

def _centred_shadow_text(surface, text, font, color, cy, shadow_offset=1, shadow_color=(0, 0, 0)):
    w = font.size(text)[0]
    x = SCREEN_WIDTH // 2 - w // 2
    return _shadow_text(surface, text, font, color, (x, cy), shadow_offset, shadow_color)

class _Button:
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

        font = _font(19, bold=True)
        # Subtle 1px outline for crisp text
        shadow_surf = font.render(self.text, True, (0, 0, 0))
        cx = self.rect.centerx - shadow_surf.get_width() // 2
        cy = self.rect.centery - shadow_surf.get_height() // 2
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            surface.blit(shadow_surf, (cx + dx, cy + dy))
        label = font.render(self.text, True, self.text_color)
        surface.blit(label, (cx, cy))

out_dir = os.path.join(os.path.dirname(__file__), "inspect_screens_v2")
os.makedirs(out_dir, exist_ok=True)

W, H = SCREEN_WIDTH, SCREEN_HEIGHT

# ----------------- 1. Home Screen -----------------
screen = pygame.Surface((W, H))
bg = BackgroundRenderer()
bg.update(pipes_passed=0)
bg.draw(screen)

# Title
_centred_shadow_text(screen, "FLAPPY ADAPT",
                     _font(48, bold=True), (255, 235, 70), 55, shadow_offset=3)

# Subtitle inside a subtle soft pill
sub_text = "A Flappy Bird with Smart Difficulty"
sub_font = _font(16, bold=True)
sub_w, sub_h = sub_font.size(sub_text)
_pill(screen, W // 2 - sub_w // 2 - 12, 114, sub_w + 24, sub_h + 8,
      bg_color=(15, 25, 45, 140), border_color=(120, 170, 240, 100), radius=10)
_centred_shadow_text(screen, sub_text, sub_font, (225, 245, 255), 118, shadow_offset=1)

# Best scores in a sleek badge panel
best_w = 340
best_h = 36
best_x = W // 2 - best_w // 2
_pill(screen, best_x, 158, best_w, best_h,
      bg_color=(12, 20, 38, 170), border_color=(80, 130, 210, 140), radius=12)

bf_str = "Best Fixed: 12"
ba_str = "Best Adaptive: 8"
sf16 = _font(15, bold=True)
bf_w = sf16.size(bf_str)[0]
ba_w = sf16.size(ba_str)[0]
pad = (best_w - bf_w - ba_w) // 3
_shadow_text(screen, bf_str, sf16, (255, 225, 90), (best_x + pad, 166), shadow_offset=1)
_shadow_text(screen, ba_str, sf16, (110, 255, 180), (best_x + pad * 2 + bf_w, 166), shadow_offset=1)

# Buttons
btn_w, btn_h = 300, 52
btn_x = W // 2 - btn_w // 2
btn_fixed = _Button((btn_x, 214, btn_w, btn_h), "Play Fixed Difficulty", (35, 110, 205), (65, 150, 255))
btn_adaptive = _Button((btn_x, 280, btn_w, btn_h), "Play Adaptive Difficulty", (35, 155, 80), (60, 200, 110))
btn_fixed.draw(screen)
btn_adaptive.draw(screen)

# Mode descriptions inside a unified backing card
card_w = 400
card_h = 220
card_x = W // 2 - card_w // 2
card_y = 350
_pill(screen, card_x, card_y, card_w, card_h,
      bg_color=(14, 22, 42, 210), border_color=(90, 140, 220, 150), radius=14, border_width=2)

hdr_font = _font(16, bold=True)
body_font = _font(14)
line_spacing = 21

# Fixed section
_shadow_text(screen, "Fixed Difficulty:", hdr_font, (255, 230, 100), (card_x + 18, card_y + 14), shadow_offset=1)
f_lines = [
    "• Constant pipe gap, speed, and spawn timing.",
    "• Traditional Flappy Bird challenge from start to end.",
]
for i, l in enumerate(f_lines):
    _shadow_text(screen, l, body_font, (225, 240, 255), (card_x + 22, card_y + 40 + i * line_spacing), shadow_offset=1)

# Adaptive section
_shadow_text(screen, "Adaptive Difficulty:", hdr_font, (110, 255, 180), (card_x + 18, card_y + 98), shadow_offset=1)
a_lines = [
    "• Monitors your success rate over the last 5 pipes.",
    "• Dynamically tunes gap size, speed, and interval.",
    "• Gets harder when you excel, easier when you struggle.",
]
for i, l in enumerate(a_lines):
    _shadow_text(screen, l, body_font, (225, 240, 255), (card_x + 22, card_y + 124 + i * line_spacing), shadow_offset=1)

# Bottom hint in a pill
hint_str = "SPACE / Click to jump   •   ESC to quit"
hf = _font(14, bold=True)
hw, hh = hf.size(hint_str)
_pill(screen, W // 2 - hw // 2 - 14, H - 36, hw + 28, hh + 10,
      bg_color=(10, 18, 32, 190), border_color=(80, 130, 200, 120), radius=10)
_centred_shadow_text(screen, hint_str, hf, (230, 245, 255), H - 32, shadow_offset=1)

pygame.image.save(screen, os.path.join(out_dir, "01_home_screen.png"))

# ----------------- 2. Gameplay HUD -----------------
for phase_name, pipes_passed in [("day", 0), ("evening", 15), ("night", 30)]:
    s = pygame.Surface((W, H))
    bg_hud = BackgroundRenderer()
    bg_hud.update(pipes_passed=pipes_passed)
    bg_hud.draw(s)
    p1 = Pipe(180, 150, speed=3.5)
    p1.draw(s)
    p2 = Pipe(360, 140, speed=3.5)
    p2.draw(s)
    b = Bird()
    b.draw(s)

    # Score pill at top center
    score_str = str(pipes_passed)
    score_f = _font(34, bold=True)
    sw, sh = score_f.size(score_str)
    pill_w = max(68, sw + 30)
    pill_h = sh + 10
    _pill(s, W // 2 - pill_w // 2, 8, pill_w, pill_h,
          bg_color=(10, 18, 35, 180), border_color=(255, 255, 255, 120), radius=12, border_width=2)
    _centred_shadow_text(s, score_str, score_f, (255, 255, 255), 12, shadow_offset=1)

    # Mode badge top-left
    mode_str = "Adaptive Mode"
    mf = _font(14, bold=True)
    mw, mh = mf.size(mode_str)
    _pill(s, 10, 10, mw + 20, mh + 10,
          bg_color=(10, 18, 35, 180), border_color=(80, 150, 240, 140), radius=8)
    _shadow_text(s, mode_str, mf, (220, 240, 255), (20, 15), shadow_offset=1)

    # Debug badge top-right
    dbg_str = "Gap 150  •  Spd 3.5"
    df = _font(14, bold=True)
    dw, dh = df.size(dbg_str)
    dbg_x = W - dw - 30
    _pill(s, dbg_x, 10, dw + 20, dh + 10,
          bg_color=(10, 28, 20, 180), border_color=(60, 180, 110, 140), radius=8)
    _shadow_text(s, dbg_str, df, (130, 255, 190), (dbg_x + 10, 15), shadow_offset=1)

    pygame.image.save(s, os.path.join(out_dir, f"02_hud_{phase_name}.png"))

# ----------------- 3. GameOver Screen -----------------
s_gov = pygame.Surface((W, H))
bg_gov = BackgroundRenderer()
bg_gov.update(pipes_passed=15)
bg_gov.draw(s_gov)

overlay = pygame.Surface((W, H), pygame.SRCALPHA)
overlay.fill((0, 0, 0, 180))
s_gov.blit(overlay, (0, 0))

panel_w, panel_h = 370, 310
panel_x = W // 2 - panel_w // 2
panel_y = H // 2 - panel_h // 2 - 15

_pill(s_gov, panel_x, panel_y, panel_w, panel_h,
      bg_color=(16, 22, 45, 235), border_color=(100, 150, 255, 180), radius=16, border_width=2)

# Title
_centred_shadow_text(s_gov, "GAME OVER",
                     _font(44, bold=True), (255, 80, 80), panel_y + 20, shadow_offset=2)

# Mode badge
mode_label = "Mode: Adaptive"
ml_font = _font(15, bold=True)
ml_w, ml_h = ml_font.size(mode_label)
_pill(s_gov, W // 2 - ml_w // 2 - 12, panel_y + 76, ml_w + 24, ml_h + 8,
      bg_color=(25, 40, 75, 180), border_color=(100, 150, 240, 130), radius=8)
_centred_shadow_text(s_gov, mode_label, ml_font, (220, 240, 255), panel_y + 80, shadow_offset=1)

# Score
_centred_shadow_text(s_gov, "Score: 15",
                     _font(28, bold=True), (255, 235, 90), panel_y + 116, shadow_offset=1)

# Best score badge
best_label = "Best: 15  (NEW BEST!)"
bf_font = _font(19, bold=True)
_centred_shadow_text(s_gov, best_label, bf_font, (100, 255, 170), panel_y + 156, shadow_offset=1)

# Buttons inside the card
btn_retry = _Button((panel_x + 22, panel_y + 200, 155, 48),
                    "Retry (R)", (195, 65, 40), (235, 100, 70))
btn_home  = _Button((panel_x + panel_w - 22 - 155, panel_y + 200, 155, 48),
                    "Home (H)", (40, 95, 205), (70, 140, 245))
btn_retry.draw(s_gov)
btn_home.draw(s_gov)

# Card bottom hint
hint_text = "Press R to Retry   •   Press H for Home"
hf2 = _font(13, bold=True)
_centred_shadow_text(s_gov, hint_text, hf2, (180, 205, 235), panel_y + 268, shadow_offset=1)

pygame.image.save(s_gov, os.path.join(out_dir, "03_gameover.png"))

print("V2 screenshots saved.")
