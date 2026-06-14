# Quadcopter Multi-Agent Simulation — Complete A-to-Z Documentation

**Package:** `robot_proximity` | **ROS 2 Distribution:** Humble | **Language:** Python 3.10  
**Maintainer:** jatin | **License:** Apache-2.0

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [ROS 2 Package Configuration](#3-ros-2-package-configuration)
4. [System Architecture and Node Communication](#4-system-architecture-and-node-communication)
5. [Component Deep Dive — Every File Explained](#5-component-deep-dive--every-file-explained)
   - 5.1 [graph_manager.py — Grid and BFS Engine](#51-graph_managerpy)
   - 5.2 [robot_node.py — Physics Agent and Flight Controller](#52-robot_nodepy)
   - 5.3 [graph_visualizer.py — Map Renderer and Obstacle Spawner](#53-graph_visualizerpy)
   - 5.4 [proximity_monitor.py — Inter-Drone Observer](#54-proximity_monitorpy)
   - 5.5 [interactive_runner.py — Simulation Orchestrator](#55-interactive_runnerpy)
   - 5.6 [diag_test.py — Path Validation Tool](#56-diag_testpy)
   - 5.7 [simulation.launch.py — Static Launch File](#57-simulationlaunchpy)
   - 5.8 [simulation.rviz — RViz Configuration](#58-simulationrviz)
6. [Algorithms in Detail](#6-algorithms-in-detail)
   - 6.1 [BFS Pathfinding](#61-bfs-pathfinding)
   - 6.2 [PD Controller and Virtual Rabbit Tracking](#62-pd-controller-and-virtual-rabbit-tracking)
   - 6.3 [Quadcopter Tilt Model](#63-quadcopter-tilt-model)
   - 6.4 [Yaw Spring-Damper](#64-yaw-spring-damper)
   - 6.5 [Cell-Based Deadlock Prevention](#65-cell-based-deadlock-prevention)
   - 6.6 [Distance-Priority Yielding](#66-distance-priority-yielding)
   - 6.7 [Dynamic Obstacle Spawning](#67-dynamic-obstacle-spawning)
7. [Flight State Machine](#7-flight-state-machine)
8. [ROS Topics, Services and Parameters](#8-ros-topics-services-and-parameters)
9. [Running the Project — All Modes](#9-running-the-project--all-modes)
10. [Build Instructions](#10-build-instructions)
11. [Grid Reference](#11-grid-reference)

---

## 1. Project Overview

The **Quadcopter Multi-Agent Simulation** is a fully decentralized, ROS 2-based multi-robot coordination system that simulates up to **10 autonomous quadcopters** flying simultaneously in a shared 3D airspace above a structured grid map. Every drone operates as its own independent ROS 2 node — there is no central controller. All coordination happens through the ROS 2 publish/subscribe mesh and service layer.

Key capabilities:

| Feature | Description |
|---|---|
| Realistic Physics | PD-controller pursuit of a virtual rabbit target produces smooth inertial motion |
| True Quadcopter Dynamics | Pitch and Roll are derived mathematically from the acceleration vector, not hardcoded |
| Rounded Cornering | Momentum retention causes sweeping arcs at 90-degree turns |
| BFS Pathfinding | Automatic rerouting around static and dynamically spawned obstacles |
| Cell Deadlock Prevention | Grid-cell reservation system prevents head-on collisions at intersections |
| Priority Yielding | Distance-based spatial yielding; lower ID drones have right-of-way |
| Dynamic Obstacles | User-defined interval controls how often the obstacle layout reshuffles |
| RViz Visualization | Full 3D render with spinning propellers, tilting body, altitude bobbing, labels |
| Multi-Mode Launch | AUTO mode (pre-stored paths) or MANUAL mode (user-defined waypoints) |

---

## 2. Repository Structure

```
turtle_to_quadcopter final with modifications/
|
|-- README_A_TO_Z.md                         <- This documentation
|
|-- src/
|   |-- robot_proximity/
|       |-- package.xml                      <- ROS 2 manifest (dependencies)
|       |-- setup.py                         <- Python package setup + entry points
|       |-- setup.cfg                        <- Build config (ament_python)
|       |-- resource/
|       |   |-- robot_proximity              <- ament resource index file
|       |-- launch/
|       |   |-- simulation.launch.py         <- Static 4-robot launch file
|       |-- config/
|       |   |-- simulation.rviz              <- RViz panel and topic configuration
|       |-- test/                            <- ament lint test stubs
|       |-- robot_proximity/                 <- Core Python package
|           |-- __init__.py
|           |-- graph_manager.py             <- 10x8 grid + BFS pathfinding
|           |-- robot_node.py                <- Physics engine + FSM + collision
|           |-- graph_visualizer.py          <- RViz grid renderer + obstacle spawner
|           |-- proximity_monitor.py         <- Distance logger + service trigger
|           |-- interactive_runner.py        <- Terminal UI + launch file generator
|           |-- diag_test.py                 <- Offline path validation script
|
|-- build/                                   <- colcon output (auto-generated)
|-- install/                                 <- install overlay (auto-generated)
|-- log/                                     <- build logs (auto-generated)
```

---

## 3. ROS 2 Package Configuration

### package.xml

Declares the package name `robot_proximity`, build type `ament_python`, and the following ROS 2 dependencies:

| Dependency | What It Provides |
|---|---|
| `rclpy` | Python ROS 2 client: Node, Publisher, Subscriber, Timer, Service APIs |
| `geometry_msgs` | `Pose` message type used for broadcasting drone 3D position + quaternion orientation |
| `visualization_msgs` | `Marker` and `MarkerArray` messages used to render all 3D objects in RViz |
| `std_msgs` | `String` message for the cell registry topic |
| `std_srvs` | `Trigger` service definition used for inter-drone communication RPC |

### setup.py

Registers four console-script entry points via `colcon`:

```python
'console_scripts': [
    'robot_node        = robot_proximity.robot_node:main',
    'proximity_monitor = robot_proximity.proximity_monitor:main',
    'graph_visualizer  = robot_proximity.graph_visualizer:main',
    'interactive_runner= robot_proximity.interactive_runner:main',
],
```

Each maps to a `main()` function, making them launchable with `ros2 run robot_proximity <name>`.

---

## 4. System Architecture and Node Communication

The system is **completely decentralized**. All coordination flows through the ROS 2 middleware layer:

```
                       /robot_cell_registry  (String)
     robot1 ─────────────────────────────────────────► all other robot_nodes
            ◄────────────────────────────────────────── all other robot_nodes

     robot1 ─── /robot1/pose (Pose) ──────────────────► proximity_monitor
                                                       ► all other robot_nodes

     robot1 ─── /robot1/markers (MarkerArray) ─────────► RViz

     graph_visualizer ─── /graph_markers (MarkerArray) ─► RViz
     graph_visualizer ─── /dynamic_obstacles (String) ──► all robot_nodes

     proximity_monitor ─── /robotN/communicate (Trigger service call) ─► robotN
```

Every `robot_node` instance independently subscribes to all other drones' pose and cell data and makes its own decisions. There is no master process coordinating movement.

---

## 5. Component Deep Dive — Every File Explained

---

### 5.1 `graph_manager.py`

**Role:** The mathematical and topological foundation of the entire project. Instantiated independently by `robot_node`, `graph_visualizer`, and `interactive_runner`.

#### Grid Construction

The grid is a **10-column x 8-row** matrix of named cells:
- Rows: A through H (A at top, H at bottom)
- Columns: 1 through 10 (left to right)
- Total cells: **80 nodes** spanning A1 through H10
- Cell spacing: **2.0 metres** between adjacent cell centres

```python
self.cell_size   = 2.0
self.num_cols    = 10
self.num_rows    = 8
self.row_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
```

Each cell name maps to Cartesian coordinates:
```
A1  -> (0.0,  0.0)     A10 -> (18.0,  0.0)
B1  -> (0.0,  2.0)     H10 -> (18.0, 14.0)
```

#### Static Obstacle Cells

Twelve cells are blocked by default, chosen carefully to keep the graph fully connected (rows A and H remain fully clear for perimeter traversal):

```
B4, B8, C2, C6, D5, D9, E3, E7, F2, F6, G4, G9
```

Obstacle cells are excluded from edge construction and rendered as tall red blocks in RViz.

#### Edge Construction

Edges connect horizontally and vertically adjacent non-obstacle cells only. No diagonal movement is permitted:

```python
# Horizontal edges
for row in self.rows:
    for i in range(len(row) - 1):
        n1, n2 = row[i], row[i+1]
        if n1 not in obstacles and n2 not in obstacles:
            self.edges.append((n1, n2))

# Vertical edges
for col_idx in range(num_cols):
    for row_idx in range(num_rows - 1):
        n1 = rows[row_idx][col_idx]
        n2 = rows[row_idx+1][col_idx]
        if n1 not in obstacles and n2 not in obstacles:
            self.edges.append((n1, n2))
```

An adjacency dict `self._adj` is rebuilt every time `update_obstacles()` is called, enabling O(1) neighbour lookups during BFS.

#### Key API Methods

| Method | Returns | Description |
|---|---|---|
| `get_coords(node)` | `(float, float)` | Cartesian XY coordinates of a node |
| `get_distance(p1, p2)` | `float` | Euclidean distance between two coordinate tuples |
| `interpolate(start, end, alpha)` | `(float, float)` | Linear interpolation between two nodes at fraction alpha in [0,1] |
| `is_obstacle(node)` | `bool` | True if the node is currently blocked |
| `is_edge(n1, n2)` | `bool` | True if a direct edge exists between two nodes |
| `find_path(start, end)` | `list` or `None` | BFS shortest path from start to end |
| `find_path_excluding(start, end, excluded)` | `list` or `None` | BFS avoiding a set of nodes (used for deadlock rerouting) |
| `resolve_path(waypoints)` | `list` | Expands a sparse waypoint list into a full edge-by-edge path using BFS between each pair |
| `update_obstacles(new_obs)` | `None` | Replaces obstacle set and completely rebuilds edges + adjacency |

---

### 5.2 `robot_node.py`

**Role:** The core agent. One instance runs per drone. It manages 3D physics, flight states, all collision avoidance logic, and produces all RViz markers for its drone.

#### ROS 2 Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `robot_id` | string | `robot1` | Unique drone identifier |
| `color` | string | `red` | Drone body and propeller colour |
| `path` | string | `A1,A2,A3` | Comma-separated waypoint list |
| `speed` | float | `0.4` | Virtual rabbit speed in m/s (default reduced for visibility) |
| `radius` | float | `2.0` | Communication range disc radius in metres |

#### State Variables

**Physical position:**
- `self.x, self.y` — True physical Cartesian position (metres). Controlled by PD controller.
- `self.vx, self.vy` — Velocity in X and Y. Accumulate from PD-computed acceleration.
- `self.rabbit_x, self.rabbit_y` — Position of the virtual rabbit target on the strict grid path.
- `self.z` — Altitude in metres. Controlled by the takeoff/landing FSM.

**Rotation state:**
- `self._current_yaw` — Current heading angle in radians. Tracks instantaneous velocity direction.
- `self.pitch, self.roll` — Computed from body-frame acceleration. Drive 3D tilt visual.
- `self.yaw_vel, self.pitch_vel, self.roll_vel` — Angular velocities for spring-damper smoothing.

**Flight dynamics constants:**
- `target_z = 1.2` — Cruising altitude in metres
- `v_z = 0.6` — Climb and descent rate in m/s
- `tilt_max = 0.15` — Max allowed tilt angle in radians (approximately 8.6 degrees)
- `prop_angle` — Continuously incremented propeller animation angle

**Collision avoidance state:**
- `_cells_of_others` — Dict mapping other robot IDs to their claimed cell lists
- `_poses_of_others` — Dict mapping other robot IDs to their latest Pose position
- `_waiting` — True when blocked by another drone's claimed cell
- `_is_yielding` — True when paused to give way to a higher-priority drone
- `_safety_distance = 2.5` — Reactive distance bubble radius in metres
- `_reroute_count` — Count of BFS reroutes triggered this session
- `_needs_reroute` — Flag set by dynamic obstacle callback to trigger next-tick reroute

#### Timer Architecture

```python
self.create_timer(0.02,  self._timer_cb)        # 50 Hz physics loop
self.create_timer(0.33,  self._refresh_timer_cb) # 3 Hz marker refresh
```

The 3 Hz refresh guarantees drones remain visible in RViz even when the main loop is idle (e.g. during waiting or landing states).

#### Quaternion Helpers

```python
def _quat_from_yaw(yaw):              # Heading-only rotation
def _quat_from_rpy(roll, pitch, yaw): # Full 3-axis rotation for tilt visual
```

These convert Euler angles to ROS 2 quaternions for setting `marker.pose.orientation`.

#### Marker Composition

`_force_publish_markers(x, y)` builds a `MarkerArray` with exactly **9 marker primitives** per drone, all sharing the drone's current roll/pitch/yaw orientation:

| ID | Marker Type | Description |
|---|---|---|
| 0 | `CUBE` | Central fuselage (0.5 x 0.5 x 0.16 m). Dimmed when waiting. |
| 1 | `CYLINDER` | Fore-aft arm (length 1.1 m). Dark grey. Tilts with body. |
| 2 | `CYLINDER` | Left-right lateral arm. Perpendicular to arm 1. |
| 11-14 | `CYLINDER` (x4) | Motor housings at the four arm tips. Dark grey. |
| 3-6 | `CYLINDER` (x4) | Propeller discs at arm tips. Coloured. Spin via prop_angle. Counter-rotating pairs. |
| 7 | `CYLINDER` | Flat communication-range disc on the ground. Translucent, coloured. |
| 8 | `TEXT_VIEW_FACING` | Name label above drone. Shows state: CRUISE / TAKEOFF / LANDING / YIELD / WAITING |

The prop_angle increments at different rates per flight state:
- Taking off: +15 rad/s
- Flying: +20 rad/s  
- Landing: +10 rad/s

---

### 5.3 `graph_visualizer.py`

**Role:** Dual-purpose node that renders the entire 10x8 grid environment in RViz and periodically randomises obstacle placement.

#### Publishers

| Topic | Type | Rate | Description |
|---|---|---|---|
| `/graph_markers` | `MarkerArray` | 1 Hz | Complete visual grid with cells, lines, labels |
| `/dynamic_obstacles` | `String` | user-defined | Comma-separated list of new obstacle node names |

#### Subscriber

| Topic | Type | Callback | Description |
|---|---|---|---|
| `/robot_cell_registry` | `String` | `cell_registry_cb` | Tracks which cells are occupied so obstacles never spawn on robots |

#### Parameter

| Parameter | Type | Default | Description |
|---|---|---|---|
| `spawn_interval` | `float` | `8.0` | Seconds between obstacle reshuffles. Enter 0 to disable entirely. |

The timer is only created if `spawn_interval > 0`:
```python
if spawn_interval > 0:
    self.create_timer(spawn_interval, self.spawn_obstacles)
```

#### publish_graph() — Three-Layer Rendering

The map is assembled as a single `MarkerArray` sent every second:

**Layer 1 — Ground plane:**
A large dark `CUBE` (40 x 40 x 0.02 m) positioned at Z = -0.15 behind all other markers. Colour: dark charcoal (R=0.12, G=0.14, B=0.18).

**Layer 2 — Grid lines:**
A `LINE_LIST` marker drawing all horizontal and vertical cell borders at Z = -0.05. Line width 0.06 m. Muted purple-grey colour.

**Layer 3 — Per-cell markers (x80 cells, 2 markers each = 160 markers):**

Walkable cell:
- Flat `CUBE` (1.92 x 1.92 x 0.04 m) at Z = -0.10. Dark blue-grey fill.
- `TEXT_VIEW_FACING` label at Z = 0.3. Light blue-white text.

Obstacle cell:
- Tall `CUBE` (1.92 x 1.92 x 0.80 m) at Z = 0.40. Solid dark red (alpha 0.95).
- `TEXT_VIEW_FACING` label at Z = 1.0. Bright red text.

#### spawn_obstacles()

```python
def spawn_obstacles(self):
    # Collect all cells claimed by any robot
    occupied = set()
    for cells in self.robot_cells.values():
        occupied.update(cells)

    # Sample 15 random cells not occupied by any robot
    possible = [n for n in self.gm.nodes.keys() if n not in occupied]
    new_obs  = random.sample(possible, min(15, len(possible)))

    # Broadcast to all robot_nodes via /dynamic_obstacles
    msg = String()
    msg.data = ",".join(new_obs)
    self.obs_pub.publish(msg)

    # Update local GraphManager for visual refresh
    self.gm.update_obstacles(new_obs)
    self.publish_graph()
```

When the visualizer fires this, all robots receive the update within milliseconds and immediately flag `_needs_reroute = True`, triggering BFS rerouting on the next physics tick.

---

### 5.4 `proximity_monitor.py`

**Role:** A passive background observer that tracks inter-drone distances and triggers inter-drone communication events when drones come within range. It does not influence movement.

#### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `threshold` | `float` | `10.0` | Distance in metres below which proximity is logged |
| `robot_ids` | `string` | `robot1,robot2,...` | Comma-separated list of drone IDs to monitor |

#### Behaviour

1. Creates a Pose subscriber for every robot in `robot_ids` targeting `/robotN/pose`.
2. Creates a `Trigger` service client for every robot's `/robotN/communicate` endpoint.
3. Runs `check_proximity()` at **5 Hz**.

In `check_proximity()`, for every unique pair (r1, r2):
```python
dist = math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)
if dist < self.threshold:
    # Apply 1.0s cooldown per pair to avoid log flooding
    self.trigger_comm(r1, r2, dist)
```

When triggered, `trigger_comm()` calls the target drone's `/communicate` service asynchronously and logs the response via `add_done_callback`.

#### Communication Service Handler (in robot_node.py)

```python
def _communication_cb(self, request, response):
    response.success = True
    response.message = f"Hii this is {self.robot_id}"
    return response
```

Every robot exposes this service. It is purely demonstrating ROS 2 service-based inter-robot messaging.

#### ASCII Log Format

The monitor prints formatted ASCII boxes for every interaction:

```
+------------------------------------------------------------+
| PROXIMITY DETECTED   (Interaction #7)                      |
|------------------------------------------------------------|
| Robot A :  robot1                                          |
| Robot B :  robot3                                          |
| Distance:  3.82 units  (threshold 10.0)                    |
+------------------------------------------------------------+
```

---

### 5.5 `interactive_runner.py`

**Role:** The primary user-facing entry point. This is a pure Python procedural script (not a ROS 2 node) that gathers configuration from the terminal, validates it, dynamically generates a `.launch.py` file, and runs it.

#### Startup Sequence

```
ros2 run robot_proximity interactive_runner
        |
        v
[1] Print 10x8 grid visual showing obstacle cells as [XX]
[2] Print all valid cell connections
[3] Prompt: simulation mode (1=AUTO, 2=MANUAL)
[4] Prompt: obstacle spawn interval in seconds (0 = disable)
[5] AUTO: prompt robot count (1-10), select from AUTO_PATHS
    MANUAL: prompt waypoints for each robot, validate via resolve_path()
[6] generate_launch_file_content(robots_config, spawn_time)
        -> writes temp_interactive.launch.py to disk
[7] subprocess.run(["ros2", "launch", temp_launch_path])
```

#### AUTO_PATHS — 10 Pre-Stored Routes

| Robot | Colour | Route Description | Speed |
|---|---|---|---|
| robot1 | red | Full top row A1 to A10, then down right column to H10 | 0.8 |
| robot2 | blue | Down left column A1 to H1, then across bottom to H10 | 0.8 |
| robot3 | green | S-curve through centre with obstacle cells auto-rerouted | 0.8 |
| robot4 | purple | Right-to-left top row A10 to A1, then down left column | 0.8 |
| robot5 | orange | Column 5 full vertical traverse A5 to H5 | 0.8 |
| robot6 | cyan | Bottom row H10 to H1, then up left column to A1 | 0.8 |
| robot7 | magenta | Full outer perimeter clockwise loop | 0.6 |
| robot8 | yellow | Interior zigzag diagonal | 0.8 |
| robot9 | teal | Column 6 traverse with horizontal cross at F row | 0.8 |
| robot10 | white | Inner rectangular loop C3 to G7 | 0.8 |

#### MANUAL Mode Validation

For each manually entered path:
1. Splits input on commas into a waypoint list
2. Checks all nodes exist in `gm.nodes`
3. Calls `gm.resolve_path(waypoints)` — BFS fills gaps automatically
4. Requires at least 2 resolved nodes, reports errors otherwise

#### generate_launch_file_content(robots, spawn_time)

Produces a Python launch file as an f-string containing a valid `generate_launch_description()` function with:
- One `Node()` per robot (package, executable, name, parameters: robot_id, color, path, speed, radius)
- One `proximity_monitor` node (threshold=3.5, robot_ids=joined string)
- One `graph_visualizer` node (spawn_interval=spawn_time from user input)
- One `rviz2` node pointing at `simulation.rviz`

The file is written to `temp_interactive.launch.py` in the current working directory and immediately executed via `subprocess.run`.

---

### 5.6 `diag_test.py`

**Role:** A standalone Python utility for offline path validation. Does not import or require a running ROS 2 environment.

#### Function

```python
def test():
    gm = GraphManager()
    paths_to_test = [
        ('robot1', 'A1,A2,A3,A4,A5,A6,A7,B7,C7,D7,E7'),
        ('robot3', 'A1,A2,B2,C2,C3,C4,C5,D5,E5,E6,E7'),
        ('robot5', 'A3,B3,C3,D3,E3,E4,D4,C4,B4,A4,A5')
    ]
    for rid, path_str in paths_to_test:
        resolved = gm.resolve_path(waypoints)
        # Check: no obstacle nodes in resolved path
        # Check: every consecutive pair has a valid edge
```

Outputs `Path is VALID` or detailed error messages per path. Used during development to catch routing bugs without starting the full simulation.

**Usage:**
```bash
python3 src/robot_proximity/robot_proximity/diag_test.py
```

---

### 5.7 `simulation.launch.py`

**Role:** A static, pre-built 4-robot launch configuration for quick repeatable launches without the interactive terminal prompt.

Launches four robots (robot1=red, robot2=blue, robot3=green, robot4=purple) on hardcoded paths at speed 0.5 and radius 1.5. Also launches `proximity_monitor` (threshold=3.0), `graph_visualizer` at default spawn_interval, and RViz.

The RViz config path first checks the old source directory path and falls back to the installed share directory.

**Usage:**
```bash
ros2 launch robot_proximity simulation.launch.py
```

---

### 5.8 `simulation.rviz`

**Role:** Defines the complete RViz2 display panel configuration loaded at startup.

| Display Name | Topic | Description |
|---|---|---|
| Grid | (built-in) | Background reference grid |
| Graph Markers | `/graph_markers` | Full 10x8 cell grid, obstacle blocks, labels |
| Robot 1 | `/robot1/markers` | Drone body, arms, props, label, comms disc |
| Robot 2-10 | `/robot2-10/markers` | Same as Robot 1 for each drone |

**Camera configuration:**
- Fixed Frame: `map`
- View type: Orbit
- Camera distance: 30 units
- Focal point: X=6, Y=5, Z=0 (centre of the 10x8 grid)
- Pitch: 0.7 rad, Yaw: 0.7 rad (angled top-down view)
- Window size: 1200 x 800 pixels

---

## 6. Algorithms in Detail

### 6.1 BFS Pathfinding

Breadth-First Search is used in three distinct scenarios within the simulation.

**Scenario A — Initial path stitching via `resolve_path(waypoints)`:**

When a robot receives a waypoint list like `A1,C2,H10`, node `C2` may be an obstacle. `resolve_path` iterates consecutive waypoint pairs and calls `find_path(src, dst)` to auto-route around any obstacles, stitching sub-paths into a single complete traversable path.

**Scenario B — Deadlock rerouting via `find_path_excluding(start, end, blocked)`:**

When a drone times out waiting for a blocked cell (after 2.5 seconds), it collects all cells claimed by all other drones and requests a new path that entirely avoids them:

```python
blocked = self._blocked_cells_set()  # Union of all other robots' claimed cells
blocked.discard(final_dest)          # Never exclude the destination
blocked.discard(current_cell)        # Never exclude current position
new_path = self.gm.find_path_excluding(current_cell, final_dest, blocked)
```

**Scenario C — Dynamic obstacle rerouting via `_reroute(force=True)`:**

Triggered immediately when `/dynamic_obstacles` is received. Performs the same `find_path_excluding` call, this time prioritising newly blocked obstacle cells.

**Core BFS Implementation:**
```python
visited = {start}
queue   = deque([(start, [start])])
while queue:
    cur, path = queue.popleft()
    for nb in self._adj[cur]:          # O(1) adjacency lookup
        if nb == end:
            return path + [nb]         # Shortest path found
        if nb not in visited:
            visited.add(nb)
            queue.append((nb, path + [nb]))
return None                            # No path exists
```

**Complexity:** O(V + E) where V = 80 nodes and E ≈ 120 edges. BFS guarantees the shortest path in terms of hop count.

---

### 6.2 PD Controller and Virtual Rabbit Tracking

The core navigation innovation. Instead of rigidly teleporting the drone along grid segments, the system uses a Proportional-Derivative controller to pursue a ghost "virtual rabbit" that moves strictly along the path ahead.

**Step 1 — Advance the virtual rabbit along the grid path:**
```python
self.alpha += (self.speed * dt) / edge_length   # alpha in [0, 1] per edge segment
rabbit_x, rabbit_y = gm.interpolate(cur_node, next_node, self.alpha)
```

**Step 2 — Compute tracking error and rabbit velocity:**
```python
err_x     = rabbit_x - self.x          # Position error X
err_y     = rabbit_y - self.y          # Position error Y
rabbit_vx = (dx / edge_len) * speed    # Rabbit's velocity X
rabbit_vy = (dy / edge_len) * speed    # Rabbit's velocity Y
```

**Step 3 — PD control law:**
```
Kp = 3.5   (proportional gain — how strongly to close the gap)
Kd = 2.0   (derivative gain  — damps oscillation, velocity matching)

ax = Kp * err_x + Kd * (rabbit_vx - vx)
ay = Kp * err_y + Kd * (rabbit_vy - vy)
```

**Step 4 — Euler integration of velocity and position:**
```python
self.vx += ax * dt;   self.x += self.vx * dt
self.vy += ay * dt;   self.y += self.vy * dt
```

**Step 5 — Speed cap to prevent corner runaway:**
```python
cur_speed = sqrt(vx*vx + vy*vy)
if cur_speed > speed * 1.5:
    vx = (vx / cur_speed) * (speed * 1.5)
    vy = (vy / cur_speed) * (speed * 1.5)
```

The key insight: the drone carries actual velocity `(vx, vy)` going into a turn. The PD controller's acceleration pulls it toward the rabbit, but momentum causes it to **sweep wide** in a natural arc — exactly how real aircraft round corners.

---

### 6.3 Quadcopter Tilt Model

A real quadcopter generates horizontal force by tilting its thrust vector. This simulation reverses that: the required acceleration determines the tilt angle.

**Step 1 — Rotate world-frame acceleration into drone body frame using yaw (psi):**
```
a_fwd = ax * cos(psi) + ay * sin(psi)     (forward thrust component)
a_lat = -ax * sin(psi) + ay * cos(psi)   (lateral thrust component)
```

**Step 2 — Convert to tilt angles using gravity (g = 9.81 m/s^2):**
```
target_pitch = atan2(a_fwd, g) * 1.5     (positive = nose down / forward lean)
target_roll  = -atan2(a_lat, g) * 1.5   (positive = right bank)
```

The multiplier of 1.5 amplifies the visual effect for clarity without changing the physics logic.

**Step 3 — Spring-damper smoothing to simulate rotational inertia:**
```
tilt_spring = 40.0    tilt_damp = 8.0

pitch_vel += ((target_pitch - pitch) * tilt_spring - pitch_vel * tilt_damp) * dt
pitch     += pitch_vel * dt
```
This makes the body take approximately 0.3 seconds to fully adopt a new tilt — matching the characteristic lag seen in real drone footage.

---

### 6.4 Yaw Spring-Damper

The drone's heading tracks its true velocity direction rather than the grid segment direction:

```python
if cur_speed > 0.1:
    target_yaw = atan2(vy, vx)            # Heading = direction of motion

yaw_diff  = angle_diff(target_yaw, current_yaw)   # Shortest-arc difference
yaw_accel = yaw_diff * 15.0 - yaw_vel * 5.0       # Spring-damper
yaw_vel  += yaw_accel * dt
yaw_vel   = clamp(yaw_vel, -3.0, +3.0)            # Max 3 rad/s
current_yaw += yaw_vel * dt
```

`angle_diff` normalises to (-pi, pi] ensuring the drone always rotates via the shortest angular arc, never spinning the wrong way around.

---

### 6.5 Cell-Based Deadlock Prevention

Every drone claims the cells it currently occupies or is traversing by broadcasting to `/robot_cell_registry`:

- `"robot1:A3,A4"` — robot1 is actively moving from A3 to A4
- `"robot2:B7"` — robot2 is stationary at B7

Before advancing to the next cell, the drone checks:

```python
def _is_cell_blocked(self, cell_name):
    for claimed in self._cells_of_others.values():
        if cell_name in claimed:
            return True
    return False
```

If blocked, the drone hovers in place and starts a timer:
```python
secs = (now - self._wait_start_time).nanoseconds / 1e9
if secs >= DEADLOCK_TIMEOUT:    # 2.5 seconds
    self._reroute()             # Invoke BFS reroute
```

Successfully rerouted paths increment `_reroute_count` for telemetry tracking.

---

### 6.6 Distance-Priority Yielding

A reactive secondary layer that catches cases where drones approach each other between cell boundaries where the registry system alone is insufficient.

**Priority Rule:** Lower numerical ID = higher priority. `robot1 > robot2 > ... > robot10`.

```python
def get_id_num(rid):
    return int(''.join(filter(str.isdigit, rid)))   # "robot4" -> 4

for other_id, other_pos in self._poses_of_others.items():
    dx = other_pos.x - self.x
    dy = other_pos.y - self.y
    dz = other_pos.z - self.z
    dist3d = sqrt(dx*dx + dy*dy + dz*dz)

    if dist3d < 2.5 and get_id_num(other_id) < get_id_num(self.robot_id):
        self._is_yielding = True   # This drone pauses
        break
```

While yielding, no PD advancement occurs. The drone gently levels its tilt and logs a warning every 100 timer frames.

---

### 6.7 Dynamic Obstacle Spawning

Controlled entirely by the `spawn_interval` parameter entered by the user at launch.

**Full chain of events:**

1. `graph_visualizer` timer fires at the user-defined interval.
2. Reads `robot_cells` dict to find all currently occupied cells.
3. Randomly samples 15 unoccupied cells from all 80 grid nodes.
4. Publishes them as a comma-separated string to `/dynamic_obstacles`.
5. All `robot_node` instances receive this immediately:
   ```python
   def _dynamic_obs_cb(self, msg: String):
       new_obs = [o.strip() for o in msg.data.split(',') if o.strip()]
       self.gm.update_obstacles(new_obs)   # Rebuild adjacency graph
       self._needs_reroute = True          # Flag for next physics tick
   ```
6. On the next 50 Hz tick, the drone calls `_reroute(force=True)` which computes a new BFS path navigating around the new obstacle layout.
7. The graph_visualizer also updates its local GraphManager reference and re-renders the grid, showing the new red obstacle towers in RViz.

Setting `spawn_interval = 0` at startup prevents the timer from being created entirely, leaving the grid static with only the original 12 obstacles.

---

## 7. Flight State Machine

Each drone's lifecycle is governed by a four-state Finite State Machine defined by the `FlightState` enum:

```
[LANDED] ---> path exists ---> [TAKING_OFF] ---> z >= 1.2m ---> [FLYING]
   ^                                                                  |
   |                                            arrive at final dest  |
   |                                                                  v
[LANDED] <--- z <= 0.0 <--- [LANDING] <----------------------------------
```

| State | Value | Z Behaviour | Propeller Speed | Horizontal Movement |
|---|---|---|---|---|
| `LANDED` | 0 | Fixed at z = 0.0 | Stopped | None |
| `TAKING_OFF` | 1 | z increases at v_z = 0.6 m/s | +15 rad/s | None (waiting for cruise altitude) |
| `FLYING` | 2 | z = 1.2m + hover bob | +20 rad/s | Full PD physics + all avoidance |
| `LANDING` | 3 | z decreases at v_z = 0.6 m/s | +10 rad/s | None, tilt resets toward 0 |

**Hover bobbing** (active in all non-LANDED states):
```python
hover_drift_z = 0.05 * sin(hover_time * 2.5)
```
This produces a gentle sinusoidal altitude oscillation of +/-5 cm at approximately 0.4 Hz, making flying drones look alive.

---

## 8. ROS Topics, Services and Parameters

### Topics

| Topic | Message Type | Publisher | Subscribers | Description |
|---|---|---|---|---|
| `/robot_cell_registry` | `String` | All robot_nodes | All robot_nodes + graph_visualizer | Drone cell reservation registry |
| `/robotN/pose` | `Pose` | robot_node N | All robot_nodes + proximity_monitor | 3D position + quaternion orientation |
| `/robotN/markers` | `MarkerArray` | robot_node N | RViz | Full drone visual (body, arms, props, label) |
| `/graph_markers` | `MarkerArray` | graph_visualizer | RViz | Grid ground, lines, obstacles, cell labels |
| `/dynamic_obstacles` | `String` | graph_visualizer | All robot_nodes | Comma list of new obstacle cells |

### Services

| Service | Type | Server | Client | Trigger Condition |
|---|---|---|---|---|
| `/robotN/communicate` | `Trigger` | robot_node N | proximity_monitor | Two drones within proximity threshold |

### Parameters by Node

| Node | Parameter | Type | Default | Description |
|---|---|---|---|---|
| `robot_node` | `robot_id` | string | `robot1` | Unique drone ID |
| `robot_node` | `color` | string | `red` | Body and propeller colour |
| `robot_node` | `path` | string | `A1,A2,A3` | Waypoint list (comma-separated) |
| `robot_node` | `speed` | float | `0.4` | Virtual rabbit speed (m/s) |
| `robot_node` | `radius` | float | `2.0` | Comm-range disc radius (m) |
| `proximity_monitor` | `threshold` | float | `10.0` | Proximity detection radius (m) |
| `proximity_monitor` | `robot_ids` | string | — | Comma-separated drone IDs to monitor |
| `graph_visualizer` | `spawn_interval` | float | `8.0` | Obstacle reshuffle interval (s). 0 = disabled |

---

## 9. Running the Project — All Modes

### Mode 1: Interactive Runner (Recommended)

```bash
ros2 run robot_proximity interactive_runner
```

The terminal prompts in order:
1. Displays the full grid map with obstacle markers
2. Lists all valid cell connections
3. Asks for simulation mode: **1 = AUTO**, **2 = MANUAL**
4. Asks for obstacle spawn interval in seconds (**0 to disable**)
5. AUTO: asks for robot count (1-10)
   MANUAL: asks for waypoint path per robot then validates it

### Mode 2: Static Launch File

```bash
ros2 launch robot_proximity simulation.launch.py
```

Immediately launches 4 pre-configured robots with no prompts. Dynamic obstacles use the default 8-second interval.

### Mode 3: Individual Node Launch (Debug)

Open four terminal windows:

```bash
# Terminal 1 — Launch a single drone
source /opt/ros/humble/setup.bash
source install/setup.bash
ros2 run robot_proximity robot_node --ros-args \
  -p robot_id:=robot1 -p color:=red \
  -p path:=A1,B1,C1,D1,H1 -p speed:=0.4 -p radius:=2.0

# Terminal 2 — Launch the grid visualizer
ros2 run robot_proximity graph_visualizer --ros-args -p spawn_interval:=6.0

# Terminal 3 — Launch the proximity monitor
ros2 run robot_proximity proximity_monitor --ros-args \
  -p robot_ids:=robot1 -p threshold:=5.0

# Terminal 4 — Launch RViz
rviz2 -d src/robot_proximity/config/simulation.rviz
```

### Mode 4: Path Diagnostics (no ROS required)

```bash
python3 src/robot_proximity/robot_proximity/diag_test.py
```

Tests three hard-coded paths and validates them against the GraphManager offline.

---

## 10. Build Instructions

```bash
# Step 1 — Source ROS 2 Humble environment
source /opt/ros/humble/setup.bash

# Step 2 — Navigate to the workspace root
cd "/home/jatin/ros2_assign_2_10_robo_modified_tonew/turtle_to_quadcopter final with modifications"

# Step 3 — Build the package
colcon build --packages-select robot_proximity

# Step 4 — Source the install overlay
source install/setup.bash

# Step 5 — Launch the simulation
ros2 run robot_proximity interactive_runner
```

After any source code change, repeat steps 3 and 4 before relaunching.

---

## 11. Grid Reference

```
     Col:  1     2     3     4     5     6     7     8     9    10
Row A: [ A1] [ A2] [ A3] [ A4] [ A5] [ A6] [ A7] [ A8] [ A9] [A10]
         |     |     |     |     |     |     |     |     |     |
Row B: [ B1] [ B2] [ B3] [XXX] [ B5] [ B6] [ B7] [XXX] [ B9] [B10]
         |     |     |     |     |     |     |     |     |     |
Row C: [ C1] [XXX] [ C3] [ C4] [ C5] [XXX] [ C7] [ C8] [ C9] [C10]
         |     |     |     |     |     |     |     |     |     |
Row D: [ D1] [ D2] [ D3] [ D4] [XXX] [ D6] [ D7] [ D8] [XXX] [D10]
         |     |     |     |     |     |     |     |     |     |
Row E: [ E1] [ E2] [XXX] [ E4] [ E5] [ E6] [XXX] [ E8] [ E9] [E10]
         |     |     |     |     |     |     |     |     |     |
Row F: [ F1] [XXX] [ F3] [ F4] [ F5] [XXX] [ F7] [ F8] [ F9] [F10]
         |     |     |     |     |     |     |     |     |     |
Row G: [ G1] [ G2] [ G3] [XXX] [ G5] [ G6] [ G7] [ G8] [XXX] [G10]
         |     |     |     |     |     |     |     |     |     |
Row H: [ H1] [ H2] [ H3] [ H4] [ H5] [ H6] [ H7] [ H8] [ H9] [H10]

Legend:
  [XXX] = Static obstacle (12 total). BFS routes automatically avoid these.
  [A1]  = Walkable cell. Robots may traverse, wait, or be yielding here.

Grid Statistics:
  Dimensions  : 10 columns x 8 rows
  Cell spacing: 2.0 metres between cell centres
  Total cells : 80
  Obstacles   : 12 (static) + up to 15 (dynamic, reshuffled at user interval)
  Walkable    : 68 (when only static obstacles active)
```

---

*End of Documentation — robot_proximity v0.0.0 | ROS 2 Humble*
