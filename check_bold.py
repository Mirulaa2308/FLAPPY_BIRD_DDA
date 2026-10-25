import pygame
pygame.init()
f_bold = pygame.font.SysFont("tahoma, verdana, trebuchetms, arial", 16, bold=True)
print("Bold font object:", f_bold)
print("Bold metric for 'Score':", f_bold.size("Score"))
f_reg = pygame.font.SysFont("tahoma, verdana, trebuchetms, arial", 16, bold=False)
print("Reg metric for 'Score':", f_reg.size("Score"))
