import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Pose
from visualization_msgs.msg import Marker, MarkerArray
from std_srvs.srv import Trigger
from robot_proximity.graph_manager import GraphManager


class RobotNode(Node):
    def __init__(self):
        super().__init__('robot_node')

        # Parameters
        self.declare_parameter('robot_id', 'robot1')
        self.declare_parameter('color', 'red')
        self.declare_parameter('path', 'A,B,C,D')
        self.declare_parameter('speed', 0.5)
        self.declare_parameter('radius', 1.5)

        self.robot_id = self.get_parameter('robot_id').get_parameter_value().string_value
        self.color_name = self.get_parameter('color').get_parameter_value().string_value
        path_raw = self.get_parameter('path').get_parameter_value().string_value
        self.path = [p.strip() for p in path_raw.split(',') if p.strip()]
        self.speed = self.get_parameter('speed').get_parameter_value().double_value
        self.radius = self.get_parameter('radius').get_parameter_value().double_value

        self.gm = GraphManager()
        self.current_edge_index = 0
        self.alpha = 0.0
        self._frame_count = 0

        # QoS with depth 10 to prevent message drops when many robots publish
        marker_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10
        )

        # Pose publisher (lightweight, high frequency ok)
        self.pose_pub = self.create_publisher(Pose, f'/{self.robot_id}/pose', 10)

        # Marker publisher - per-robot topic to avoid cross-robot message drops
        self.marker_pub = self.create_publisher(
            MarkerArray,
            f'/{self.robot_id}/markers',
            marker_qos
        )

        # Color mapping
        self.rgba = self.get_rgba(self.color_name)

        # Path validation
        self.validate_path()

        # Publish initial position IMMEDIATELY so robot is visible from start
        self.publish_current_pos(self.path[0], force_markers=True)

        # Service server
        self.srv = self.create_service(
            Trigger,
            f'/{self.robot_id}/communicate',
            self.communication_callback
        )

        # Timer for movement (50Hz for smooth interpolation)
        self.dt = 0.02  # 50Hz
        self.timer = self.create_timer(self.dt, self.timer_callback)
        self.last_time = self.get_clock().now()

        self.get_logger().info(
            f"Robot {self.robot_id} ({self.color_name}) ready on path {self.path}"
        )

    def communication_callback(self, request, response):
        self.get_logger().info(f"Robot {self.robot_id} RECEIVED communication request!")
        response.success = True
        response.message = f"Hii this is {self.robot_id}"
        return response

    def validate_path(self):
        """Check if the provided path follows the graph edges."""
        for i in range(len(self.path) - 1):
            n1 = self.path[i]
            n2 = self.path[i + 1]
            if not self.gm.is_edge(n1, n2):
                self.get_logger().error(
                    f"INVALID PATH: No edge between '{n1}' and '{n2}'!"
                )

    def get_rgba(self, color_name):
        colors = {
            'red':     (1.0, 0.0, 0.0, 1.0),
            'blue':    (0.0, 0.3, 1.0, 1.0),
            'green':   (0.0, 0.8, 0.0, 1.0),
            'purple':  (0.6, 0.0, 0.8, 1.0),
            'orange':  (1.0, 0.5, 0.0, 1.0),
            'cyan':    (0.0, 0.8, 0.8, 1.0),
            'magenta': (0.8, 0.0, 0.6, 1.0),
            'yellow':  (0.9, 0.9, 0.0, 1.0),
            'teal':    (0.0, 0.5, 0.5, 1.0),
            'white':   (1.0, 1.0, 1.0, 1.0),
            'black':   (0.0, 0.0, 0.0, 1.0),
        }
        return colors.get(color_name.lower(), (0.5, 0.5, 0.5, 1.0))

    def timer_callback(self):
        current_time = self.get_clock().now()
        dt = (current_time - self.last_time).nanoseconds / 1e9
        self.last_time = current_time
        self._frame_count += 1

        if dt > 0.2:
            dt = 0.02

        if self.current_edge_index >= len(self.path) - 1:
            self.publish_current_pos(self.path[-1])
            return

        start_node = self.path[self.current_edge_index]
        end_node = self.path[self.current_edge_index + 1]

        p1 = self.gm.get_coords(start_node)
        p2 = self.gm.get_coords(end_node)
        dist = self.gm.get_distance(p1, p2)

        if dist == 0:
            self.current_edge_index += 1
            return

        step = (self.speed * dt) / dist
        self.alpha += step

        while self.alpha >= 1.0:
            self.alpha -= 1.0
            self.current_edge_index += 1
            if self.current_edge_index >= len(self.path) - 1:
                self.get_logger().info(f"Robot {self.robot_id} reached the end.")
                self.publish_current_pos(self.path[-1])
                return

            start_node = self.path[self.current_edge_index]
            end_node = self.path[self.current_edge_index + 1]
            p1 = self.gm.get_coords(start_node)
            p2 = self.gm.get_coords(end_node)
            dist = self.gm.get_distance(p1, p2)
            if dist == 0:
                dist = 0.001

        x, y = self.gm.interpolate(start_node, end_node, self.alpha)
        self.publish_current_pos(x, y)

    def publish_current_pos(self, x_or_id, y=None, force_markers=False):
        if y is None:
            coords = self.gm.get_coords(x_or_id)
            if coords is None:
                self.get_logger().error(
                    f"Node '{x_or_id}' not found in GraphManager!"
                )
                return
            x, y = coords
        else:
            x = x_or_id

        # Always publish pose (lightweight)
        msg = Pose()
        msg.position.x = x
        msg.position.y = y
        self.pose_pub.publish(msg)

        # Publish markers at ~25Hz (every 2nd frame) to reduce RViz load
        # Always publish on first call (force_markers) for instant visibility
        if not force_markers and self._frame_count % 2 != 0:
            return

        marker_array = MarkerArray()
        timestamp = self.get_clock().now().to_msg()

        # Body Marker (Sphere)
        body_marker = Marker()
        body_marker.header.frame_id = "map"
        body_marker.header.stamp = timestamp
        body_marker.ns = self.robot_id
        body_marker.id = 0
        body_marker.type = Marker.SPHERE
        body_marker.action = Marker.ADD
        body_marker.lifetime = rclpy.duration.Duration().to_msg()
        body_marker.pose.position.x = x
        body_marker.pose.position.y = y
        body_marker.pose.position.z = 0.3
        body_marker.scale.x = 0.6
        body_marker.scale.y = 0.6
        body_marker.scale.z = 0.6
        body_marker.color.r = self.rgba[0]
        body_marker.color.g = self.rgba[1]
        body_marker.color.b = self.rgba[2]
        body_marker.color.a = 1.0
        marker_array.markers.append(body_marker)

        # Range Marker (Disk)
        range_marker = Marker()
        range_marker.header.frame_id = "map"
        range_marker.header.stamp = timestamp
        range_marker.ns = f"{self.robot_id}_range_ns"
        range_marker.id = 1
        range_marker.type = Marker.CYLINDER
        range_marker.action = Marker.ADD
        range_marker.lifetime = rclpy.duration.Duration().to_msg()
        range_marker.pose.position.x = x
        range_marker.pose.position.y = y
        range_marker.pose.position.z = 0.01
        range_marker.scale.x = self.radius * 2.0
        range_marker.scale.y = self.radius * 2.0
        range_marker.scale.z = 0.05
        range_marker.color.r = self.rgba[0]
        range_marker.color.g = self.rgba[1]
        range_marker.color.b = self.rgba[2]
        range_marker.color.a = 0.2
        marker_array.markers.append(range_marker)

        # Text label above robot
        text_marker = Marker()
        text_marker.header.frame_id = "map"
        text_marker.header.stamp = timestamp
        text_marker.ns = f"{self.robot_id}_label"
        text_marker.id = 2
        text_marker.type = Marker.TEXT_VIEW_FACING
        text_marker.action = Marker.ADD
        text_marker.lifetime = rclpy.duration.Duration().to_msg()
        text_marker.pose.position.x = x
        text_marker.pose.position.y = y
        text_marker.pose.position.z = 0.8
        text_marker.scale.z = 0.3
        text_marker.color.r = 1.0
        text_marker.color.g = 1.0
        text_marker.color.b = 1.0
        text_marker.color.a = 1.0
        text_marker.text = self.robot_id
        marker_array.markers.append(text_marker)

        self.marker_pub.publish(marker_array)


def main(args=None):
    rclpy.init(args=args)
    node = RobotNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
