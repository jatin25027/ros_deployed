from setuptools import find_packages, setup

package_name = 'robot_proximity'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/simulation.launch.py']),
        ('share/' + package_name + '/config', ['config/simulation.rviz']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jatin',
    maintainer_email='jatin@todo.todo',
    description='Robot proximity communication system',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'robot_node = robot_proximity.robot_node:main',
            'proximity_monitor = robot_proximity.proximity_monitor:main',
            'graph_visualizer = robot_proximity.graph_visualizer:main',
            'interactive_runner = robot_proximity.interactive_runner:main',
        ],
    },
)
