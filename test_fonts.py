import pygame

pygame.init()
print("All available fonts containing common names:")
sys_fonts = pygame.font.get_fonts()
for target in ["segoe", "arial", "tahoma", "verdana", "trebuchet", "consolas", "calibri"]:
    matches = [f for f in sys_fonts if target in f]
    print(f"  {target}: {matches}")

# Let's see what SysFont loads for these:
for name in ["segoeui", "tahoma", "verdana", "trebuchetms", "arial"]:
    f = pygame.font.SysFont(name, 16)
    bold_f = pygame.font.SysFont(name, 16, bold=True)
    print(f"SysFont('{name}', 16) -> metrics for 'Flappy': {f.size('Flappy')}")
