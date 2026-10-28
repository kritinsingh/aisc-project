"""Path-planning algorithms and map generators (no pygame code in here)."""
from __future__ import annotations

import heapq
import math
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

from .config import COLS, ROWS, MUD_COST

SQ2 = math.sqrt(2)

# event kinds recorded while searching (used for the animation)
FRONTIER, VISITED = 1, 2

ALGORITHMS = {
    "astar": "A*",
    "dijkstra": "Dijkstra",
    "greedy": "Greedy",
    "bfs": "BFS",
    "dfs": "DFS",
}

ALGO_INFO = {
    "astar": "Optimal - a heuristic steers it toward the goal",
    "dijkstra": "Optimal - explores evenly in every direction",
    "greedy": "Very fast - but the path is often not the shortest",
    "bfs": "Fewest steps - but it ignores terrain cost",
    "dfs": "Dives deep - finds *a* path, rarely a short one",
}

ALGO_DETAILS = {
    "astar": {
        "title": "A* Search",
        "tagline": "Optimal & Heuristic-Guided",
        "formula": "Priority: f(n) = g(n) + h(n)",
        "desc_line1": "Combines actual cost from Start with estimated distance to Goal.",
        "desc_line2": "Guides search aggressively towards target; avoids useless branches.",
    },
    "dijkstra": {
        "title": "Dijkstra's Algorithm",
        "tagline": "Optimal & Uniform-Cost",
        "formula": "Priority: f(n) = g(n)",
        "desc_line1": "Expands outward in concentric waves strictly by lowest cost.",
        "desc_line2": "Guaranteed shortest path; navigates around mud and walls.",
    },
    "greedy": {
        "title": "Greedy Best-First",
        "tagline": "Fast & Goal-Obsessed",
        "formula": "Priority: f(n) = h(n)",
        "desc_line1": "Expands nodes closest to the goal. Extremely quick.",
        "desc_line2": "Ignores terrain cost and easily gets stuck inside dead ends.",
    },
    "bfs": {
        "title": "Breadth-First Search",
        "tagline": "Fewest Grid Hops (Unweighted)",
        "formula": "Queue: FIFO Frontier",
        "desc_line1": "Explores layer-by-layer equally in all directions.",
        "desc_line2": "Finds path with fewest grid steps, but treats mud as normal cost.",
    },
    "dfs": {
        "title": "Depth-First Search",
        "tagline": "Deep Exploration",
        "formula": "Stack: LIFO Frontier",
        "desc_line1": "Plunges as deep as possible down one path before backtracking.",
        "desc_line2": "Finds *a* path quickly in some mazes, but route is rarely short.",
    },
}


@dataclass
class Result:
    algo: str
    events: list                 # [(cell, FRONTIER|VISITED), ...] in order
    visited: int                 # number of cells expanded
    path: list                   # [(x, y), ...] from start to goal
    cost: Optional[float]
    ms: float

    @property
    def found(self) -> bool:
        return bool(self.path)

    @property
    def steps(self) -> Optional[int]:
        return len(self.path) - 1 if self.path else None


# ---------------------------------------------------------------- helpers
def neighbors(cell, walls, diag):
    """Yield (next_cell, distance) for every legal move from `cell`."""
    x, y = cell
    moves = [(1, 0, 1), (0, 1, 1), (-1, 0, 1), (0, -1, 1)]
    if diag:
        moves += [(1, 1, SQ2), (-1, 1, SQ2), (-1, -1, SQ2), (1, -1, SQ2)]
    for dx, dy, dist in moves:
        nx, ny = x + dx, y + dy
        if not (0 <= nx < COLS and 0 <= ny < ROWS) or (nx, ny) in walls:
            continue
        # a robot can't squeeze diagonally between two touching walls
        if dx and dy and ((x + dx, y) in walls or (x, y + dy) in walls):
            continue
        yield (nx, ny), dist


def heuristic(a, b, diag):
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    if diag:
        return (dx + dy) + (SQ2 - 2) * min(dx, dy)     # octile distance
    return dx + dy                                      # manhattan distance


def path_cost(path, mud):
    total = 0.0
    for a, b in zip(path, path[1:]):
        dist = SQ2 if (a[0] != b[0] and a[1] != b[1]) else 1.0
        total += dist * (MUD_COST if b in mud else 1)
    return total


# ---------------------------------------------------------------- search
def search(algo, start, goal, walls, mud, diag) -> Result:
    t0 = time.perf_counter()
    events = [(start, FRONTIER)]
    came = {start: None}
    visited = 0

    if algo == "bfs":
        queue = deque([start])
        while queue:
            cur = queue.popleft()
            events.append((cur, VISITED))
            visited += 1
            if cur == goal:
                break
            for nxt, _ in neighbors(cur, walls, diag):
                if nxt not in came:
                    came[nxt] = cur
                    queue.append(nxt)
                    events.append((nxt, FRONTIER))

    elif algo == "dfs":
        stack, closed, seen = [start], set(), {start}
        while stack:
            cur = stack.pop()
            if cur in closed:
                continue
            closed.add(cur)
            events.append((cur, VISITED))
            visited += 1
            if cur == goal:
                break
            for nxt, _ in reversed(list(neighbors(cur, walls, diag))):
                if nxt in closed:
                    continue
                came[nxt] = cur
                stack.append(nxt)
                if nxt not in seen:
                    seen.add(nxt)
                    events.append((nxt, FRONTIER))

    else:  # dijkstra, astar, greedy -> priority queue
        best = {start: 0.0}
        closed = set()
        heap = [(0.0, 0.0, 0, start)]
        counter = 0
        while heap:
            _, _, _, cur = heapq.heappop(heap)
            if cur in closed:
                continue
            closed.add(cur)
            events.append((cur, VISITED))
            visited += 1
            if cur == goal:
                break
            for nxt, dist in neighbors(cur, walls, diag):
                if nxt in closed:
                    continue
                new = best[cur] + dist * (MUD_COST if nxt in mud else 1)
                if nxt not in best or new < best[nxt]:
                    if nxt not in best:
                        events.append((nxt, FRONTIER))
                    best[nxt] = new
                    came[nxt] = cur
                    h = heuristic(nxt, goal, diag)
                    if algo == "astar":
                        priority = new + h
                    elif algo == "dijkstra":
                        priority = new
                    else:
                        priority = h
                    counter += 1
                    # tie-break on h so A* prefers cells closer to the goal
                    heapq.heappush(heap, (priority, h, counter, nxt))

    path = []
    if goal in came:
        cur = goal
        while cur is not None:
            path.append(cur)
            cur = came[cur]
        path.reverse()

    ms = (time.perf_counter() - t0) * 1000
    cost = path_cost(path, mud) if path else None
    return Result(algo, events, visited, path, cost, ms)


# ---------------------------------------------------------------- maps
def make_maze():
    """Recursive-backtracker maze with a few extra openings (so there are loops)."""
    gx = COLS - 2 if (COLS - 2) % 2 == 1 else COLS - 3
    gy = ROWS - 2 if (ROWS - 2) % 2 == 1 else ROWS - 3
    walls = {(x, y) for x in range(COLS) for y in range(ROWS)}
    stack = [(1, 1)]
    walls.discard((1, 1))
    while stack:
        x, y = stack[-1]
        options = [(dx, dy) for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
                   if 1 <= x + dx <= gx and 1 <= y + dy <= gy
                   and (x + dx, y + dy) in walls]
        if not options:
            stack.pop()
            continue
        dx, dy = random.choice(options)
        walls.discard((x + dx // 2, y + dy // 2))
        walls.discard((x + dx, y + dy))
        stack.append((x + dx, y + dy))
    for x in range(1, gx + 1):
        for y in range(1, gy + 1):
            if (x, y) in walls and random.random() < 0.07:
                walls.discard((x, y))
    return walls, (1, 1), (gx, gy)


def scatter_walls(start, goal, density=0.2):
    walls = {(x, y) for x in range(COLS) for y in range(ROWS)
             if random.random() < density}
    walls.discard(start)
    walls.discard(goal)
    return walls
