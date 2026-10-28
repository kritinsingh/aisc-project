"""The simulator: map editing, search animation, the robot and the sidebar."""
from __future__ import annotations

import asyncio
import math
import random

import pygame

from . import config as C
from .algorithms import (ALGO_DETAILS, ALGO_INFO, ALGORITHMS, FRONTIER, VISITED,
                         make_maze, scatter_walls, search)
from .ui import (Button, Fonts, Slider, Toggle, clamp, draw_glow,
                 ease_out_back, gradient_surface, lerp_color)

TOOLS = ("wall", "mud", "erase")
POP_TIME = 0.28            # seconds for the "pop-in" animation of cells


# ---------------------------------------------------------------- helpers
def cell_center(cell):
    return (cell[0] * C.CELL + C.CELL // 2, cell[1] * C.CELL + C.CELL // 2)


def partial_polyline(pts, t):
    """First `t` segments of a polyline (t may be fractional)."""
    k = int(t)
    if k >= len(pts) - 1:
        return list(pts)
    out = list(pts[:k + 1])
    f = t - k
    a, b = pts[k], pts[k + 1]
    out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    return out


def line_cells(a, b):
    """Bresenham line so fast mouse movement never leaves gaps."""
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    out = []
    while True:
        out.append((x0, y0))
        if (x0, y0) == (x1, y1):
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy
    return out


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("PathPilot - Robot Path Planning Simulator")
        self.screen = pygame.display.set_mode((C.WIDTH, C.HEIGHT))
        self.clock = pygame.time.Clock()
        self.fonts = Fonts()
        self.running = True
        self.now = 0.0

        # map
        self.start = (3, C.ROWS // 2)
        self.goal = (C.COLS - 4, C.ROWS // 2)
        self.walls, self.mud, self.born = set(), set(), {}

        # settings (smooth default speed = 22 for observable search)
        self.algo = "astar"
        self.diag = True
        self.tool = "wall"
        self.speed = 22
        self.paused = False
        self.results = {}

        # mouse editing
        self.drag = None
        self.paint_mode = "wall"
        self.last_cell = None

        # effects & animations
        self.particles = []
        self.toast = None            # (text, colour, time_created)
        self.angle = 0.0
        self.active_cell = None
        self.fx = pygame.Surface((C.GRID_W, C.GRID_H), pygame.SRCALPHA)

        self.clear_path()
        self.build_assets()
        self.build_ui()
        self.scatter(announce=False)

    # ------------------------------------------------------------ assets
    def build_assets(self):
        cell, inset = C.CELL, 2
        size = cell - 2 * inset

        # background: subtle space grid + gentle ambient glows
        bg = pygame.Surface((C.GRID_W, C.GRID_H))
        bg.blit(gradient_surface(C.GRID_W, C.GRID_H, C.BG_TOP, C.BG_BOTTOM), (0, 0))
        draw_glow(bg, (220, 160), 360, C.VIOLET, 0.14)
        draw_glow(bg, (C.GRID_W - 160, C.GRID_H - 120), 380, C.CYAN, 0.10)
        tile = pygame.Surface((cell, cell), pygame.SRCALPHA)
        pygame.draw.rect(tile, (140, 170, 255, 12), (1, 1, cell - 2, cell - 2), border_radius=6)
        for x in range(C.COLS):
            for y in range(C.ROWS):
                bg.blit(tile, (x * cell, y * cell))
        self.bg = bg

        # explored cells: cyan -> violet gradient (32 smooth steps)
        self.vis_surfs = []
        for i in range(32):
            col = lerp_color(C.CYAN_DEEP, C.VIOLET, i / 31)
            s = pygame.Surface((cell, cell), pygame.SRCALPHA)
            pygame.draw.rect(s, (*col, 205), (inset, inset, size, size), border_radius=7)
            edge = lerp_color(col, (255, 255, 255), 0.32)
            pygame.draw.rect(s, (*edge, 115), (inset, inset, size, size), 1, border_radius=7)
            self.vis_surfs.append(s)

        # frontier cells: glowing warm amber with center pulse beacon
        s = pygame.Surface((cell, cell), pygame.SRCALPHA)
        pygame.draw.rect(s, (*C.AMBER, 195), (inset, inset, size, size), border_radius=7)
        pygame.draw.rect(s, (255, 245, 190, 230), (inset, inset, size, size), 2, border_radius=7)
        pygame.draw.circle(s, (255, 255, 255, 240), (cell // 2, cell // 2), 3)
        self.front_surf = s

        # walls: bevelled solid obstacle blocks
        s = pygame.Surface((cell, cell), pygame.SRCALPHA)
        s.blit(gradient_surface(size, size, C.WALL_TOP, C.WALL_BOT, True, 7), (inset, inset))
        pygame.draw.rect(s, (205, 218, 250, 140), (inset, inset, size, size), 1, border_radius=7)
        self.wall_surf = s

        # mud: rough brown terrain with clear "5x" cost indicator watermark
        s = pygame.Surface((cell, cell), pygame.SRCALPHA)
        pygame.draw.rect(s, (*C.MUD, 235), (inset, inset, size, size), border_radius=7)
        pygame.draw.rect(s, (190, 140, 90, 130), (inset, inset, size, size), 1, border_radius=7)
        rnd = random.Random(7)
        for _ in range(7):
            pygame.draw.circle(s, (88, 56, 28, 180),
                               (rnd.randint(5, cell - 5), rnd.randint(5, cell - 5)), rnd.choice((1, 2)))
        try:
            m_font = pygame.font.SysFont("arial", 9, bold=True)
            tag = m_font.render("5x", True, (255, 220, 160))
            s.blit(tag, (cell - tag.get_width() - 4, cell - tag.get_height() - 3))
        except Exception:
            pass
        self.mud_surf = s

        # hover highlight
        s = pygame.Surface((cell, cell), pygame.SRCALPHA)
        pygame.draw.rect(s, (255, 255, 255, 34), (1, 1, cell - 2, cell - 2), border_radius=7)
        pygame.draw.rect(s, (255, 255, 255, 100), (1, 1, cell - 2, cell - 2), 1, border_radius=7)
        self.hover_surf = s

        # robot chassis
        r = pygame.Surface((52, 52), pygame.SRCALPHA)
        pygame.draw.rect(r, (8, 12, 26), (12, 10, 20, 7), border_radius=3)      # wheels
        pygame.draw.rect(r, (8, 12, 26), (12, 35, 20, 7), border_radius=3)
        r.blit(gradient_surface(28, 22, (120, 238, 252), (34, 150, 205), True, 7), (12, 15))
        pygame.draw.rect(r, (255, 255, 255, 230), (12, 15, 28, 22), 1, border_radius=7)
        pygame.draw.circle(r, (255, 255, 255), (34, 26), 4)                    # sensor eye
        pygame.draw.circle(r, (10, 18, 40), (35, 26), 2)
        pygame.draw.circle(r, C.PINK, (18, 26), 2)
        self.robot_surf = r

        # logo
        logo = pygame.Surface((40, 40), pygame.SRCALPHA)
        logo.blit(gradient_surface(40, 40, C.PRIMARY_A, C.VIOLET, False, 11), (0, 0))
        pts = [(9, 30), (9, 19), (16, 12), (26, 12), (31, 18), (31, 25)]
        pygame.draw.lines(logo, (255, 255, 255), False, pts, 3)
        pygame.draw.circle(logo, (255, 255, 255), (9, 30), 4)
        pygame.draw.polygon(logo, (255, 255, 255), [(26, 24), (36, 24), (31, 32)])
        self.logo = logo

    # ------------------------------------------------------------ UI layout
    def build_ui(self):
        X = C.GRID_W + 16
        W = C.SIDEBAR_W - 32
        self.X, self.W = X, W
        widgets = []

        # algorithm buttons
        self.algo_buttons = {}
        keys = list(ALGORITHMS)
        bw = (W - 16) // 3
        for i, key in enumerate(keys[:3]):
            self.algo_buttons[key] = Button((X + i * (bw + 8), 82, bw, 32), ALGORITHMS[key],
                                            lambda k=key: self.set_algo(k), size=13)
        bw2 = (W - 8) // 2
        for i, key in enumerate(keys[3:]):
            self.algo_buttons[key] = Button((X + i * (bw2 + 8), 120, bw2, 32), ALGORITHMS[key],
                                            lambda k=key: self.set_algo(k), size=13)
        widgets += list(self.algo_buttons.values())

        # toggles and sliders
        widgets.append(Toggle((X, 246, W, 24), "Diagonal moves", self.diag, self.set_diag))
        self.slider_speed = Slider((X, 274, W, 36), "Speed", 1, 100, self.speed, self.set_speed)
        widgets.append(self.slider_speed)

        # brush buttons
        self.tool_buttons = {}
        tw = (W - 16) // 3
        swatches = {"wall": C.WALL_TOP, "mud": C.MUD, "erase": C.DIM}
        for i, name in enumerate(TOOLS):
            self.tool_buttons[name] = Button((X + i * (tw + 8), 330, tw, 28), name.capitalize(),
                                             lambda n=name: self.set_tool(n), swatch=swatches[name])
        widgets += list(self.tool_buttons.values())

        # primary simulation controls (Run + Pause/Resume)
        run_w = int(W * 0.65)
        pause_w = W - run_w - 8
        self.btn_run = Button((X, 366, run_w, 36), "Run Simulation", self.on_run,
                              kind="primary", icon="play", size=14)
        self.btn_pause = Button((X + run_w + 8, 366, pause_w, 36), "Pause", self.toggle_pause,
                                kind="normal", icon="pause", size=13)
        widgets += [self.btn_run, self.btn_pause]

        # secondary quick actions
        sw = (W - 24) // 4
        for i, (label, fn) in enumerate((("Clear", self.clear_path_ui), ("Maze", self.make_maze),
                                         ("Random", self.scatter), ("Reset", self.reset_all))):
            widgets.append(Button((X + i * (sw + 8), 408, sw, 26), label, fn, size=11))

        # benchmark compare button
        widgets.append(Button((X + W - 92, 546, 92, 24), "Run all", self.compare_all, size=12))

        self.widgets = widgets
        self.refresh_buttons()
        self.update_control_buttons()

    def refresh_buttons(self):
        for key, b in self.algo_buttons.items():
            b.active = key == self.algo
        for name, b in self.tool_buttons.items():
            b.active = name == self.tool

    def update_control_buttons(self):
        if not hasattr(self, "btn_pause"):
            return
        if self.paused:
            self.btn_pause.label = "Resume"
            self.btn_pause.icon = "play"
        else:
            self.btn_pause.label = "Pause"
            self.btn_pause.icon = "pause"

    # ------------------------------------------------------------ settings
    def set_algo(self, key):
        self.algo = key
        self.refresh_buttons()
        self.refresh()

    def set_diag(self, value):
        self.diag = value
        self.refresh()

    def set_speed(self, value):
        self.speed = value

    def set_tool(self, name):
        self.tool = name
        self.refresh_buttons()

    # ------------------------------------------------------------ state & controls
    def clear_path(self):
        self.phase = "idle"          # idle -> search -> path -> robot -> done
        self.paused = False
        self.result = None
        self.cell_state = {}         # cell -> (kind, time, order)
        self.active_cell = None
        self.ev_ptr = 0
        self.ev_acc = 0.0
        self.vis_count = 0
        self.total_visited = 1
        self.path = []
        self.path_t = 0.0
        self.robot_t = 0.0
        self.update_control_buttons()

    def clear_path_ui(self):
        self.clear_path()
        self.show_toast("Path and simulation reset", C.MUTED)

    def run(self, instant=False):
        self.clear_path()
        res = search(self.algo, self.start, self.goal, self.walls, self.mud, self.diag)
        self.result = res
        self.results[self.algo] = res
        self.path = res.path
        self.total_visited = max(2, res.visited)
        if instant:
            for cell, kind in res.events:
                if kind == VISITED:
                    self.cell_state[cell] = (VISITED, self.now - 5, self.vis_count)
                    self.vis_count += 1
                else:
                    self.cell_state[cell] = (FRONTIER, self.now - 5, 0)
            self.ev_ptr = len(res.events)
            self.path_t = robot_end = max(0, len(self.path) - 1)
            self.robot_t = robot_end
            self.phase = "done"
        else:
            self.phase = "search"
        self.update_control_buttons()

    def on_run(self):
        self.run()

    def toggle_pause(self):
        if self.phase in ("search", "path", "robot"):
            self.paused = not self.paused
            if self.paused:
                self.show_toast("Simulation Paused (Press Space to resume)", C.AMBER)
            else:
                self.show_toast("Simulation Resumed", C.CYAN)
        elif self.phase in ("idle", "done"):
            self.run()
        self.update_control_buttons()

    def step_forward(self):
        """Advances a small batch of events while paused for careful study."""
        if self.phase == "idle":
            self.run()
            self.paused = True
            return
        if self.phase == "search":
            self.paused = True
            events = self.result.events if self.result else []
            count = 0
            while self.ev_ptr < len(events) and count < 6:
                cell, kind = events[self.ev_ptr]
                self.ev_ptr += 1
                self.active_cell = cell
                if kind == VISITED:
                    self.cell_state[cell] = (VISITED, self.now, self.vis_count)
                    self.vis_count += 1
                else:
                    self.cell_state[cell] = (FRONTIER, self.now, 0)
                count += 1
            if self.ev_ptr >= len(events):
                if self.result.found:
                    self.phase = "path"
                    self.path_t = 0.0
                else:
                    self.phase = "done"
                    self.show_toast("No path found - goal unreachable", C.PINK)
            self.update_control_buttons()

    def refresh(self):
        """Called whenever the map or settings change."""
        if self.phase == "done":
            self.run(instant=True)            # live dynamic re-planning
        elif self.phase != "idle":
            self.clear_path()

    def compare_all(self):
        for algo in ALGORITHMS:
            self.results[algo] = search(algo, self.start, self.goal, self.walls, self.mud, self.diag)
        self.show_toast("Benchmark completed for all 5 algorithms", C.CYAN)

    def make_maze(self):
        self.walls, self.start, self.goal = make_maze()
        self.mud.clear()
        self.born = {c: self.now + (c[0] + c[1]) * 0.012 for c in self.walls}
        self.clear_path()
        self.results.clear()
        self.show_toast("Procedural maze generated", C.VIOLET)

    def scatter(self, announce=True):
        self.walls = scatter_walls(self.start, self.goal, 0.22)
        self.mud.clear()
        self.born = {c: self.now + random.random() * 0.5 for c in self.walls}
        self.clear_path()
        self.results.clear()
        if announce:
            self.show_toast("Random obstacle terrain placed", C.VIOLET)

    def reset_all(self):
        self.walls.clear()
        self.mud.clear()
        self.born.clear()
        self.start = (3, C.ROWS // 2)
        self.goal = (C.COLS - 4, C.ROWS // 2)
        self.clear_path()
        self.results.clear()
        self.show_toast("Map cleared to open grid", C.MUTED)

    def show_toast(self, text, color=C.CYAN):
        self.toast = (text, color, self.now)

    # ------------------------------------------------------------ editing
    def cell_at(self, pos):
        x, y = pos[0] // C.CELL, pos[1] // C.CELL
        if 0 <= x < C.COLS and 0 <= y < C.ROWS and pos[0] >= 0 and pos[1] >= 0:
            return (x, y)
        return None

    def paint(self, cell, mode):
        if cell in (self.start, self.goal):
            return False
        if mode == "wall" and cell not in self.walls:
            self.walls.add(cell)
            self.mud.discard(cell)
            self.born[cell] = self.now
            return True
        if mode == "mud" and cell not in self.mud:
            self.mud.add(cell)
            self.walls.discard(cell)
            self.born[cell] = self.now
            return True
        if mode == "erase" and (cell in self.walls or cell in self.mud):
            self.walls.discard(cell)
            self.mud.discard(cell)
            return True
        return False

    def move_marker(self, which, cell):
        other = self.goal if which == "start" else self.start
        current = self.start if which == "start" else self.goal
        if cell == current or cell == other or cell in self.walls:
            return False
        if which == "start":
            self.start = cell
        else:
            self.goal = cell
        return True

    # ------------------------------------------------------------ input
    def on_key(self, key):
        if key == pygame.K_SPACE:
            if self.phase in ("search", "path", "robot"):
                self.toggle_pause()
            else:
                self.run()
        elif key == pygame.K_p:
            self.toggle_pause()
        elif key == pygame.K_s:
            self.step_forward()
        elif key == pygame.K_c:
            self.clear_path_ui()
        elif key == pygame.K_m:
            self.make_maze()
        elif key == pygame.K_r:
            self.scatter()
        elif key == pygame.K_x:
            self.reset_all()
        elif key == pygame.K_k:
            self.compare_all()
        elif key == pygame.K_d:
            for w in self.widgets:
                if isinstance(w, Toggle):
                    w.value = not w.value
                    w.on_change(w.value)
        elif key == pygame.K_t:
            self.set_tool(TOOLS[(TOOLS.index(self.tool) + 1) % len(TOOLS)])
        elif key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5):
            self.set_algo(list(ALGORITHMS)[key - pygame.K_1])
        elif key == pygame.K_UP:
            self.bump_speed(+5)
        elif key == pygame.K_DOWN:
            self.bump_speed(-5)

    def bump_speed(self, delta):
        self.speed = int(clamp(self.speed + delta, 1, 100))
        for w in self.widgets:
            if isinstance(w, Slider):
                w.value = self.speed

    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
                continue
            if e.type == pygame.KEYDOWN:
                self.on_key(e.key)
                continue

            consumed = False
            for w in self.widgets:
                consumed = w.handle(e) or consumed

            if e.type == pygame.MOUSEBUTTONDOWN and not consumed and e.pos[0] < C.GRID_W:
                cell = self.cell_at(e.pos)
                if cell is None:
                    continue
                if e.button == 1 and cell == self.start:
                    self.drag = "start"
                elif e.button == 1 and cell == self.goal:
                    self.drag = "goal"
                elif e.button in (1, 3):
                    self.drag = "paint"
                    self.paint_mode = self.tool if e.button == 1 else "erase"
                    self.last_cell = cell
                    if self.paint(cell, self.paint_mode):
                        self.refresh()
            elif e.type == pygame.MOUSEBUTTONUP:
                self.drag = None
                self.last_cell = None

    def apply_drag(self):
        cell = self.cell_at(pygame.mouse.get_pos())
        if cell is None:
            return
        if self.drag == "paint":
            changed = False
            for c in line_cells(self.last_cell or cell, cell):
                changed = self.paint(c, self.paint_mode) or changed
            self.last_cell = cell
            if changed:
                self.refresh()
        elif self.drag in ("start", "goal"):
            if self.move_marker(self.drag, cell):
                self.refresh()

    # ------------------------------------------------------------ update & pacing
    def rate(self):
        """Pacing curve: slow and observable at low speeds, swift at high speeds."""
        return 4.0 + 0.16 * (self.speed ** 2.03)

    def robot_cps(self):
        return 2.4 + self.speed * 0.08

    def update(self, dt):
        self.now += dt
        mouse = pygame.mouse.get_pos()
        for w in self.widgets:
            w.update(mouse, dt)

        if self.drag:
            self.apply_drag()

        # when paused, keep particle/turning animations active but halt search/robot step progression
        if self.paused:
            self.update_particles(dt)
            return

        if self.phase == "search":
            self.ev_acc += dt * self.rate()
            n = int(self.ev_acc)
            self.ev_acc -= n
            events = self.result.events
            for _ in range(n):
                if self.ev_ptr >= len(events):
                    break
                cell, kind = events[self.ev_ptr]
                self.ev_ptr += 1
                self.active_cell = cell
                if kind == VISITED:
                    self.cell_state[cell] = (VISITED, self.now, self.vis_count)
                    self.vis_count += 1
                else:
                    self.cell_state[cell] = (FRONTIER, self.now, 0)
            if self.ev_ptr >= len(events):
                self.active_cell = None
                if self.result.found:
                    self.phase = "path"
                    self.path_t = 0.0
                    self.show_toast(f"Route discovered! {self.result.steps} steps, "
                                    f"cost {self.result.cost:.1f}", C.GREEN)
                else:
                    self.phase = "done"
                    self.show_toast("No path possible - the goal is blocked", C.PINK)

        elif self.phase == "path":
            # smooth, pleasant path trace speed
            self.path_t += dt * (14.0 + self.speed * 0.55)
            if self.path_t >= len(self.path) - 1:
                self.path_t = len(self.path) - 1
                self.phase = "robot"
                self.robot_t = 0.0

        elif self.phase == "robot":
            self.robot_t += dt * self.robot_cps()
            self.spawn_trail()
            if self.robot_t >= len(self.path) - 1:
                self.robot_t = len(self.path) - 1
                self.phase = "done"
                self.burst(cell_center(self.goal))
                self.show_toast("Destination Reached!", C.GREEN)

        # robot heading (smooth turning towards trajectory vector)
        diff = (self.target_angle() - self.angle + math.pi) % (2 * math.pi) - math.pi
        self.angle += diff * min(1.0, dt * 12)

        self.update_particles(dt)

    def target_angle(self):
        if self.phase in ("robot", "done") and len(self.path) > 1:
            i = min(int(self.robot_t), len(self.path) - 2)
            a, b = self.path[i], self.path[i + 1]
            return math.atan2(b[1] - a[1], b[0] - a[0])
        return math.atan2(self.goal[1] - self.start[1], self.goal[0] - self.start[0])

    def robot_pos(self):
        if self.phase in ("robot", "done") and len(self.path) > 1:
            pts = [cell_center(c) for c in self.path]
            return partial_polyline(pts, self.robot_t)[-1]
        return cell_center(self.start)

    # ------------------------------------------------------------ particles
    def spawn_trail(self):
        x, y = self.robot_pos()
        bx, by = x - math.cos(self.angle) * 10, y - math.sin(self.angle) * 10
        a = random.uniform(0, math.tau)
        sp = random.uniform(5, 25)
        self.particles.append([bx, by, math.cos(a) * sp, math.sin(a) * sp,
                               0.55, 0.55, C.CYAN, random.uniform(1.5, 3.2)])

    def burst(self, pos):
        colors = (C.PINK, C.AMBER, C.CYAN, C.GREEN, C.VIOLET)
        for _ in range(46):
            a = random.uniform(0, math.tau)
            sp = random.uniform(40, 190)
            life = random.uniform(0.6, 1.2)
            self.particles.append([pos[0], pos[1], math.cos(a) * sp, math.sin(a) * sp,
                                   life, life, random.choice(colors), random.uniform(2, 4.2)])

    def update_particles(self, dt):
        alive = []
        for p in self.particles:
            p[4] -= dt
            if p[4] <= 0:
                continue
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[2] *= 0.96
            p[3] *= 0.96
            alive.append(p)
        self.particles = alive

    # ------------------------------------------------------------ drawing
    def blit_pop(self, surf, cell, age):
        x, y = cell
        if age >= 1:
            self.screen.blit(surf, (x * C.CELL, y * C.CELL))
            return
        s = max(0.08, ease_out_back(age))
        size = max(2, int(C.CELL * s))
        img = pygame.transform.smoothscale(surf, (size, size))
        self.screen.blit(img, img.get_rect(center=cell_center(cell)))

    def draw(self):
        scr = self.screen
        now = self.now
        scr.blit(self.bg, (0, 0))

        # hover cursor highlight
        if not self.drag:
            mc = self.cell_at(pygame.mouse.get_pos())
            if mc and mc not in (self.start, self.goal):
                scr.blit(self.hover_surf, (mc[0] * C.CELL, mc[1] * C.CELL))

        # terrain: mud
        for c in self.mud:
            age = (now - self.born.get(c, -9)) / POP_TIME
            if age >= 0:
                self.blit_pop(self.mud_surf, c, age)

        # search exploration wavefront (frontier & explored)
        total = max(1, self.total_visited - 1)
        for c, (kind, tb, order) in self.cell_state.items():
            surf = (self.front_surf if kind == FRONTIER
                    else self.vis_surfs[min(31, int(31 * order / total))])
            self.blit_pop(surf, c, (now - tb) / POP_TIME)

        # active radar scanning focus on the current expanding node
        if self.phase == "search" and self.active_cell:
            ax, ay = cell_center(self.active_cell)
            pulse_r = int(10 + 6 * (math.sin(now * 16) * 0.5 + 0.5))
            draw_glow(scr, (ax, ay), 26, C.CYAN, 0.70)
            pygame.draw.circle(scr, (255, 255, 255), (ax, ay), pulse_r, 2)

        # obstacles / walls
        for c in self.walls:
            age = (now - self.born.get(c, -9)) / POP_TIME
            if age >= 0:
                self.blit_pop(self.wall_surf, c, age)

        # path, markers, robot, overlays
        self.draw_effects()
        self.draw_markers()
        self.draw_robot()
        self.draw_hud()
        self.draw_legend()
        self.draw_toast()
        self.draw_sidebar()

    def draw_effects(self):
        has_path = self.path and self.phase in ("path", "robot", "done")
        if not has_path and not self.particles:
            return
        fx = self.fx
        fx.fill((0, 0, 0, 0))
        pts = [cell_center(c) for c in self.path] if has_path and len(self.path) > 1 else []

        if pts:
            shown = partial_polyline(pts, self.path_t)
            if len(shown) > 1:
                # wide golden navigation glow
                pygame.draw.lines(fx, (*C.YELLOW, 45), False, shown, 16)
                pygame.draw.lines(fx, (255, 215, 45, 230), False, shown, 4)

                # directional chevron flow arrows along path segments
                for i in range(len(shown) - 1):
                    p1, p2 = shown[i], shown[i + 1]
                    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                    dist = math.hypot(dx, dy)
                    if dist > 8:
                        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
                        ang = math.atan2(dy, dx)
                        sz = 5
                        left = (mx - sz * math.cos(ang - 0.55), my - sz * math.sin(ang - 0.55))
                        right = (mx - sz * math.cos(ang + 0.55), my - sz * math.sin(ang + 0.55))
                        tip = (mx + sz * math.cos(ang), my + sz * math.sin(ang))
                        pygame.draw.polygon(fx, (255, 255, 255, 220), [left, tip, right])

                # vertex waypoints
                for p in pts:
                    if p[0] <= shown[-1][0] + 1 and p[1] <= shown[-1][1] + 1:
                        pygame.draw.circle(fx, (255, 240, 140, 240), (int(p[0]), int(p[1])), 3)

            # robot driven trail
            if self.phase in ("robot", "done"):
                trail = partial_polyline(pts, self.robot_t)
                if len(trail) > 1:
                    pygame.draw.lines(fx, (*C.CYAN, 55), False, trail, 12)
                    pygame.draw.lines(fx, (255, 255, 255, 240), False, trail, 4)

            # animated traveling pulse light packet
            if len(pts) > 1:
                cycle = (self.now * 6.5) % (len(pts) - 1)
                pkt = partial_polyline(pts, cycle)[-1]
                draw_glow(self.screen, pkt, 18, (255, 240, 100), 0.75)
                pygame.draw.circle(self.screen, (255, 255, 255), (int(pkt[0]), int(pkt[1])), 4)

        for x, y, _, _, life, maxlife, color, size in self.particles:
            alpha = int(255 * clamp(life / maxlife, 0, 1))
            pygame.draw.circle(fx, (*color, alpha), (int(x), int(y)), max(1, int(size)))
        self.screen.blit(fx, (0, 0))

    def draw_markers(self):
        scr, now = self.screen, self.now
        pulse = 0.5 + 0.5 * math.sin(now * 4.5)

        # Start Marker (Green beacon + clear "START" badge)
        sx, sy = cell_center(self.start)
        draw_glow(scr, (sx, sy), 30, C.GREEN, 0.45 + 0.25 * pulse)
        pygame.draw.circle(scr, C.GREEN, (sx, sy), 13, 2)
        pygame.draw.circle(scr, (255, 255, 255), (sx, sy), 4)

        st_label = self.fonts.render("START", 10, (255, 255, 255), bold=True)
        bw, bh = st_label.get_width() + 12, 17
        s_pill = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(s_pill, (14, 46, 32, 235), (0, 0, bw, bh), border_radius=8)
        pygame.draw.rect(s_pill, (*C.GREEN, 240), (0, 0, bw, bh), 1, border_radius=8)
        s_pill.blit(st_label, (6, 2))
        scr.blit(s_pill, s_pill.get_rect(midbottom=(sx, sy - 15)))

        # Goal Marker (Pink target + double ring + clear "GOAL" badge)
        gx, gy = cell_center(self.goal)
        draw_glow(scr, (gx, gy), 38, C.PINK, 0.45 + 0.35 * pulse)
        pygame.draw.circle(scr, C.PINK, (gx, gy), int(15 + 4 * pulse), 1)
        pygame.draw.circle(scr, C.PINK, (gx, gy), 11, 2)
        pygame.draw.circle(scr, (255, 255, 255), (gx, gy), 4)

        gl_label = self.fonts.render("GOAL", 10, (255, 255, 255), bold=True)
        gw, gh = gl_label.get_width() + 12, 17
        g_pill = pygame.Surface((gw, gh), pygame.SRCALPHA)
        pygame.draw.rect(g_pill, (52, 16, 28, 235), (0, 0, gw, gh), border_radius=8)
        pygame.draw.rect(g_pill, (*C.PINK, 240), (0, 0, gw, gh), 1, border_radius=8)
        g_pill.blit(gl_label, (6, 2))
        scr.blit(g_pill, g_pill.get_rect(midbottom=(gx, gy - 16)))

    def draw_robot(self):
        x, y = self.robot_pos()
        # forward headlights projection cone
        cone_surf = pygame.Surface((C.GRID_W, C.GRID_H), pygame.SRCALPHA)
        ang = self.angle
        p0 = (x + math.cos(ang) * 12, y + math.sin(ang) * 12)
        p1 = (x + math.cos(ang - 0.40) * 60, y + math.sin(ang - 0.40) * 60)
        p2 = (x + math.cos(ang + 0.40) * 60, y + math.sin(ang + 0.40) * 60)
        pygame.draw.polygon(cone_surf, (150, 240, 255, 34), [p0, p1, p2])
        self.screen.blit(cone_surf, (0, 0))

        draw_glow(self.screen, (x, y), 32, C.CYAN, 0.50)
        img = pygame.transform.rotate(self.robot_surf, -math.degrees(self.angle))
        self.screen.blit(img, img.get_rect(center=(int(x), int(y))))

        # floating robot status tag
        if self.phase in ("robot", "done"):
            tag = self.fonts.render("ROBOT [NAV]", 10, C.CYAN, bold=True)
            tw, th = tag.get_width() + 10, 16
            pill = pygame.Surface((tw, th), pygame.SRCALPHA)
            pygame.draw.rect(pill, (10, 16, 32, 220), (0, 0, tw, th), border_radius=8)
            pygame.draw.rect(pill, (*C.CYAN, 180), (0, 0, tw, th), 1, border_radius=8)
            pill.blit(tag, (5, 1))
            self.screen.blit(pill, pill.get_rect(midbottom=(int(x), int(y) - 22)))

    # ------------------------------------------------------------ stage HUD & legend
    def draw_hud(self):
        """Top glassmorphic HUD explaining exactly what the simulation is doing."""
        scr, f = self.screen, self.fonts
        hw, hh = 640, 64
        hx = (C.GRID_W - hw) // 2
        hy = 12

        hud = pygame.Surface((hw, hh), pygame.SRCALPHA)
        pygame.draw.rect(hud, (10, 15, 32, 235), (0, 0, hw, hh), border_radius=13)
        pygame.draw.rect(hud, (42, 60, 110, 210), (0, 0, hw, hh), 1, border_radius=13)

        # determine stage status, badge text, colors and descriptive message
        progress = 0.0
        bar_color = C.CYAN

        if self.phase == "search":
            stage_badge = "STAGE 1/3: EXPLORING"
            badge_col = C.AMBER
            total_ev = len(self.result.events) if self.result else 1
            progress = clamp(self.ev_ptr / max(1, total_ev), 0.0, 1.0)
            bar_color = C.AMBER
            pct = int(progress * 100)
            main_text = f"{ALGORITHMS[self.algo]} evaluating open frontier nodes towards GOAL ({pct}%)"
            sub_text = f"Nodes in Queue: {len([c for c, s in self.cell_state.items() if s[0] == FRONTIER])}  |  Evaluated: {self.vis_count}"

        elif self.phase == "path":
            stage_badge = "STAGE 2/3: ROUTE FOUND"
            badge_col = C.YELLOW
            total_steps = len(self.path) - 1 if self.path else 1
            progress = clamp(self.path_t / max(1, total_steps), 0.0, 1.0)
            bar_color = C.YELLOW
            main_text = f"Optimal trajectory established ({self.result.steps} steps, total cost {self.result.cost:.1f})"
            sub_text = "Reconstructing shortest path backwards from Goal to Start..."

        elif self.phase == "robot":
            stage_badge = "STAGE 3/3: ROBOT EXECUTING"
            badge_col = C.CYAN
            total_steps = len(self.path) - 1 if self.path else 1
            progress = clamp(self.robot_t / max(1, total_steps), 0.0, 1.0)
            bar_color = C.CYAN
            cur_step = min(int(self.robot_t), total_steps)
            main_text = f"Autonomous rover following waypoint route (Step {cur_step} of {total_steps})"
            sub_text = "Rover driving along calculated low-cost trajectory..."

        elif self.phase == "done":
            if self.result and self.result.found:
                stage_badge = "MISSION ACCOMPLISHED"
                badge_col = C.GREEN
                progress = 1.0
                bar_color = C.GREEN
                main_text = f"Goal reached! Total Cost: {self.result.cost:.1f} | Explored: {self.result.visited} cells"
                sub_text = f"Algorithm compute time: {self.result.ms:.2f} ms  •  Drag dots or click 'Maze' to re-test"
            else:
                stage_badge = "NO PATH POSSIBLE"
                badge_col = C.PINK
                progress = 1.0
                bar_color = C.PINK
                main_text = "Goal is completely trapped behind impassable obstacles!"
                sub_text = "Erase some wall blocks or click 'Maze' to reconnect Start and Goal."

        else:  # idle
            stage_badge = "READY TO SIMULATE"
            badge_col = C.PRIMARY_B
            progress = 0.0
            det = ALGO_DETAILS.get(self.algo, {})
            main_text = f"Selected Algorithm: {ALGORITHMS[self.algo]}  ({det.get('tagline', 'Path Planning')})"
            sub_text = "Click 'Run Simulation' or press Space to observe path search in action."

        # draw stage badge pill
        f_badge = self.fonts.render(stage_badge, 11, badge_col, bold=True)
        bw, bh = f_badge.get_width() + 16, 22
        badge_pill = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(badge_pill, (*badge_col, 36), (0, 0, bw, bh), border_radius=6)
        pygame.draw.rect(badge_pill, (*badge_col, 200), (0, 0, bw, bh), 1, border_radius=6)
        badge_pill.blit(f_badge, (8, 3))
        hud.blit(badge_pill, (14, 10))

        # pause indicator badge
        if self.paused and self.phase in ("search", "path", "robot"):
            f_p = self.fonts.render("[ PAUSED - Press Space / Resume ]", 11, C.AMBER, bold=True)
            hud.blit(f_p, (14 + bw + 10, 14))

        # text descriptions
        f.draw(hud, main_text, 13, C.TEXT, (14, 38), bold=True)
        f.draw(hud, sub_text, 11, C.MUTED, (14 + bw + 12 if not (self.paused and self.phase in ("search", "path", "robot")) else 14, 14))

        # sleek bottom progress bar
        bar_w = hw - 28
        bar_x, bar_y = 14, hh - 6
        pygame.draw.rect(hud, (22, 32, 60), (bar_x, bar_y, bar_w, 3), border_radius=2)
        if progress > 0:
            fill_w = max(4, int(bar_w * progress))
            pygame.draw.rect(hud, bar_color, (bar_x, bar_y, fill_w, 3), border_radius=2)

        scr.blit(hud, (hx, hy))

    def draw_legend(self):
        """Permanent bottom legend demystifying every visual element on the grid."""
        scr, f = self.screen, self.fonts
        lw, lh = C.GRID_W - 28, 26
        lx = 14
        ly = C.GRID_H - 32

        leg = pygame.Surface((lw, lh), pygame.SRCALPHA)
        pygame.draw.rect(leg, (10, 15, 30, 220), (0, 0, lw, lh), border_radius=8)
        pygame.draw.rect(leg, (35, 48, 85, 180), (0, 0, lw, lh), 1, border_radius=8)

        items = [
            ("Start", C.GREEN, "circle"),
            ("Goal", C.PINK, "target"),
            ("Frontier (Queue)", C.AMBER, "rect"),
            ("Explored (Closed)", C.CYAN_DEEP, "rect"),
            ("Planned Route", C.YELLOW, "line"),
            ("Mud (Cost 5x)", C.MUD, "rect"),
            ("Wall (Blocked)", C.WALL_TOP, "rect"),
        ]

        step = lw / len(items)
        for i, (name, col, kind) in enumerate(items):
            cx = int(i * step + 16)
            cy = lh // 2
            if kind == "circle":
                pygame.draw.circle(leg, col, (cx, cy), 5)
            elif kind == "target":
                pygame.draw.circle(leg, col, (cx, cy), 6, 1)
                pygame.draw.circle(leg, col, (cx, cy), 3)
            elif kind == "line":
                pygame.draw.line(leg, col, (cx - 5, cy), (cx + 5, cy), 3)
            else:
                pygame.draw.rect(leg, col, (cx - 5, cy - 5, 10, 10), border_radius=2)
            f.draw(leg, name, 11, C.MUTED, (cx + 10, cy), anchor="midleft")

        scr.blit(leg, (lx, ly))

    def draw_toast(self):
        if not self.toast:
            return
        text, color, t0 = self.toast
        age = self.now - t0
        life = 3.2
        if age > life:
            self.toast = None
            return
        alpha = 1.0 if age < life - 0.5 else (life - age) / 0.5
        alpha *= clamp(age / 0.15, 0, 1)
        label = self.fonts.render(text, 13, C.TEXT, True)
        w, h = label.get_width() + 38, 32
        pill = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(pill, (10, 15, 32, 235), (0, 0, w, h), border_radius=16)
        pygame.draw.rect(pill, (*color, 255), (0, 0, w, h), 1, border_radius=16)
        pygame.draw.circle(pill, color, (15, h // 2), 4)
        pill.blit(label, (26, h // 2 - label.get_height() // 2))
        pill.set_alpha(int(255 * alpha))
        self.screen.blit(pill, pill.get_rect(midtop=(C.GRID_W // 2, 82 + int((1 - alpha) * -8))))

    # ------------------------------------------------------------ sidebar
    def draw_sidebar(self):
        scr, f = self.screen, self.fonts
        X, W = self.X, self.W
        pygame.draw.rect(scr, C.SIDEBAR_BG, (C.GRID_W, 0, C.SIDEBAR_W, C.HEIGHT))
        pygame.draw.line(scr, C.BORDER, (C.GRID_W, 0), (C.GRID_W, C.HEIGHT), 1)

        # header
        scr.blit(self.logo, (X, 14))
        f.draw(scr, "PathPilot", 24, C.TEXT, (X + 50, 10), bold=True)
        f.draw(scr, "Robot Path Planning Simulator", 12, C.MUTED, (X + 51, 38))

        def label(text, y):
            f.draw(scr, text, 11, C.DIM, (X, y), bold=True)

        label("CHOOSE ALGORITHM", 66)

        # algorithm explanation guide card
        det = ALGO_DETAILS.get(self.algo, ALGO_DETAILS["astar"])
        card_r = pygame.Rect(X, 158, W, 80)
        pygame.draw.rect(scr, (14, 20, 38), card_r, border_radius=8)
        pygame.draw.rect(scr, (35, 48, 86), card_r, 1, border_radius=8)
        pygame.draw.rect(scr, C.CYAN, (card_r.x, card_r.y + 6, 3, card_r.h - 12), border_radius=2)
        f.draw(scr, f"{det['title']}  •  {det['tagline']}", 12, C.CYAN, (card_r.x + 12, card_r.y + 6), bold=True)
        f.draw(scr, det['formula'], 10, C.AMBER, (card_r.x + 12, card_r.y + 24), bold=True)
        f.draw(scr, det['desc_line1'], 11, C.TEXT, (card_r.x + 12, card_r.y + 42))
        f.draw(scr, det['desc_line2'], 11, C.MUTED, (card_r.x + 12, card_r.y + 58))

        label("DRAWING BRUSH", 314)

        # live stats cards
        res = self.result
        if self.phase == "search":
            vals = [str(self.vis_count), "-", "-", "-"]
        elif res:
            pct_explored = f"{res.visited * 100 // (C.COLS * C.ROWS)}%"
            vals = [f"{res.visited} ({pct_explored})",
                    f"{res.steps} steps" if res.found else "-",
                    f"{res.cost:.1f}" if res.found else "-",
                    f"{res.ms:.2f} ms"]
        else:
            vals = ["-", "-", "-", "-"]

        labels = ("Cells Explored", "Path Steps", "Path Cost", "Compute Time")
        colors = (C.CYAN, C.GREEN, C.AMBER, C.PRIMARY_B)
        label("SIMULATION METRICS", 442)
        cw = (W - 8) // 2
        for i in range(4):
            r = pygame.Rect(X + (i % 2) * (cw + 8), 458 + (i // 2) * 52, cw, 46)
            pygame.draw.rect(scr, C.PANEL, r, border_radius=8)
            pygame.draw.rect(scr, C.BORDER, r, 1, border_radius=8)
            pygame.draw.rect(scr, colors[i], (r.x, r.y + 10, 3, r.h - 20), border_radius=2)
            f.draw(scr, labels[i], 10, C.MUTED, (r.x + 12, r.y + 6))
            f.draw(scr, vals[i], 17, C.TEXT, (r.x + 12, r.y + 20), bold=True)

        # benchmark compare table
        label("ALGORITHM BENCHMARK", 552)
        table = pygame.Rect(X, 572, W, 126)
        pygame.draw.rect(scr, C.PANEL, table, border_radius=8)
        pygame.draw.rect(scr, C.BORDER, table, 1, border_radius=8)
        cols = (X + 12, X + 168, X + 232, X + W - 12)
        for text, cx, anchor in (("Algorithm", cols[0], "topleft"), ("Explored", cols[1], "topright"),
                                 ("Cost", cols[2], "topright"), ("ms", cols[3], "topright")):
            f.draw(scr, text, 11, C.DIM, (cx, 578), bold=True, anchor=anchor)

        found = [r for r in self.results.values() if r.found]
        best_cost = min((r.cost for r in found), default=None)
        best_explored = min((r.visited for r in found), default=None)

        for i, (key, name) in enumerate(ALGORITHMS.items()):
            y = 596 + i * 19
            r_res = self.results.get(key)
            current = key == self.algo
            if current:
                pygame.draw.rect(scr, C.PANEL_HI, (X + 4, y - 2, W - 8, 19), border_radius=6)
            f.draw(scr, name, 12, C.TEXT if current else C.MUTED, (cols[0], y), bold=current)
            if r_res is None:
                for cx in cols[1:]:
                    f.draw(scr, "-", 12, C.DIM, (cx, y), anchor="topright")
                continue
            ex_col = C.CYAN if r_res.found and r_res.visited == best_explored else C.TEXT
            f.draw(scr, str(r_res.visited), 12, ex_col, (cols[1], y), anchor="topright")
            if r_res.found:
                cost_col = C.GREEN if abs(r_res.cost - best_cost) < 1e-6 else C.TEXT
                f.draw(scr, f"{r_res.cost:.1f}", 12, cost_col, (cols[2], y), anchor="topright")
            else:
                f.draw(scr, "none", 12, C.PINK, (cols[2], y), anchor="topright")
            f.draw(scr, f"{r_res.ms:.1f}", 12, C.MUTED, (cols[3], y), anchor="topright")

        # keyboard shortcut quick tips
        f.draw(scr, "Shortcuts: Space run/pause  •  S step  •  M maze  •  C clear",
               10, C.DIM, (X, 720))

        for w in self.widgets:
            w.draw(scr, f)

    # ------------------------------------------------------------ main loop
    async def run_loop(self):
        while self.running:
            dt = min(self.clock.tick(C.FPS) / 1000.0, 0.05)
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()
            await asyncio.sleep(0)       # lets the browser (pygbag) breathe
        pygame.quit()
