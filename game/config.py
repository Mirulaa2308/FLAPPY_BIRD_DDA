"""Central configuration for the game and difficulty parameters."""

SCREEN_WIDTH = 480
SCREEN_HEIGHT = 640
FPS = 60

BIRD_X = 100
BIRD_START_Y = SCREEN_HEIGHT // 2
GRAVITY = 0.5
JUMP_VELOCITY = -9.0
BIRD_RADIUS = 18          # collision radius (kept conservative vs sprite size)

PIPE_WIDTH = 70
PIPE_MIN_TOP = 60
PIPE_MAX_TOP_MARGIN = 100
PIPE_SPAWN_INTERVAL = 90  # frames between pipe spawns (fixed mode baseline)
PIPE_SPEED = 3.0          # pixels per frame (fixed mode baseline)

GAP_MIN = 90
GAP_MAX = 240
GAP_DEFAULT = 165

# --- Fixed-mode parameters (never change during a run) ---
FIXED_GAP = 165
FIXED_PIPE_SPEED = 3.0
FIXED_SPAWN_INTERVAL = 90

# --- Adaptive-mode starting parameters ---
ADAPTIVE_GAP_START = 165
ADAPTIVE_PIPE_SPEED_START = 3.0
ADAPTIVE_SPAWN_INTERVAL_START = 90
# Adaptive speed/interval bounds
ADAPTIVE_SPEED_MIN = 2.0
ADAPTIVE_SPEED_MAX = 5.5
ADAPTIVE_INTERVAL_MIN = 60
ADAPTIVE_INTERVAL_MAX = 120

# Bird sprite path (relative to project root)
BIRD_SPRITE = "asset/flappy bird asset.png"
BIRD_SPRITE_SIZE = (48, 40)   # target render size preserving ~aspect ratio

# --- Sky progression thresholds (pipes passed) ---
SKY_EVENING_START = 10
SKY_NIGHT_START = 20

# Colors (fallback / pipe / text)
COLOR_BIRD = (255, 215, 0)
COLOR_PIPE = (34, 139, 34)
COLOR_PIPE_HIGHLIGHT = (60, 180, 60)
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_SHADOW = (0, 0, 0)

LOG_DIR = "data/logs"
BEST_SCORE_FILE = "data/best_score.txt"