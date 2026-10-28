"""Central configuration for the game and difficulty parameters."""

SCREEN_WIDTH = 480
SCREEN_HEIGHT = 640
FPS = 60

BIRD_X = 100
BIRD_START_Y = SCREEN_HEIGHT // 2
GRAVITY = 0.38          # was 0.5 – gentler fall gives more control at all levels
JUMP_VELOCITY = -8.0    # was -9.0 – reduced magnitude → less overshoot, smoother arc
BIRD_RADIUS = 14        # was 18 – smaller hitbox matches visible sprite better

PIPE_WIDTH = 70
PIPE_MIN_TOP = 80           # was 60 – top pipe can't hug the ceiling
PIPE_MAX_TOP_MARGIN = 130   # was 100 – bottom pipe can't hug the floor
PIPE_SPAWN_INTERVAL = 90    # frames between pipe spawns (fixed mode baseline)
PIPE_SPEED = 3.0            # pixels per frame (fixed mode baseline)

GAP_MIN = 90
GAP_MAX = 260
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

# ---------------------------------------------------------------------------
#  Difficulty presets  (gap, pipe_speed, spawn_interval, max_center_delta)
#  MAHAROGA uses the DataDrivenAdaptiveController (ML-adaptive).
#
#  max_center_delta: max px shift between consecutive pipe gap-centres.
#    Caps procedural randomness so no pipe arrangement is unreachable.
#  ml_override: True only for MAHAROGA – lets the ML controller adjust knobs.
#    False for Easy/Medium/Hard – preset values must stay fixed during play.
# ---------------------------------------------------------------------------
DIFFICULTY_PRESETS = {
    "easy": {
        "gap":              250,   # very wide – beginner-friendly
        "pipe_speed":       2.0,   # slow – more time to react
        "spawn_interval":   120,   # 2 s between pipes at 60 FPS
        "max_center_delta": 55,    # consecutive gap centres stay close
        "ml_override":      False, # ML must NOT increase Easy difficulty
        "label":            "EASY",
        "description":      "Wide gaps · Slow pipes · Chill vibes",
        "color":            (60,  200, 100),
        "hover_color":      (90,  240, 140),
    },
    "medium": {
        "gap":              170,
        "pipe_speed":       2.8,
        "spawn_interval":   95,
        "max_center_delta": 90,
        "ml_override":      False,
        "label":            "MEDIUM",
        "description":      "Classic Flappy · Fair challenge",
        "color":            (40,  120, 220),
        "hover_color":      (70,  160, 255),
    },
    "hard": {
        "gap":              120,
        "pipe_speed":       3.8,
        "spawn_interval":   78,
        "max_center_delta": 120,
        "ml_override":      False,
        "label":            "HARD",
        "description":      "Narrow gaps · Fast pipes · Intense",
        "color":            (200,  90,  30),
        "hover_color":      (240, 130,  60),
    },
    "maharoga": {
        # MAHAROGA is ML-adaptive; these are only the initial starting values.
        # The DataDrivenAdaptiveController adjusts them over time.
        "gap":              115,
        "pipe_speed":       4.2,
        "spawn_interval":   70,
        "max_center_delta": 140,
        "ml_override":      True,  # ML adapts all knobs
        "label":            "MAHAROGA",
        "description":      "Domain Expansion · ML adapts to YOU",
        "color":            (130,  20, 180),
        "hover_color":      (170,  50, 220),
    },
}

# --- Sky repeating-cycle progression ---
# Period of 40 pipes: Day(0-9) → Evening(10-19) → Night(20-39) → repeat
SKY_CYCLE_PERIOD     = 40   # pipes per full cycle
SKY_DAY_END          = 10   # cycle-relative pipe at which day ends / evening begins
SKY_EVENING_END      = 20   # cycle-relative pipe at which evening ends / night begins

# Legacy aliases kept so background.py can still import them
SKY_EVENING_START = SKY_DAY_END
SKY_NIGHT_START   = SKY_EVENING_END

# Colors (fallback / pipe / text)
COLOR_BIRD = (255, 215, 0)
COLOR_PIPE = (34, 139, 34)
COLOR_PIPE_HIGHLIGHT = (60, 180, 60)
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_SHADOW = (0, 0, 0)

LOG_DIR = "data/logs"
BEST_SCORE_FILE = "data/best_score.txt"