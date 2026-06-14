import rclpy
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point
from std_msgs.msg import String
import random
from robot_proximity.graph_manager import GraphManager

class GraphVisualizer(Node):
    def __init__(self):
        super().__init__('graph_visualizer')
        self.get_logger().info("(OK) GraphVisualizer Node starting...")
        self.gm = GraphManager()
        self.marker_pub = self.create_publisher(MarkerArray, '/graph_markers', 10)
        self.obs_pub = self.create_publisher(String, '/dynamic_obstacles', 10)
        
        self.robot_cells = {}
        self.create_subscription(String, '/robot_cell_registry', self.cell_registry_cb, 10)
        
        self.create_timer(1.0, self.publish_graph)
        self.create_timer(8.0, self.spawn_obstacles) # New obstacles every 8 seconds
        self.get_logger().info("(OK) GraphVisualizer Node fully active. DYNAMIC OBSTACLES: ON (8s interval)")

    def cell_registry_cb(self, msg: String):
        parts = msg.data.split(':', 1)
        if len(parts) == 2:
            self.robot_cells[parts[0]] = parts[1].split(',')
            
    def spawn_obstacles(self):
        occupied = set()
        for cells in self.robot_cells.values():
            occupied.update(cells)
            
        possible = [n for n in self.gm.nodes.keys() if n not in occupied]
        num_obs = 15
        if len(possible) < num_obs:
            num_obs = len(possible)
            
        new_obs = random.sample(possible, num_obs) if possible else []
        
        msg = String()
        msg.data = ",".join(new_obs)
        self.obs_pub.publish(msg)
        
        self.gm.update_obstacles(new_obs)
        self.publish_graph()
        self.get_logger().info(f"Spawned {len(new_obs)} new dynamic obstacles! Avoiding occupied cells.")

    def publish_graph(self):
        markers = MarkerArray()
        cs = self.gm.cell_size
        mid = 0

        # ── 1. Ground plane (large flat cube behind everything) ──
        ground = Marker()
        ground.header.frame_id = "map"
        ground.header.stamp = self.get_clock().now().to_msg()
        ground.ns = "ground"
        ground.id = mid; mid += 1
        ground.type = Marker.CUBE
        ground.action = Marker.ADD
        # Center of the grid
        cx = (self.gm.num_cols - 1) * cs / 2.0
        cy = (self.gm.num_rows - 1) * cs / 2.0
        ground.pose.position.x = cx
        ground.pose.position.y = cy
        ground.pose.position.z = -0.15   # Deepest layer
        ground.scale.x = 40.0           # Much larger ground
        ground.scale.y = 40.0           # Much larger ground
        ground.scale.z = 0.02
        ground.color.r = 0.12
        ground.color.g = 0.14
        ground.color.b = 0.18
        ground.color.a = 1.0
        markers.markers.append(ground)

        # ── 2. Grid lines (thin white lines between cells) ──
        grid_lines = Marker()
        grid_lines.header.frame_id = "map"
        grid_lines.header.stamp = self.get_clock().now().to_msg()
        grid_lines.ns = "grid_lines"
        grid_lines.id = mid; mid += 1
        grid_lines.type = Marker.LINE_LIST
        grid_lines.action = Marker.ADD
        grid_lines.scale.x = 0.06   # Thicker lines
        grid_lines.color.r = 0.50   # Brighter lines
        grid_lines.color.g = 0.40
        grid_lines.color.b = 0.50
        grid_lines.color.a = 0.7

        # Horizontal grid lines
        x_min = -cs / 2.0
        x_max = (self.gm.num_cols - 1) * cs + cs / 2.0
        for r in range(self.gm.num_rows + 1):
            y_val = r * cs - cs / 2.0
            p1 = Point(); p1.x = x_min; p1.y = y_val; p1.z = -0.05
            p2 = Point(); p2.x = x_max; p2.y = y_val; p2.z = -0.05
            grid_lines.points.extend([p1, p2])

        # Vertical grid lines
        y_min = -cs / 2.0
        y_max = (self.gm.num_rows - 1) * cs + cs / 2.0
        for c in range(self.gm.num_cols + 1):
            x_val = c * cs - cs / 2.0
            p1 = Point(); p1.x = x_val; p1.y = y_min; p1.z = -0.05
            p2 = Point(); p2.x = x_val; p2.y = y_max; p2.z = -0.05
            grid_lines.points.extend([p1, p2])

        markers.markers.append(grid_lines)

        # ── 3. Individual cells ──
        for node_id, coords in self.gm.nodes.items():
            is_obs = self.gm.is_obstacle(node_id)

            # Cell fill cube
            cell = Marker()
            cell.header.frame_id = "map"
            cell.header.stamp = self.get_clock().now().to_msg()
            cell.ns = "grid_cells"
            cell.id = mid; mid += 1
            cell.type = Marker.CUBE
            cell.action = Marker.ADD
            cell.pose.position.x = coords[0]
            cell.pose.position.y = coords[1]

            if is_obs:
                # Obstacle: tall solid red block
                cell.pose.position.z = 0.4
                cell.scale.x = cs - 0.08
                cell.scale.y = cs - 0.08
                cell.scale.z = 0.8
                cell.color.r = 0.75
                cell.color.g = 0.1
                cell.color.b = 0.1
                cell.color.a = 0.95
            else:
                # Walkable: flat light tile
                cell.pose.position.z = -0.10   # Below lines, above ground
                cell.scale.x = cs - 0.08
                cell.scale.y = cs - 0.08
                cell.scale.z = 0.04
                cell.color.r = 0.20
                cell.color.g = 0.25
                cell.color.b = 0.32
                cell.color.a = 1.0   # Solid opacity for rows

            markers.markers.append(cell)

            # Label
            label = Marker()
            label.header.frame_id = "map"
            label.header.stamp = self.get_clock().now().to_msg()
            label.ns = "node_labels"
            label.id = mid; mid += 1
            label.type = Marker.TEXT_VIEW_FACING
            label.action = Marker.ADD
            label.pose.position.x = coords[0]
            label.pose.position.y = coords[1]
            label.scale.z = 0.45

            if is_obs:
                label.pose.position.z = 1.0
                label.color.r = 1.0
                label.color.g = 0.3
                label.color.b = 0.3
                label.color.a = 1.0
                label.text = node_id
            else:
                label.pose.position.z = 0.3
                label.color.r = 0.9
                label.color.g = 0.95
                label.color.b = 1.0
                label.color.a = 0.9
                label.text = node_id

            markers.markers.append(label)

        self.marker_pub.publish(markers)

def main(args=None):
    rclpy.init(args=args)
    node = GraphVisualizer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
