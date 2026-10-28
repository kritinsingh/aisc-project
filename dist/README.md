# PathPilot - Robot Path Planning Simulator

An interactive simulator that shows how a robot plans a route through a grid
with obstacles and rough terrain. Built with Python + Pygame.

## Features
- 5 algorithms: **A\***, **Dijkstra**, **Greedy Best-First**, **BFS**, **DFS**
- Animated search (open set = amber, closed set = cyan -> violet gradient)
- Animated robot that follows the final path
- Obstacles, **mud** terrain (costs 5x), diagonal moves on/off
- Maze generator and random obstacle generator
- Drag the start / goal - the path **re-plans live**
- Live stats (cells explored, steps, cost, compute time)
- "Run all" comparison table across all algorithms

## Run it
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Controls
| Key / mouse | Action |
|---|---|
| Left mouse | Draw with the selected brush (Wall / Mud / Erase) |
| Right mouse | Erase |
| Drag green / pink dot | Move start / goal |
| `Space` | Run the simulation |
| `1` - `5` | A*, Dijkstra, Greedy, BFS, DFS |
| `C` | Clear the path |
| `M` / `R` | Maze / random obstacles |
| `K` | Compare all algorithms |
| `D` | Toggle diagonal moves |
| `T` | Cycle brush |
| `Up` / `Down` | Speed |
| `X` | Reset everything |

## Project layout
```
main.py            entry point
sim/config.py      sizes and colour palette
sim/algorithms.py  A*, Dijkstra, Greedy, BFS, DFS + maze generator
sim/ui.py          buttons, toggle, slider, fonts, gradients
sim/app.py         the simulator (editing, animation, robot, sidebar)
```

## Deploy to the web (pygbag)
The game loop is already async, so it can run in a browser via WebAssembly.

```
pip install pygbag
pygbag .                 # test locally at http://localhost:8000
pygbag --build .         # creates build/web/
```
Then either:
- upload the zipped `build/web` folder to **itch.io** (kind of project: HTML), or
- push the contents of `build/web` to a GitHub repo and enable **GitHub Pages**.

## Deploy as a Windows app
```
pip install pyinstaller
pyinstaller --onefile --windowed --name PathPilot main.py
```
The `.exe` appears in the `dist` folder.
