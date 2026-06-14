import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    pkg_dir = get_package_share_directory('robot_proximity')
    rviz_config_dir = os.path.join(pkg_dir, 'config', 'simulation.rviz')

    # Define robots
    robots = [
        {'id': 'robot1', 'color': 'red', 'path': 'A,B,G,L,M,R,S', 'speed': 0.5, 'radius': 1.5},
        {'id': 'robot2', 'color': 'blue', 'path': 'P,K,F,A,B,G,H,I,D', 'speed': 0.5, 'radius': 1.5},
        {'id': 'robot3', 'color': 'green', 'path': 'T,S,R,Q,L,M,H,C,D', 'speed': 0.5, 'radius': 1.5},
        {'id': 'robot4', 'color': 'purple', 'path': 'E,J,O,NodeN,M,G,B,A', 'speed': 0.5, 'radius': 1.5}
    ]

    robot_nodes = []
    robot_ids = []

    for r in robots:
        robot_ids.append(r['id'])
        robot_nodes.append(
            Node(
                package='robot_proximity',
                executable='robot_node',
                name=r['id'],
                parameters=[{
                    'robot_id': r['id'],
                    'color': r['color'],
                    'path': r['path'],
                    'speed': r['speed'],
                    'radius': r['radius']
                }],
                output='screen',
                emulate_tty=True
            )
        )

    return LaunchDescription([
        *robot_nodes,

        Node(
            package='robot_proximity',
            executable='proximity_monitor',
            name='proximity_monitor',
            parameters=[{
                'threshold': 3.0,
                'robot_ids': ','.join(robot_ids)
            }],
            output='screen',
            emulate_tty=True
        ),
        Node(
            package='robot_proximity',
            executable='graph_visualizer',
            name='graph_visualizer',
            output='screen',
            emulate_tty=True
        ),
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            arguments=['-d', rviz_config_dir],
            output='screen'
        )
    ])
