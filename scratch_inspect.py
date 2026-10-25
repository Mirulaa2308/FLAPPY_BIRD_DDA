import os
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
pygame.init()

from game.config import SCREEN_WIDTH, SCREEN_HEIGHT
from game.background import BackgroundRenderer
from game.bird import Bird
from game.pipe import Pipe
from game.game import (
    _home_screen, _draw_hud, _gameover_screen, _Button,
    _font, _shadow_text, _centred_shadow_text
)

out_dir = os.path.join(os.path.dirname(__file__), "inspect_screens")
os.makedirs(out_dir, exist_ok=True)

# 1. Render Home Screen
screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
bg = BackgroundRenderer()
bg.update(pipes_passed=0)
bg.draw(screen)

# Draw what _home_screen draws on one frame
_centred_shadow_text(screen, "FLAPPY ADAPT",
                     _font(50, bold=True), (255, 255, 100), 72, shadow_offset=3)
_centred_shadow_text(screen, "A Flappy Bird with Smart Difficulty",
                     _font(18), (200, 240, 255), 138)

W, H = SCREEN_WIDTH, SCREEN_HEIGHT
btn_w, btn_h = 290, 54
btn_x = W // 2 - btn_w // 2

bf_str  = f"Best Fixed: 12"
ba_str  = f"Best Adaptive: 8"
sf16    = _font(16, bold=True)
gap_px  = 24
bf_w    = sf16.size(bf_str)[0]
ba_w    = sf16.size(ba_str)[0]
total_w = bf_w + gap_px + ba_w
lx      = W // 2 - total_w // 2
_shadow_text(screen, bf_str,  sf16, (255, 230, 80),  (lx, 226))
_shadow_text(screen, ba_str,  sf16, (100, 255, 160), (lx + bf_w + gap_px, 226))

btn_fixed    = _Button((btn_x, 272, btn_w, btn_h),
                       "Play Fixed Difficulty",
                       (40, 120, 210), (70, 160, 255))
btn_adaptive = _Button((btn_x, 342, btn_w, btn_h),
                       "Play Adaptive Difficulty",
                       (40, 165, 90), (70, 210, 120))
btn_fixed.draw(screen)
btn_adaptive.draw(screen)

desc_font = _font(15)
line_h    = 20
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

desc_top = 412
for i, line in enumerate(fixed_desc):
    col = (255, 255, 150) if i == 0 else (215, 240, 255)
    _shadow_text(screen, line, desc_font, col, (btn_x, desc_top + i * line_h))

adaptive_top = desc_top + len(fixed_desc) * line_h + 10
for i, line in enumerate(adaptive_desc):
    col = (160, 255, 180) if i == 0 else (215, 240, 255)
    _shadow_text(screen, line, desc_font, col, (btn_x, adaptive_top + i * line_h))

_centred_shadow_text(screen, "SPACE / Click to jump   •   ESC to quit",
                     _font(14), (200, 220, 240), H - 26)

pygame.image.save(screen, os.path.join(out_dir, "01_home_screen.png"))

# 2. Render HUD screens (Day, Evening, Night)
for phase_name, pipes_passed in [("day", 0), ("evening", 15), ("night", 30)]:
    s = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
    bg_hud = BackgroundRenderer()
    bg_hud.update(pipes_passed=pipes_passed)
    bg_hud.draw(s)
    # Draw some pipes
    p1 = Pipe(180, 150, speed=3.5)
    p1.draw(s)
    p2 = Pipe(360, 140, speed=3.5)
    p2.draw(s)
    # Draw bird
    b = Bird()
    b.draw(s)
    # Draw HUD
    _draw_hud(s, score=pipes_passed, current_gap=150, mode_name="adaptive", pipe_speed=3.5)
    pygame.image.save(s, os.path.join(out_dir, f"02_hud_{phase_name}.png"))

# 3. Render GameOver Screen
s_gov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
bg_gov = BackgroundRenderer()
bg_gov.update(pipes_passed=15)
bg_gov.draw(s_gov)

overlay = pygame.Surface((W, H), pygame.SRCALPHA)
overlay.fill((0, 0, 0, 185))
s_gov.blit(overlay, (0, 0))

panel_w, panel_h = 352, 250
panel_x = W // 2 - panel_w // 2
panel_y = H // 2 - panel_h // 2 - 28
panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
panel_surf.fill((18, 18, 48, 215))
pygame.draw.rect(panel_surf, (110, 150, 255, 140),
                 (0, 0, panel_w, panel_h), 2, border_radius=16)
s_gov.blit(panel_surf, (panel_x, panel_y))

_centred_shadow_text(s_gov, "GAME OVER",
                     _font(44, bold=True), (255, 75, 75),
                     panel_y + 20, shadow_offset=3)
_centred_shadow_text(s_gov, "Mode: Adaptive",
                     _font(16), (160, 205, 255), panel_y + 78)
_centred_shadow_text(s_gov, "Score: 15",
                     _font(26, bold=True), (255, 255, 100),
                     panel_y + 110, shadow_offset=2)
_centred_shadow_text(s_gov, "Best: 15   ★ NEW BEST!",
                     _font(20, bold=True), (90, 255, 155),
                     panel_y + 150)

btn_retry = _Button((W // 2 - 200 - 12, H // 2 + 62, 200, 50),
                    "Retry",  (190, 70, 40), (235, 115, 75))
btn_home  = _Button((W // 2 + 12,          H // 2 + 62, 200, 50),
                    "Home",   (45,  90, 195), (75, 135, 235))
btn_retry.draw(s_gov)
btn_home.draw(s_gov)

_centred_shadow_text(s_gov, "R = Retry     H = Home",
                     _font(14), (175, 195, 215), H // 2 + 128)

pygame.image.save(s_gov, os.path.join(out_dir, "03_gameover.png"))

print("Rendered all screens to", out_dir)
