import rclpy
import sys
import os
import subprocess
from robot_proximity.graph_manager import GraphManager
from ament_index_python.packages import get_package_share_directory


# ────────────────────────────────────────────────────────
#  Pre-stored paths for auto mode (all validated against
#  the graph edges in GraphManager)
# ────────────────────────────────────────────────────────
AUTO_PATHS = [
    # 1: Top row left→right, down right col, bottom row back
    {'id': 'robot1',  'color': 'red',     'path': 'A,B,C,D,E,J,O,T,S,R,Q,P',       'speed': 0.5, 'radius': 1.5},
    # 2: Top row right→left, down left col, bottom row forward
    {'id': 'robot2',  'color': 'blue',    'path': 'E,D,C,B,A,F,K,P,Q,R,S,T',       'speed': 0.5, 'radius': 1.5},
    # 3: Diagonal zig-zag
    {'id': 'robot3',  'color': 'green',   'path': 'A,G,M,S,T,O,I,C,B,F,K,Q',       'speed': 0.5, 'radius': 1.5},
    # 4: Bottom row back then up left col, top row forward
    {'id': 'robot4',  'color': 'purple',  'path': 'T,S,R,Q,P,K,F,A,B,C,D,E',       'speed': 0.5, 'radius': 1.5},
    # 5: Bottom row forward then up right col, top row back
    {'id': 'robot5',  'color': 'orange',  'path': 'P,Q,R,S,T,O,J,E,D,C,B,A',       'speed': 0.5, 'radius': 1.5},
    # 6: Middle row 2 left→right then row 1 right→left
    {'id': 'robot6',  'color': 'cyan',    'path': 'K,L,M,NodeN,O,J,I,H,G,F',       'speed': 0.5, 'radius': 1.5},
    # 7: Middle row 1 left→right then row 2 right→left
    {'id': 'robot7',  'color': 'magenta', 'path': 'F,G,H,I,J,O,NodeN,M,L,K',       'speed': 0.5, 'radius': 1.5},
    # 8: Loop-ish around top-right
    {'id': 'robot8',  'color': 'yellow',  'path': 'A,F,G,H,I,J,E,D,C,B',           'speed': 0.5, 'radius': 1.5},
    # 9: Vertical zig-zag center
    {'id': 'robot9',  'color': 'teal',    'path': 'B,G,L,Q,R,M,H,C,D,I,NodeN,S',   'speed': 0.5, 'radius': 1.5},
    # 10: Vertical zig-zag center reverse
    {'id': 'robot10', 'color': 'white',   'path': 'D,C,H,M,R,Q,L,G,B,A',           'speed': 0.5, 'radius': 1.5},
]


def main():
    print("=" * 60)
    print("   INTERACTIVE ROBOT SIMULATION VISUALIZER")
    print("=" * 60)

    gm = GraphManager()

    # ----- Show graph -----
    print_graph_visual()
    print_connections(gm)

    # ----- Auto / Manual choice -----
    print("\n" + "=" * 60)
    print("  SIMULATION MODE")
    print("=" * 60)
    print("  1) AUTO   – use pre-stored paths (just enter robot count)")
    print("  2) MANUAL – define each robot's path yourself")
    print("=" * 60)

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
#  Manual Mode (original behavior)
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
                f"Enter path for {robot_id} (comma-separated, e.g., A,B,G): "
            ).strip()
            path_list = [p.strip() for p in path_input.split(',') if p.strip()]

            if len(path_list) < 2:
                print("Path must have at least 2 nodes!")
                continue

            valid = True
            for j in range(len(path_list) - 1):
                n1, n2 = path_list[j], path_list[j + 1]
                if n1 not in gm.nodes:
                    print(f"Error: Node '{n1}' does not exist!")
                    valid = False
                    break
                if n2 not in gm.nodes:
                    print(f"Error: Node '{n2}' does not exist!")
                    valid = False
                    break
                if not gm.is_edge(n1, n2):
                    print(f"Error: No edge between '{n1}' and '{n2}'!")
                    valid = False
                    break

            if valid:
                robots_config.append({
                    'id': robot_id,
                    'color': color,
                    'path': path_input,
                    'speed': 0.5,
                    'radius': 1.5,
                })
                break
            else:
                print("Invalid path, please try again.")

    return robots_config


# ──────────────────────────────────────────────────────
#  Graph visual helpers
# ──────────────────────────────────────────────────────
def print_graph_visual():
    print("\n Graph Map (Approximate Layout):")
    print(" ---------------------------------")
    print(" Row 0:   A --- B --- C --- D --- E")
    print("          | \\ / | \\ / | \\ / | \\ / |")
    print(" Row 1:   F --- G --- H --- I --- J")
    print("          | / \\ | / \\ | / \\ | / \\ |")
    print(" Row 2:   K --- L --- M --- N --- O   (N = NodeN)")
    print("          | \\ / | \\ / | \\ / | \\ / |")
    print(" Row 3:   P --- Q --- R --- S --- T")
    print(" ---------------------------------\n")


def print_connections(gm):
    print("--- Available Graph Edges ---")
    connections = {}
    for start, end in gm.edges:
        connections.setdefault(start, []).append(end)
        connections.setdefault(end, []).append(start)
    for node in sorted(connections.keys()):
        connected = sorted(set(connections[node]))
        print(f"  Node {node:>5} connects to: {', '.join(connected)}")
    print("-----------------------------")


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

    return LaunchDescription([
        *robot_nodes,

        Node(
            package='robot_proximity',
            executable='proximity_monitor',
            name='proximity_monitor',
            parameters=[{{
                'threshold': 3.0,
                'robot_ids': ','.join(robot_ids)
            }}],
            output='screen'
        ),
        Node(
            package='robot_proximity',
            executable='graph_visualizer',
            name='graph_visualizer',
            output='screen'
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_config_dir],
            output='screen'
        )
    ])
"""


if __name__ == '__main__':
    main()
