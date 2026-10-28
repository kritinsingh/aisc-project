"""Global settings and the colour palette."""

# ---- grid / window ---------------------------------------------------------
CELL = 30
COLS, ROWS = 31, 25            # odd numbers -> perfect mazes
GRID_W, GRID_H = COLS * CELL, ROWS * CELL
SIDEBAR_W = 350
WIDTH, HEIGHT = GRID_W + SIDEBAR_W, GRID_H
FPS = 60

MUD_COST = 5                   # rough terrain costs 5x to cross

# ---- colours ---------------------------------------------------------------
BG_TOP = (12, 18, 36)
BG_BOTTOM = (6, 9, 20)
SIDEBAR_BG = (9, 13, 26)
PANEL = (17, 24, 45)
PANEL_HI = (29, 40, 72)
BORDER = (42, 56, 96)

TEXT = (226, 232, 245)
MUTED = (127, 141, 173)
DIM = (82, 96, 130)

CYAN = (34, 211, 238)
CYAN_DEEP = (30, 150, 205)
VIOLET = (139, 92, 246)
PINK = (244, 63, 94)
GREEN = (52, 211, 153)
AMBER = (251, 191, 36)
YELLOW = (250, 204, 21)

PRIMARY_A = (45, 212, 238)
PRIMARY_B = (129, 140, 248)

WALL_TOP = (116, 134, 190)
WALL_BOT = (62, 76, 122)
MUD = (136, 94, 54)
