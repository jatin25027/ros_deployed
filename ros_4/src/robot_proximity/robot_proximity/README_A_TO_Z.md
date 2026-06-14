# Quadcopter Multi-Agent Simulation: Comprehensive Documentation

## 1. Project Overview

The **Quadcopter Multi-Agent Simulation** project is an advanced ROS 2 (Robot Operating System) based ecosystem designed to orchestrate and visualize the collaborative and collision-free movement of multiple quadcopters operating within a shared 3D airspace. 

Built extensively utilizing Python, the ROS 2 Humble environment, and RViz2 for high-fidelity spatial rendering, this simulation goes beyond simple waypoint navigation strictly by incorporating rigid body dynamics, reactive collision avoidance mechanisms, graph-theory-based pathfinding, and realistic aesthetic visualizations of quadcopter pitch, roll, and yaw natively derived from Cartesian acceleration.

---

## 2. System Architecture

The ecosystem relies on an asynchronous publish-subscribe mesh typical of ROS 2 paradigms. Each quadcopter operates as a statistically independent computational node (`RobotNode`), ensuring the simulation represents a truly decentralized multi-agent environment rather than a centrally coordinated puppet system.

### Core Modules
1. **`robot_node.py`**: The primary intelligence and physics controller. Every quadcopter runs an isolated instance of this script.
2. **`interactive_runner.py`**: A centralized spawning multiplexer that assigns paths, scales temporal attributes, launches the specific requested independent node instances, and boots up RViz.
3. **`graph_manager.py`**: The mathematical mapping foundation. Translates a logical `A1-H10` style geographical grid into spatial $xy$-coordinates and computes shortest-paths using Breadth-First Search (BFS) strategies.
4. **`proximity_monitor.py` & `diag_test.py`**: Supplementary diagnostics services tracking node health and logging dynamic spatial intersections.

---

## 3. Flight State Machine

The lifetime of each agent is rigidly governed by an enumerated Finite State Machine (FSM):

- **`LANDED (0)`**: Starting state. The drone sits on the ground with zero vertical altitude.
- **`TAKING_OFF (1)`**: Triggered when a path is assigned. The drone gradually climbs to the cruising altitude (`target_z`) while simulating high prop-spin rotation.
- **`FLYING (2)`**: The cruise state. The multi-dimensional PD controller handles horizontal trajectory mapping.
- **`LANDING (3)`**: Triggered exclusively when the spatial distance between the drone and its final geographical destination falls beneath an ultra-low threshold.

---

## 4. Physics and Flight Dynamics Algorithm

This project eschews basic rigid point-to-point sliding in favor of realistic Drone Newtonian approximations. Because real quadcopters dictate lateral traverse strictly by altering the orientation of their downward-facing thrust vector, our nodes emulate this reality mathematically.

### 4.1 Proportional-Derivative (PD) Virtual Rabbit Tracking
To achieve gracefully rounded corners, the drone strictly pursues a "virtual rabbit" that moves along the rigid logical graph. 

- $x_{rabbit}$, $y_{rabbit}$: The coordinates exactly on the strict linear grid.
- $\vec{v}_{rabbit}$: The derivative vector representing the immediate velocity of the virtual target.
- $x, y$: The true physical coordinates of the quadcopter.

Using a highly tuned spring-damper logic (Kp = 3.5, Kd = 2.0), the drone computes the desired $X$ and $Y$ accelerations:
$$a_x = K_p (x_{rabbit} - x) + K_d (v_{rabbit\_x} - v_x)$$
$$a_y = K_p (y_{rabbit} - y) + K_d (v_{rabbit\_y} - v_y)$$

This naturally forces the drone to "swing wide" on sharp $90^\circ$ turns, yielding an incredibly realistic curved cornering logic naturally resulting from momentum retention.

### 4.2 Accelerative Tilt Conversion
Instead of manually spoofing the tilt aesthetic, the simulated pitch and roll are explicitly derived from the required accelerations rotated into the quadcopter's body frame (dictated by Yaw). 

$$a_{fwd} = a_x \cos(\psi) + a_y \sin(\psi)$$
$$a_{lat} = -a_x \sin(\psi) + a_y \cos(\psi)$$

Assuming $g$ is the standard gravitational constant, the tilt required to maintain such lateral acceleration is natively retrieved through the arc-tangent proportion of horizontal thrust to vertical gravity:

$$\text{Pitch} = \arctan \left(\frac{a_{fwd}}{g}\right) \times 1.5$$
$$\text{Roll} = -\arctan \left(\frac{a_{lat}}{g}\right) \times 1.5$$

These hard angles are subsequently smoothed again by an independent second-order differential equation simulating the rotational inertia of the physical drone body itself.

---

## 5. Algorithmic Avoidance & Routing

Because the drones operate simultaneously in tight configurations, advanced avoidance logics run identically and concurrently on all agents to guarantee no physical intersections.

### 5.1 Cell-Based Registry (Deadlock Prevention)
Each drone explicitly reserves the specific "square" (i.e. node A1) that it currently sits on via a multi-cast ROS Topic (`/robot_cell_registry`). Before advancing to a new cell, the drone queries the global database representation.
- If a target cell is occupied by a drone that is also waiting, an algorithmic stall is detected within a brief threshold (e.g., $2.5$ seconds) termed the `DEADLOCK_TIMEOUT`.
- The system then performs an impromptu A-Star/BFS graph traversal recalculation that completely obfuscates the clogged cell from the topological mapping, forcing an alternative geographical path entirely around the offending agent.

### 5.2 Distance-Based Priority Yielding (Reactive)
If paths intersect mid-edge or drones approach each other perpendicularly, the standard Cell Registry might fail due to instantaneous overlap gaps.
- Each `RobotNode` subscribes explicitly globally to all other nodes' `/pose` feeds.
- If distance breaches internal limits ($< 2.5$ meters in Cartesian space), a hardcoded logic steps in evaluating the integer extraction of the drone's name (e.g., `robot2` vs. `robot4`). 
- The drone possessing the historically "newer" ID (numerically higher) is forced to perform a complete horizontal trajectory halt and "Yield" (Hover), freezing coordinate advancement while allowing the numerically superior agent the right of way.

---

## 6. Execution Instructions

1. **Source ROS 2 Framework**  
   Load the Humble variables specifically in the Linux/WSL instance.
   ```bash
   source /opt/ros/humble/setup.bash
   ```

2. **Re-Compilation**  
   If mathematical variables or logic handlers require updating, clean and rebuild the package.
   ```bash
   cd "/home/jatin/ros2_assign_2_10_robo_modified_tonew/turtle_to_quadcopter final with modifications"
   colcon build
   source install/setup.bash
   ```

3. **Interactive Launch**  
   Fire the runner script. This boots up the centralized simulation controller capable of creating interactive or highly randomized environments explicitly showcasing the rounded flight physics and collision avoidance mechanisms.
   ```bash
   ros2 run robot_proximity interactive_runner
   ```

---
*End of Documentation*
