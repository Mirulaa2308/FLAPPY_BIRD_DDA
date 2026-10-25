import os
import pygame
os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()

_FONT_NAMES = "tahoma, verdana, trebuchetms, arial"
f16b = pygame.font.SysFont(_FONT_NAMES, 16, bold=True)
print("f16b best width:", f16b.size("Best Fixed: 9999   Best Adaptive: 9999"))
f15 = pygame.font.SysFont(_FONT_NAMES, 15, bold=False)
longest = "  Gets harder when you fly well, easier when you struggle."
print("longest desc line width:", f15.size(longest))
print("x=95 + width:", 95 + f15.size(longest)[0])
