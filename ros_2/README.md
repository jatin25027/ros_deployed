# Robot Proximity Communication System

A ROS2-based simulation where multiple robots navigate a graph, detect each other's proximity, and communicate via ROS2 services. All movement and interactions are visualized in real-time using RViz2.

---

## Prerequisites

- **ROS2 Humble** on WSL (Ubuntu 22.04)
- **X Server** for RViz (WSLg, GWSL, or VcXsrv)
- All commands below must be run inside your **WSL terminal**, not PowerShell/CMD.

---

## Setup and Build

```bash
# 1. Source ROS2
source /opt/ros/humble/setup.bash

# 2. Navigate to workspace
cd ~/ros2_ASSIGN_2_updated

# 3. Build
colcon build --packages-select robot_proximity

# 4. Source workspace
source install/setup.bash
```

---

## Running the Project

### Interactive Simulation (Recommended)

```bash
ros2 run robot_proximity interactive_runner
```

This gives you two modes:

| Mode | What it does |
|------|-------------|
| **Auto** (enter `1`) | Pre-stored paths for 1–10 robots. Just enter the robot count. |
| **Manual** (enter `2`) | You define each robot's path node-by-node (e.g., `A,B,C,D,E`). |

### Default 4-Robot Launch

```bash
ros2 launch robot_proximity simulation.launch.py
```

---

## Architecture Overview

The system has **5 ROS2 nodes** that communicate via topics and services:

```
┌─────────────────────────────────────────────────────────────┐
│                     ROS2 LAUNCH                             │
│  Starts: robot_node(s), proximity_monitor, graph_visualizer,│
│          rviz2                                              │
└─────────────────────────────────────────────────────────────┘

  ┌──────────────┐         /{robot_id}/pose           ┌──────────────────┐
  │  robot_node   │ ─────── (Pose topic) ──────────▶  │ proximity_monitor │
  │  (per robot)  │                                   │                  │
  │              │ ◀─── /{robot_id}/communicate ────  │  Checks distance │
  │  Moves along │       (Trigger service)            │  between all     │
  │  graph edges │                                    │  robot pairs     │
  └──────┬───────┘                                    └──────────────────┘
         │
         │  /{robot_id}/markers
         │  (MarkerArray topic)
         ▼
  ┌──────────────┐         /graph_markers             ┌──────────────────┐
  │    RViz2      │ ◀───── (MarkerArray topic) ─────  │ graph_visualizer  │
  │              │                                    │                  │
  │  Displays    │ ◀── /{robot_id}/markers ──────────  │  Publishes graph │
  │  everything  │     (from each robot_node)         │  nodes + edges   │
  └──────────────┘                                    └──────────────────┘
```

---

## Component Details

### 1. `graph_manager.py` — Graph Data Structure

**Purpose:** Defines the graph (nodes and edges) that robots navigate on.

- **20 nodes** arranged in a 5×4 grid, labeled A through T (with `N` stored as `NodeN` to avoid YAML boolean parsing issues).
- **Edges:** Horizontal, vertical, and both diagonal directions — giving each interior node up to 8 neighbors.
- Provides helper functions: `get_coords()`, `is_edge()`, `interpolate()`, `get_distance()`.

```
  Row 0:   A --- B --- C --- D --- E
           | \ / | \ / | \ / | \ / |
  Row 1:   F --- G --- H --- I --- J
           | / \ | / \ | / \ | / \ |
  Row 2:   K --- L --- M --- N --- O    (N = NodeN internally)
           | \ / | \ / | \ / | \ / |
  Row 3:   P --- Q --- R --- S --- T
```

### 2. `robot_node.py` — Robot Movement & Visualization

**Purpose:** Each robot runs as a separate ROS2 node that moves along its assigned path.

**How it works:**
1. Reads ROS2 parameters: `robot_id`, `color`, `path`, `speed`, `radius`.
2. Validates the path against graph edges at startup.
3. Runs a **50Hz timer** that interpolates the robot's position between graph nodes using real time-delta for frame-rate-independent movement.
4. **Publishes:**
   - `/{robot_id}/pose` (Pose) — current position at 50Hz for proximity checking.
   - `/{robot_id}/markers` (MarkerArray) — 3 markers at 25Hz:
     - **Sphere** — the robot body (colored).
     - **Cylinder** — communication range disk (semi-transparent).
     - **Text** — robot name label floating above.
5. **Service server** `/{robot_id}/communicate` — responds to incoming communication requests with `"Hii this is {robot_id}"`.

### 3. `proximity_monitor.py` — Proximity Detection & Communication Trigger

**Purpose:** Monitors all robot positions and triggers communication when two robots are within a distance threshold.

**How it works:**
1. Subscribes to `/{robot_id}/pose` for every robot.
2. Runs a **5Hz check** that calculates Euclidean distance between every pair of active robots.
3. When distance < threshold (default 3.0 units):
   - Logs a **PROXIMITY DETECTED** box with both robot names and distance.
   - Calls the target robot's `/{robot_id}/communicate` service (asynchronous).
   - Logs a **COMMUNICATION REQUEST** box showing sender → receiver.
   - On response, logs a **COMMUNICATION RESPONSE** box showing receiver ← sender.
4. Uses a **cooldown** (1 second per pair) to avoid flooding.

**Terminal output format:**
```
+------------------------------------------------------------+
| PROXIMITY DETECTED   (Interaction #3)                      |
|------------------------------------------------------------|
| Robot A :  robot1                                          |
| Robot B :  robot2                                          |
| Distance:  2.45 units  (threshold 3.0)                     |
+------------------------------------------------------------+

+------------------------------------------------------------+
| COMMUNICATION REQUEST  #3                                  |
|------------------------------------------------------------|
| Sender   :  robot1                                         |
| Receiver :  robot2                                         |
| Direction:  robot1  -->  robot2                             |
+------------------------------------------------------------+

+------------------------------------------------------------+
| COMMUNICATION RESPONSE  #3                                 |
|------------------------------------------------------------|
| Responder :  robot2                                        |
| Reply To  :  robot1                                        |
| Direction :  robot2  <--  robot1  (reply)                   |
+------------------------------------------------------------+
```

### 4. `graph_visualizer.py` — Graph Rendering in RViz

**Purpose:** Visualizes the underlying graph structure (nodes, edges, labels) in RViz.

**How it works:**
1. Publishes to `/graph_markers` (MarkerArray) at **1Hz**.
2. Renders:
   - **White spheres** at each graph node position.
   - **Gray lines** for every edge.
   - **Text labels** (A, B, C, ... T) floating above each node.

### 5. `interactive_runner.py` — Interactive Simulation Launcher

**Purpose:** User-friendly entry point that configures and launches the simulation.

**How it works:**
1. Displays the graph map and all valid connections.
2. Asks user to choose **Auto** or **Manual** mode:
   - **Auto:** 10 pre-stored, graph-validated paths. User only enters robot count (1–10).
   - **Manual:** User defines each robot's path interactively with real-time edge validation.
3. Generates a temporary ROS2 launch file with the configured robots.
4. Executes `ros2 launch` to start all nodes simultaneously.

---

## ROS2 Topics & Services

| Topic / Service | Type | Publisher | Subscriber | Purpose |
|----------------|------|-----------|------------|---------|
| `/{robot_id}/pose` | `geometry_msgs/Pose` | robot_node | proximity_monitor | Real-time robot position |
| `/{robot_id}/markers` | `visualization_msgs/MarkerArray` | robot_node | RViz | Robot body, range, label |
| `/{robot_id}/communicate` | `std_srvs/Trigger` | robot_node (server) | proximity_monitor (client) | Communication service |
| `/graph_markers` | `visualization_msgs/MarkerArray` | graph_visualizer | RViz | Graph nodes, edges, labels |

---

## Project Structure

```
ros2_ASSIGN_2_updated/
├── src/robot_proximity/
│   ├── robot_proximity/
│   │   ├── graph_manager.py         # Graph data structure (nodes, edges)
│   │   ├── robot_node.py            # Robot movement & visualization node
│   │   ├── proximity_monitor.py     # Proximity detection & communication
│   │   ├── graph_visualizer.py      # RViz graph rendering
│   │   └── interactive_runner.py    # Auto/manual simulation launcher
│   ├── launch/
│   │   └── simulation.launch.py     # Default 4-robot launch file
│   ├── config/
│   │   └── simulation.rviz          # RViz display configuration
│   ├── package.xml
│   └── setup.py
├── build/                            # Build output (auto-generated)
├── install/                          # Install output (auto-generated)
└── README.md                         # This file
```
