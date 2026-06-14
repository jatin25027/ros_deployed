import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Pose
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import String
from std_srvs.srv import Trigger
from robot_proximity.graph_manager import GraphManager
import math

# ---------------------------------------------------------------------------
# Deadlock timeout (seconds a robot waits before rerouting)
# ---------------------------------------------------------------------------
DEADLOCK_TIMEOUT   = 2.5
CELL_REGISTRY_TOPIC = '/robot_cell_registry'


# ---------------------------------------------------------------------------
# Quaternion helpers
# ---------------------------------------------------------------------------

def _quat_from_yaw(yaw):
    h = yaw / 2.0
    return (0.0, 0.0, math.sin(h), math.cos(h))


def _quat_from_rpy(roll, pitch, yaw):
    cr, sr = math.cos(roll  / 2), math.sin(roll  / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw   / 2), math.sin(yaw   / 2)
    return (sr*cp*cy - cr*sp*sy,
            cr*sp*cy + sr*cp*sy,
            cr*cp*sy - sr*sp*cy,
            cr*cp*cy + sr*sp*sy)


# ---------------------------------------------------------------------------
# RobotNode
# ---------------------------------------------------------------------------

class RobotNode(Node):

    def __init__(self):
        super().__init__('robot_node')

        # ── Parameters ──────────────────────────────────────────────────────
        self.declare_parameter('robot_id', 'robot1')
        self.declare_parameter('color',    'red')
        self.declare_parameter('path',     'A1,A2,A3')
        self.declare_parameter('speed',    0.8)
        self.declare_parameter('radius',   2.0)

        self.robot_id   = self.get_parameter('robot_id').get_parameter_value().string_value
        self.color_name = self.get_parameter('color').get_parameter_value().string_value
        path_raw        = self.get_parameter('path').get_parameter_value().string_value
        raw_waypoints   = [p.strip() for p in path_raw.split(',') if p.strip()]
        self.speed      = self.get_parameter('speed').get_parameter_value().double_value
        self.radius     = self.get_parameter('radius').get_parameter_value().double_value

        self.get_logger().info(
            f"[{self.robot_id}] STARTING — color={self.color_name} "
            f"raw_path={raw_waypoints}"
        )

        self.gm        = GraphManager()
        self.rgba      = self._get_rgba(self.color_name)

        # ── Resolve path ─────────────────────────────────────────────────────
        self.path        = self.gm.resolve_path(raw_waypoints)
        self._final_dest = self.path[-1] if self.path else None

        self.get_logger().info(
            f"[{self.robot_id}] Resolved path: {self.path}"
        )

        # ── Movement state ───────────────────────────────────────────────────
        self.current_edge_index = 0
        self.alpha              = 0.0
        self._frame_count       = 0
        self._current_yaw       = 0.0

        # ── Cell-collision avoidance ─────────────────────────────────────────
        self._cells_of_others  = {}
        self._waiting          = False
        self._wait_start_time  = None
        self._edge_started     = False
        self._reroute_count    = 0
        self._needs_reroute    = False

        # Last published XY (for refresh timer)
        self._last_x = None
        self._last_y = None

        # ── Publishers ──────────────────────────────────────────────────────
        qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                         history=HistoryPolicy.KEEP_LAST, depth=10)

        self.pose_pub   = self.create_publisher(Pose,        f'/{self.robot_id}/pose',    10)
        self.marker_pub = self.create_publisher(MarkerArray, f'/{self.robot_id}/markers', qos)
        self.cell_pub   = self.create_publisher(String,      CELL_REGISTRY_TOPIC,         10)

        self.get_logger().info(
            f"[{self.robot_id}] Publishing markers to: /{self.robot_id}/markers"
        )

        # ── Cell registry subscriber ─────────────────────────────────────────
        self.create_subscription(String, CELL_REGISTRY_TOPIC,
                                 self._cell_registry_cb, 10)
        self.create_subscription(String, '/dynamic_obstacles',
                                 self._dynamic_obs_cb, 10)

        # ── Service ──────────────────────────────────────────────────────────
        self.create_service(Trigger, f'/{self.robot_id}/communicate',
                            self._communication_cb)

        # ── Publish initial markers immediately ──────────────────────────────
        if self.path:
            start_coords = self.gm.get_coords(self.path[0])
            if start_coords:
                self._last_x, self._last_y = start_coords
                self._publish_cell(self.path[0])
                self._force_publish_markers(self._last_x, self._last_y)
                self.get_logger().info(
                    f"[{self.robot_id}] Initial markers published at "
                    f"({self._last_x:.2f}, {self._last_y:.2f})"
                )

        # ── Timers ───────────────────────────────────────────────────────────
        self.dt        = 0.02
        self.last_time = self.get_clock().now()
        self.create_timer(self.dt,  self._timer_cb)       # 50 Hz movement
        self.create_timer(0.33,  self._refresh_timer_cb)  # 3 Hz marker refresh

        self.get_logger().info(f"[{self.robot_id}] READY ✓")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Refresh timer — guarantees markers are always visible
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _refresh_timer_cb(self):
        if self._last_x is not None:
            self._force_publish_markers(self._last_x, self._last_y)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Cell registry
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _dynamic_obs_cb(self, msg: String):
        new_obs = [o.strip() for o in msg.data.split(',') if o.strip()]
        self.gm.update_obstacles(new_obs)
        self._needs_reroute = True

    def _cell_registry_cb(self, msg: String):
        try:
            parts = msg.data.split(':', 1)
            if len(parts) == 2 and parts[0] != self.robot_id:
                self._cells_of_others[parts[0]] = parts[1].split(',')
        except Exception:
            pass

    def _publish_cell(self, current_cell: str, next_cell: str = None):
        m = String()
        if next_cell and next_cell != current_cell:
            m.data = f"{self.robot_id}:{current_cell},{next_cell}"
        else:
            m.data = f"{self.robot_id}:{current_cell}"
        self.cell_pub.publish(m)

    def _is_cell_blocked(self, cell_name: str) -> bool:
        for claimed_cells in self._cells_of_others.values():
            if cell_name in claimed_cells:
                return True
        return False

    def _blocked_cells_set(self) -> set:
        blocked = set()
        for cells in self._cells_of_others.values():
            blocked.update(cells)
        return blocked

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Deadlock rerouting
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _reroute(self, force=False) -> bool:
        current_cell = self.path[self.current_edge_index]
        final_dest   = self._final_dest
        if current_cell == final_dest:
            self._waiting = False
            return True

        blocked = self._blocked_cells_set()
        blocked.discard(final_dest)
        blocked.discard(current_cell)

        if force:
            self.get_logger().warn(f"[{self.robot_id}] DYNAMIC OBSTACLE ahead! Rerouting '{current_cell}' -> '{final_dest}'")
        else:
            self.get_logger().warn(
                f"[{self.robot_id}] DEADLOCK — rerouting from '{current_cell}' to "
                f"'{final_dest}', avoiding {blocked}"
            )

        new_path = self.gm.find_path_excluding(current_cell, final_dest, blocked)
        if new_path and len(new_path) >= 1:
            self._reroute_count += 1
            self.path               = new_path
            self.current_edge_index = 0
            self.alpha              = 0.0
            self._edge_started      = False
            self._waiting           = False
            self._wait_start_time   = None
            self._publish_cell(current_cell)
            self.get_logger().info(
                f"[{self.robot_id}] Reroute #{self._reroute_count}: {' -> '.join(new_path)}"
            )
            return True

        self._wait_start_time = self.get_clock().now()
        self.get_logger().warn(f"[{self.robot_id}] No alternate path yet, retrying...")
        return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Communication service
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _communication_cb(self, request, response):
        self.get_logger().info(f"[{self.robot_id}] RECEIVED communication request!")
        response.success = True
        response.message = f"Hii this is {self.robot_id}"
        return response

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Movement timer (50 Hz)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _timer_cb(self):
        if len(self.path) < 2:
            return

        now = self.get_clock().now()
        dt  = (now - self.last_time).nanoseconds / 1e9
        self.last_time = now
        self._frame_count += 1
        if dt > 0.2:
            dt = 0.02

        # At destination
        if self.current_edge_index >= len(self.path) - 1:
            dest = self.path[-1]
            self._publish_cell(dest)
            self._publish_pose(self._last_x or 0.0, self._last_y or 0.0)
            return

        start_node = self.path[self.current_edge_index]
        end_node   = self.path[self.current_edge_index + 1]

        # Handle Dynamic Obstacle / Re-pathing before starting edge
        if not self._edge_started:
            if self._needs_reroute or self.gm.is_obstacle(end_node):
                self._needs_reroute = False
                self._reroute(force=True)
                return

        # Cell-collision check (only before starting a new edge)
        if not self._edge_started:
            if self._is_cell_blocked(end_node):
                if not self._waiting:
                    self._waiting = True
                    self._wait_start_time = now
                    self.get_logger().info(
                        f"[{self.robot_id}] WAITING at '{start_node}' "
                        f"— '{end_node}' is occupied."
                    )
                else:
                    secs = (now - self._wait_start_time).nanoseconds / 1e9
                    if secs >= DEADLOCK_TIMEOUT:
                        self._reroute()
                coords = self.gm.get_coords(start_node)
                if coords:
                    self._publish_cell(start_node)
                    self._publish_pose(*coords)
                    self._last_x, self._last_y = coords
                return
            else:
                if self._waiting:
                    self._waiting = False
                    self._wait_start_time = None
                    self.get_logger().info(
                        f"[{self.robot_id}] RESUMING — '{end_node}' is free."
                    )
                self._edge_started = True
                self._publish_cell(start_node, end_node)

        if not self.gm.is_edge(start_node, end_node):
            self.get_logger().error(f"[{self.robot_id}] Non-adjacent: {start_node}->{end_node}")
            self.current_edge_index += 1
            self.alpha = 0.0
            self._edge_started = False
            return

        p1   = self.gm.get_coords(start_node)
        p2   = self.gm.get_coords(end_node)
        dist = self.gm.get_distance(p1, p2)
        if dist == 0:
            self.current_edge_index += 1
            self.alpha = 0.0
            self._edge_started = False
            return

        self._current_yaw  = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
        self.alpha        += (self.speed * dt) / dist

        while self.alpha >= 1.0:
            self.alpha -= 1.0
            self.current_edge_index += 1
            self._edge_started = False

            if self.current_edge_index >= len(self.path) - 1:
                dest = self.path[-1]
                cx, cy = self.gm.get_coords(dest)
                self._publish_cell(dest)
                self._publish_pose(cx, cy)
                self._last_x, self._last_y = cx, cy
                self.get_logger().info(f"[{self.robot_id}] ARRIVED at {dest}")
                return

            start_node = self.path[self.current_edge_index]
            end_node   = self.path[self.current_edge_index + 1]
            p1 = self.gm.get_coords(start_node)
            p2 = self.gm.get_coords(end_node)
            dist = self.gm.get_distance(p1, p2)
            if not self.gm.is_edge(start_node, end_node):
                dist = 0.001
            elif dist == 0:
                dist = 0.001
            else:
                self._current_yaw = math.atan2(p2[1] - p1[1], p2[0] - p1[0])

            if not self._is_cell_blocked(end_node) and not self.gm.is_obstacle(end_node):
                self._edge_started = True
                self._publish_cell(start_node, end_node)
            else:
                self.alpha = 0.0
                self._waiting = True
                self._wait_start_time = self.get_clock().now()
                self._publish_cell(start_node)
                self.get_logger().info(
                    f"[{self.robot_id}] Mid-path WAITING at '{start_node}' "
                    f"— '{end_node}' occupied."
                )
                break

        cur  = self.path[self.current_edge_index]
        nxt  = self.path[min(self.current_edge_index + 1, len(self.path) - 1)]
        x, y = self.gm.interpolate(cur, nxt, self.alpha)
        self._publish_pose(x, y)
        self._last_x, self._last_y = x, y

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Marker publishing helpers
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _get_rgba(self, color_name):
        colors = {
            'red':     (1.0, 0.0, 0.0),
            'blue':    (0.0, 0.4, 1.0),
            'green':   (0.0, 0.9, 0.0),
            'purple':  (0.6, 0.0, 0.9),
            'orange':  (1.0, 0.5, 0.0),
            'cyan':    (0.0, 0.9, 0.9),
            'magenta': (0.9, 0.0, 0.6),
            'yellow':  (1.0, 1.0, 0.0),
            'teal':    (0.0, 0.6, 0.6),
            'white':   (1.0, 1.0, 1.0),
            'black':   (0.2, 0.2, 0.2),
        }
        return colors.get(color_name.lower(), (0.6, 0.6, 0.6))

    def _mk(self, ns, mid, mtype, ts):
        """Create a marker with correct header and infinite lifetime."""
        m = Marker()
        m.header.frame_id = 'map'
        m.header.stamp    = ts
        m.ns              = ns
        m.id              = mid
        m.type            = mtype
        m.action          = Marker.ADD
        # Lifetime 0 = INFINITE in ROS (never auto-delete)
        m.lifetime.sec    = 0
        m.lifetime.nanosec = 0
        m.pose.orientation.w = 1.0   # default: identity quaternion
        return m

    def _publish_pose(self, x: float, y: float):
        """Publish lightweight Pose (no markers)."""
        p = Pose()
        p.position.x = x
        p.position.y = y
        qx, qy, qz, qw = _quat_from_yaw(self._current_yaw)
        p.orientation.x = qx
        p.orientation.y = qy
        p.orientation.z = qz
        p.orientation.w = qw
        self.pose_pub.publish(p)

    def _force_publish_markers(self, x: float, y: float):
        """
        Publish the full TurtleBot3 Burger visualisation.
        Called from both the refresh timer (3 Hz) and mid-movement (25 Hz).
        Uses rate-limiting only for the mid-movement path; refresh timer always fires.
        """
        ts  = self.get_clock().now().to_msg()
        rid = self.robot_id
        yaw = self._current_yaw
        r, g, b = self.rgba

        ma = MarkerArray()

        # ── Robot colour state ───────────────────────────────────────────────
        body_a = 0.60 if self._waiting else 1.0   # dim when waiting

        # ── Quaternions ──────────────────────────────────────────────────────
        bqx, bqy, bqz, bqw = _quat_from_yaw(yaw)
        wqx, wqy, wqz, wqw = _quat_from_rpy(0.0, math.pi / 2.0, yaw)

        # ── TurtleBot3 Burger dimensions (×8 real-world for 2 m grid) ────────
        CR  = 0.65      # chassis radius        →  1.30 m diameter
        CH  = 0.50      # chassis height
        BR  = 0.58      # upper board radius
        BH  = 0.18      # board height
        WR  = 0.25      # wheel radius
        WW  = 0.18      # wheel width (thickness)
        CTR = 0.10      # caster ball radius
        LR  = 0.22      # LiDAR radius
        LH  = 0.28      # LiDAR height

        # ── 1. Chassis ───────────────────────────────────────────────────────
        c = self._mk(f'{rid}_chassis', 0, Marker.CYLINDER, ts)
        c.pose.position.x = x;  c.pose.position.y = y
        c.pose.position.z = CH / 2.0
        c.pose.orientation.x = bqx;  c.pose.orientation.y = bqy
        c.pose.orientation.z = bqz;  c.pose.orientation.w = bqw
        c.scale.x = CR*2;  c.scale.y = CR*2;  c.scale.z = CH
        c.color.r = r*0.75; c.color.g = g*0.75; c.color.b = b*0.75; c.color.a = body_a
        ma.markers.append(c)

        # ── 2. PCB / upper board ─────────────────────────────────────────────
        bd = self._mk(f'{rid}_board', 1, Marker.CYLINDER, ts)
        bd.pose.position.x = x;  bd.pose.position.y = y
        bd.pose.position.z = CH + BH / 2.0
        bd.pose.orientation.x = bqx;  bd.pose.orientation.y = bqy
        bd.pose.orientation.z = bqz;  bd.pose.orientation.w = bqw
        bd.scale.x = BR*2;  bd.scale.y = BR*2;  bd.scale.z = BH
        bd.color.r = 0.08; bd.color.g = 0.08; bd.color.b = 0.08; bd.color.a = 1.0
        ma.markers.append(bd)

        # ── 3 & 4. Drive wheels ──────────────────────────────────────────────
        for sign, wid, wns in [(+1, 2, f'{rid}_lwheel'), (-1, 3, f'{rid}_rwheel')]:
            wo_x = math.cos(yaw + sign * math.pi / 2) * (CR + WW / 2)
            wo_y = math.sin(yaw + sign * math.pi / 2) * (CR + WW / 2)
            w = self._mk(wns, wid, Marker.CYLINDER, ts)
            w.pose.position.x = x + wo_x;  w.pose.position.y = y + wo_y
            w.pose.position.z = WR
            w.pose.orientation.x = wqx;  w.pose.orientation.y = wqy
            w.pose.orientation.z = wqz;  w.pose.orientation.w = wqw
            w.scale.x = WR*2;  w.scale.y = WR*2;  w.scale.z = WW
            w.color.r = 0.1; w.color.g = 0.1; w.color.b = 0.1; w.color.a = 1.0
            ma.markers.append(w)

        # ── 5. Caster ball (front) ───────────────────────────────────────────
        co_x = math.cos(yaw) * (CR - CTR - 0.02)
        co_y = math.sin(yaw) * (CR - CTR - 0.02)
        ct = self._mk(f'{rid}_caster', 4, Marker.SPHERE, ts)
        ct.pose.position.x = x + co_x;  ct.pose.position.y = y + co_y
        ct.pose.position.z = CTR
        ct.scale.x = CTR*2;  ct.scale.y = CTR*2;  ct.scale.z = CTR*2
        ct.color.r = 0.65; ct.color.g = 0.65; ct.color.b = 0.65; ct.color.a = 1.0
        ma.markers.append(ct)

        # ── 6. LiDAR (grey cylinder on top) ─────────────────────────────────
        ld = self._mk(f'{rid}_lidar', 5, Marker.CYLINDER, ts)
        ld.pose.position.x = x;  ld.pose.position.y = y
        ld.pose.position.z = CH + BH + LH / 2.0
        ld.scale.x = LR*2;  ld.scale.y = LR*2;  ld.scale.z = LH
        ld.color.r = 0.85; ld.color.g = 0.85; ld.color.b = 0.85; ld.color.a = 1.0
        ma.markers.append(ld)

        # ── 7. LiDAR colour cap (team colour) ───────────────────────────────
        lc = self._mk(f'{rid}_lidar_cap', 6, Marker.CYLINDER, ts)
        lc.pose.position.x = x;  lc.pose.position.y = y
        lc.pose.position.z = CH + BH + LH + 0.008
        lc.scale.x = LR*2;  lc.scale.y = LR*2;  lc.scale.z = 0.06
        lc.color.r = r; lc.color.g = g; lc.color.b = b; lc.color.a = 1.0
        ma.markers.append(lc)

        # ── 8. Comm-range disk (semi-transparent) ────────────────────────────
        rng = self._mk(f'{rid}_range', 7, Marker.CYLINDER, ts)
        rng.pose.position.x = x;  rng.pose.position.y = y
        rng.pose.position.z = 0.01
        rng.scale.x = self.radius*2;  rng.scale.y = self.radius*2;  rng.scale.z = 0.01
        rng.color.r = r; rng.color.g = g; rng.color.b = b; rng.color.a = 0.15
        ma.markers.append(rng)

        # ── 9. Name label ────────────────────────────────────────────────────
        if self._waiting and self._wait_start_time:
            secs = (self.get_clock().now() - self._wait_start_time).nanoseconds / 1e9
            txt = f"{rid}  [WAIT {secs:.1f}s]"
        elif self._reroute_count > 0:
            txt = f"{rid}  [R#{self._reroute_count}]"
        else:
            txt = rid

        lb = self._mk(f'{rid}_label', 8, Marker.TEXT_VIEW_FACING, ts)
        lb.pose.position.x = x;  lb.pose.position.y = y
        lb.pose.position.z = CH + BH + LH + 0.55
        lb.scale.z  = 0.35
        lb.color.r  = 1.0;  lb.color.g = 1.0;  lb.color.b = 1.0;  lb.color.a = 1.0
        lb.text     = txt
        ma.markers.append(lb)

        self.marker_pub.publish(ma)

# ---------------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    node = RobotNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
