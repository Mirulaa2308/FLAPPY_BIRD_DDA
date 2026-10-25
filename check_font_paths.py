import pygame
pygame.init()
for f in ["tahoma", "verdana", "trebuchetms", "arial", "segoeui", "calibri"]:
    path = pygame.font.match_font(f)
    print(f"{f}: {path}")
