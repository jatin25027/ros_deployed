import rclpy
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray
from geometry_msgs.msg import Point
from robot_proximity.graph_manager import GraphManager

class GraphVisualizer(Node):
    def __init__(self):
        super().__init__('graph_visualizer')
        self.get_logger().info("(OK) GraphVisualizer Node starting...")
        self.gm = GraphManager()
        self.marker_pub = self.create_publisher(MarkerArray, '/graph_markers', 10)
        self.timer = self.create_timer(1.0, self.publish_graph)
        self.get_logger().info("(OK) GraphVisualizer Node fully active (publishing to /graph_markers)")

    def publish_graph(self):
        markers = MarkerArray()

        # Nodes Marker (Spheres)
        nodes_marker = Marker()
        nodes_marker.header.frame_id = "map"
        nodes_marker.header.stamp = self.get_clock().now().to_msg()
        nodes_marker.ns = "graph_nodes"
        nodes_marker.id = 0
        nodes_marker.type = Marker.SPHERE_LIST
        nodes_marker.action = Marker.ADD
        nodes_marker.scale.x = 0.1
        nodes_marker.scale.y = 0.1
        nodes_marker.scale.z = 0.1
        nodes_marker.color.r = 1.0
        nodes_marker.color.g = 1.0
        nodes_marker.color.b = 1.0
        nodes_marker.color.a = 0.8

        for node_id, coords in self.gm.nodes.items():
            p = Point()
            p.x = coords[0]
            p.y = coords[1]
            p.z = 0.05 # Slightly above 0
            nodes_marker.points.append(p)
            
            # Label Marker for each node
            label_marker = Marker()
            label_marker.header.frame_id = "map"
            label_marker.header.stamp = self.get_clock().now().to_msg()
            label_marker.ns = "node_labels"
            label_marker.id = abs(hash(node_id)) % 100000 # Handle multi-char IDs
            label_marker.type = Marker.TEXT_VIEW_FACING
            label_marker.action = Marker.ADD
            label_marker.pose.position.x = coords[0]
            label_marker.pose.position.y = coords[1]
            label_marker.pose.position.z = 0.3 # Floating slightly above
            label_marker.scale.z = 0.3 # Reasonable text height
            label_marker.color.r = 1.0
            label_marker.color.g = 1.0
            label_marker.color.b = 1.0
            label_marker.color.a = 1.0
            label_marker.text = node_id
            markers.markers.append(label_marker)

        markers.markers.append(nodes_marker)

        # Edges Marker (Line List)
        edges_marker = Marker()
        edges_marker.header.frame_id = "map"
        edges_marker.header.stamp = self.get_clock().now().to_msg()
        edges_marker.ns = "graph_edges"
        edges_marker.id = 1
        edges_marker.type = Marker.LINE_LIST
        edges_marker.action = Marker.ADD
        edges_marker.scale.x = 0.1 # line width
        edges_marker.color.r = 0.5
        edges_marker.color.g = 0.5
        edges_marker.color.b = 0.5
        edges_marker.color.a = 0.5

        for start_node, end_node in self.gm.edges:
            p1_coords = self.gm.get_coords(start_node)
            p2_coords = self.gm.get_coords(end_node)
            
            p1 = Point()
            p1.x = p1_coords[0]
            p1.y = p1_coords[1]
            p1.z = 0.0
            
            p2 = Point()
            p2.x = p2_coords[0]
            p2.y = p2_coords[1]
            p2.z = 0.0
            
            edges_marker.points.extend([p1, p2])

        markers.markers.append(edges_marker)
        self.marker_pub.publish(markers)

def main(args=None):
    rclpy.init(args=args)
    node = GraphVisualizer()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
