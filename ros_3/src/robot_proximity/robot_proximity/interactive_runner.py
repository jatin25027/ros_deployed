import rclpy
import sys
import os
import subprocess
from robot_proximity.graph_manager import GraphManager
from ament_index_python.packages import get_package_share_directory


# ────────────────────────────────────────────────────────────────────────
#  Pre-stored paths for AUTO mode
#  Grid: 10×8  (A1 – H10)   80 cells total
#  Obstacles: B4, B8, C2, C6, D5, D9, E3, E7, F2, F6, G4, G9
#  Any path through an obstacle is auto-rerouted by BFS in the robot node.
# ────────────────────────────────────────────────────────────────────────
AUTO_PATHS = [
    # 1: Full top row → down right column
    {'id': 'robot1',  'color': 'red',
     'path': 'A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,B10,C10,D10,E10,F10,G10,H10',
     'speed': 0.8, 'radius': 2.0},

    # 2: Down left column → across bottom row
    {'id': 'robot2',  'color': 'blue',
     'path': 'A1,B1,C1,D1,E1,F1,G1,H1,H2,H3,H4,H5,H6,H7,H8,H9,H10',
     'speed': 0.8, 'radius': 2.0},

    # 3: S-curve through centre (includes obstacle cells — auto-rerouted)
    {'id': 'robot3',  'color': 'green',
     'path': 'A1,A2,A3,B3,B4,C4,C5,D5,D6,E6,E7,F7,F8,G8,G9,H9,H10',
     'speed': 0.8, 'radius': 2.0},

    # 4: Right → left across top, then down left column
    {'id': 'robot4',  'color': 'purple',
     'path': 'A10,A9,A8,A7,A6,A5,A4,A3,A2,A1,B1,C1,D1,E1,F1,G1,H1',
     'speed': 0.8, 'radius': 2.0},

    # 5: Column 5 full traverse top to bottom
    {'id': 'robot5',  'color': 'orange',
     'path': 'A5,B5,C5,D5,E5,F5,G5,H5',
     'speed': 0.8, 'radius': 2.0},

    # 6: Bottom row right to left, then up left column
    {'id': 'robot6',  'color': 'cyan',
     'path': 'H10,H9,H8,H7,H6,H5,H4,H3,H2,H1,G1,F1,E1,D1,C1,B1,A1',
     'speed': 0.8, 'radius': 2.0},

    # 7: Full outer perimeter clockwise (longest path)
    {'id': 'robot7',  'color': 'magenta',
     'path': 'A1,A2,A3,A4,A5,A6,A7,A8,A9,A10,'
             'B10,C10,D10,E10,F10,G10,H10,'
             'H9,H8,H7,H6,H5,H4,H3,H2,H1,'
             'G1,F1,E1,D1,C1,B1,A1',
     'speed': 0.6, 'radius': 2.0},

    # 8: Zigzag diagonal through interior
    {'id': 'robot8',  'color': 'yellow',
     'path': 'A2,B2,B3,C3,C4,D4,D5,E5,E6,F6,F7,G7,G8,H8,H9,H10',
     'speed': 0.8, 'radius': 2.0},

    # 9: Column 8 traversal with horizontal cross
    {'id': 'robot9',  'color': 'teal',
     'path': 'H1,G1,F1,F2,F3,F4,F5,F6,F7,F8,F9,F10,E10,D10,C10,B10,A10',
     'speed': 0.8, 'radius': 2.0},

    # 10: Inner rectangular loop
    {'id': 'robot10', 'color': 'white',
     'path': 'C3,C4,C5,C6,C7,D7,E7,F7,G7,G6,G5,G4,G3,F3,E3,D3,C3',
     'speed': 0.8, 'radius': 2.0},
]


def main():
    print("=" * 70)
    print("   INTERACTIVE ROBOT GRID SIMULATION  (10x8 Grid — 80 Cells)")
    print("=" * 70)

    gm = GraphManager()

    # ----- Show grid -----
    print_graph_visual(gm)
    print_connections(gm)

    # ----- Auto / Manual choice -----
    print("\n" + "=" * 65)
    print("  SIMULATION MODE")
    print("=" * 65)
    print("  1) AUTO   – use pre-stored paths (just enter robot count)")
    print("  2) MANUAL – define each robot's path yourself")
    print("=" * 65)
    print("  NOTE: If a path goes through an obstacle, the robot will")
    print("        automatically find an alternate route using BFS!")
    print("=" * 65)

    while True:
        choice = input("Enter choice (1 or 2): ").strip()
        if choice in ('1', '2'):
            break
        print("Invalid choice! Enter 1 or 2.")

    if choice == '1':
        robots_config = auto_mode()
    else:
        robots_config = manual_mode(gm)

    if not robots_config:
        print("No robots configured. Exiting.")
        return

    # ----- Generate and launch -----
    launch_content = generate_launch_file_content(robots_config)

    temp_launch_path = os.path.join(os.getcwd(), 'temp_interactive.launch.py')
    with open(temp_launch_path, 'w') as f:
        f.write(launch_content)

    print(f"\nStarting simulation with {len(robots_config)} robots...")
    print(f"Temporary launch file: {temp_launch_path}")
    subprocess.run(["ros2", "launch", temp_launch_path])


# ──────────────────────────────────────────────────────
#  Auto Mode
# ──────────────────────────────────────────────────────
def auto_mode():
    max_robots = len(AUTO_PATHS)
    print(f"\nAuto mode supports 1 to {max_robots} robots.")

    while True:
        try:
            n = int(input(f"Enter number of robots (1-{max_robots}): ").strip())
            if 1 <= n <= max_robots:
                break
            print(f"Please enter a number between 1 and {max_robots}.")
        except ValueError:
            print("Invalid input! Enter an integer.")

    selected = AUTO_PATHS[:n]
    print("\n--- Auto-assigned robot configurations ---")
    for r in selected:
        print(f"  {r['id']:>8}  ({r['color']:>7})  path: {r['path']}")
    print()
    return selected


# ──────────────────────────────────────────────────────
#  Manual Mode
# ──────────────────────────────────────────────────────
def manual_mode(gm):
    try:
        num_robots = int(input("\nEnter number of robots to simulate: ").strip())
        if num_robots <= 0:
            print("Number of robots must be positive!")
            return []
    except ValueError:
        print("Invalid input!")
        return []

    colors = ['red', 'blue', 'green', 'purple', 'orange', 'cyan', 'magenta',
              'yellow', 'teal', 'white']
    robots_config = []

    for i in range(num_robots):
        print(f"\n--- Configuring Robot {i + 1} ---")
        robot_id = f"robot{i + 1}"
        color = colors[i % len(colors)]

        while True:
            path_input = input(
                f"Enter waypoints for {robot_id} (comma-separated, e.g., A1,A2,B2,C2): "
            ).strip()
            path_list = [p.strip() for p in path_input.split(',') if p.strip()]

            if len(path_list) < 2:
                print("Path must have at least 2 waypoints!")
                continue

            # Check that all nodes exist (obstacles are allowed — BFS will reroute)
            valid = True
            for node in path_list:
                if node not in gm.nodes:
                    print(f"Error: Node '{node}' does not exist!")
                    valid = False
                    break

            if valid:
                # Try resolving the path
                resolved = gm.resolve_path(path_list)
                if len(resolved) >= 2:
                    print(f"  Resolved path: {' -> '.join(resolved)}")
                    robots_config.append({
                        'id': robot_id,
                        'color': color,
                        'path': path_input,
                        'speed': 0.8,
                        'radius': 2.0,
                    })
                    break
                else:
                    print("Error: Could not find a valid path between those waypoints!")
                    print("  (Some waypoints may be completely unreachable.)")
            else:
                print("Invalid path, please try again.")

    return robots_config


# ──────────────────────────────────────────────────────
#  Grid visual helpers
# ──────────────────────────────────────────────────────
def print_graph_visual(gm):
    cols = gm.num_cols
    rows_count = gm.num_rows
    row_letters = gm.row_letters   # read dynamically from GraphManager
    print(f"\n  {cols}x{rows_count} Grid  —  [XX] = Obstacle (robots auto-reroute via BFS)")
    print(f"  Cells: {row_letters[0]}1 to {row_letters[-1]}{cols}   |   "
          f"Total: {cols * rows_count}   |   Obstacles: {len(gm.obstacles)}")
    print("  Movement: horizontal and vertical ONLY (no diagonals)")
    print()
    for r_idx, letter in enumerate(row_letters):
        cells = []
        for c_idx in range(cols):
            name = f"{letter}{c_idx + 1}"
            cells.append("[XX]" if gm.is_obstacle(name) else f"[{name:>3}]")

        row_str = f"  {letter}:  " + " - ".join(cells)
        print(row_str)

        if r_idx < rows_count - 1:
            connector = "       " + "    ".join(["  |  "] * cols)
            print(connector)

    print()
    obs_str = ", ".join(gm.obstacles)
    print(f"  Obstacles ({len(gm.obstacles)}): {obs_str}")
    print()


def print_connections(gm):
    print("--- Available Grid Connections ---")
    connections = {}
    for start, end in gm.edges:
        connections.setdefault(start, []).append(end)
        connections.setdefault(end, []).append(start)
    for node in sorted(connections.keys()):
        connected = sorted(set(connections[node]))
        print(f"  Cell {node:>4} connects to: {', '.join(connected)}")
    print("----------------------------------")


# ──────────────────────────────────────────────────────
#  Launch file generator (per-robot marker topics)
# ──────────────────────────────────────────────────────
def generate_launch_file_content(robots):
    robots_str = str(robots)

    return f"""
import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    pkg_dir = get_package_share_directory('robot_proximity')
    rviz_config_dir = os.path.join(pkg_dir, 'config', 'simulation.rviz')

    # User Defined Robots
    robots = {robots_str}

    robot_nodes = []
    robot_ids = []

    for r in robots:
        robot_ids.append(r['id'])
        robot_nodes.append(
            Node(
                package='robot_proximity',
                executable='robot_node',
                name=r['id'],
                parameters=[{{
                    'robot_id': r['id'],
                    'color': r['color'],
                    'path': r['path'],
                    'speed': r['speed'],
                    'radius': r['radius']
                }}],
                output='screen'
            )
        )

    ld_nodes = [
        *robot_nodes,

        Node(
            package='robot_proximity',
            executable='proximity_monitor',
            name='proximity_monitor',
            parameters=[{{
                'threshold': 3.5,
                'robot_ids': ','.join(robot_ids)
            }}],
            output='screen'
        ),
        Node(
            package='robot_proximity',
            executable='graph_visualizer',
            name='graph_visualizer',
            output='screen'
        )
    ]

    if 'DISPLAY' in os.environ:
        ld_nodes.append(
            Node(
                package='rviz2',
                executable='rviz2',
                name='rviz2',
                arguments=['-d', rviz_config_dir],
                output='screen'
            )
        )
    elif os.environ.get('FOXGLOVE_BRIDGE') == 'true':
        ld_nodes.append(
            Node(
                package='foxglove_bridge',
                executable='foxglove_bridge',
                name='foxglove_bridge',
                parameters=[{{
                    'port': 8765,
                    'address': '0.0.0.0',
                    'tls': False,
                    'topic_whitelist': ['.*'],
                    'send_buffer_limit': 10000000
                }}],
                output='screen'
            )
        )

    return LaunchDescription(ld_nodes)
"""


if __name__ == '__main__':
    main()
