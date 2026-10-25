import os
import pygame
pygame.init()
f = pygame.font.SysFont("Segoe UI, Calibri, Arial", 15)
print("Font name:", f)
print("Default font:", pygame.font.get_default_font())
print("Match for 'Segoe UI':", pygame.font.match_font("segoeui"))
print("Match for 'Arial':", pygame.font.match_font("arial"))
print("Match for 'Calibri':", pygame.font.match_font("calibri"))
print("SysFont argument parsing:")
# In pygame, SysFont takes name as a comma-separated string or list?
# SysFont(name, size, bold=False, italic=False)
# How does pygame handle "Segoe UI, Calibri, Arial"?
f2 = pygame.font.SysFont("segoeui", 15)
print("f2:", f2)
