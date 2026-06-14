import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from geometry_msgs.msg import Pose
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import String
from std_srvs.srv import Trigger
from robot_proximity.graph_manager import GraphManager
import math
from enum import Enum

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEADLOCK_TIMEOUT   = 2.5
CELL_REGISTRY_TOPIC = '/robot_cell_registry'

class FlightState(Enum):
    LANDED      = 0
    TAKING_OFF  = 1
    FLYING      = 2
    LANDING     = 3

# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def angle_diff(target, current):
    diff = (target - current) % (2.0 * math.pi)
    if diff > math.pi:
        diff -= 2.0 * math.pi
    return diff

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
        self.declare_parameter('speed',    0.4)
        self.declare_parameter('radius',   2.0)

        self.robot_id   = self.get_parameter('robot_id').get_parameter_value().string_value
        self.color_name = self.get_parameter('color').get_parameter_value().string_value
        path_raw        = self.get_parameter('path').get_parameter_value().string_value
        raw_waypoints   = [p.strip() for p in path_raw.split(',') if p.strip()]
        self.speed      = self.get_parameter('speed').get_parameter_value().double_value
        self.radius     = self.get_parameter('radius').get_parameter_value().double_value

        self.get_logger().info(
            f"[{self.robot_id}] STARTING (Physical Quadcopter) — color={self.color_name} "
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

        # ── 3D Movement state ────────────────────────────────────────────────
        self.current_edge_index = 0
        self.alpha              = 0.0
        self._frame_count       = 0
        self._current_yaw       = 0.0
        
        # True physics position & velocity
        self.x                  = None
        self.y                  = None
        self.vx                 = 0.0
        self.vy                 = 0.0
        self.rabbit_x           = None
        self.rabbit_y           = None
        
        # Flight dynamics
        self.state          = FlightState.LANDED
        self.z              = 0.0
        self.roll           = 0.0
        self.pitch          = 0.0
        self.roll_vel       = 0.0
        self.pitch_vel      = 0.0
        self.yaw_vel        = 0.0
        
        self.target_pitch   = 0.0
        self.target_roll    = 0.0
        self.target_yaw     = 0.0
        self.prop_angle     = 0.0
        
        self.target_z       = 1.2   # Target flight altitude (m)
        self.v_z            = 0.6   # Climb/descend speed (m/s)
        self.tilt_max       = 0.15  # Max tilt in radians (approx 8.5 degrees)
        self.tilt_speed     = 0.05  # How fast the tilt changes
        
        self.hover_drift_z  = 0.0
        self.hover_time     = 0.0

        # ── Cell-collision avoidance ─────────────────────────────────────────
        self._cells_of_others  = {}
        self._waiting          = False
        self._wait_start_time  = None
        self._edge_started     = False
        self._reroute_count    = 0
        self._needs_reroute    = False
        
        # Reactive collision avoidance (Distance-based)
        self._poses_of_others     = {}
        self._other_pose_subs      = {}
        self._safety_distance      = 2.5
        self._is_yielding          = False
        self._yield_target_id      = None

        # Last published XYZ (for markers)
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

        # ── Start initial position ─────────────────────────────
        if self.path:
            start_coords = self.gm.get_coords(self.path[0])
            if start_coords:
                self.x, self.y = start_coords
                self.rabbit_x, self.rabbit_y = start_coords
                self._last_x, self._last_y = start_coords
                self._publish_cell(self.path[0])
                self._force_publish_markers(self.x, self.y)

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
        if self.x is not None:
            self._force_publish_markers(self.x, self.y)

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
            if len(parts) == 2:
                other_id = parts[0]
                if other_id != self.robot_id:
                    self._cells_of_others[other_id] = parts[1].split(',')
                    
                    # Discover and subscribe to new robots' poses
                    if other_id not in self._other_pose_subs:
                        self.get_logger().info(f"[{self.robot_id}] Discovered {other_id}, subscribing to pose...")
                        self._other_pose_subs[other_id] = self.create_subscription(
                            Pose,
                            f'/{other_id}/pose',
                            lambda m, rid=other_id: self._other_pose_cb(m, rid),
                            10
                        )
        except Exception:
            pass

    def _other_pose_cb(self, msg: Pose, robot_id: str):
        self._poses_of_others[robot_id] = msg.position

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
            
        # ── Hover Bobbing ──────────────
        self.hover_time += dt
        if self.state in [FlightState.FLYING, FlightState.TAKING_OFF, FlightState.LANDING]:
            self.hover_drift_z = 0.05 * math.sin(self.hover_time * 2.5)
        else:
            self.hover_drift_z = 0.0
            
        # ── 1. Flight State Transitions & Z-Control ─────────────────────────
        if self.state == FlightState.LANDED:
            # If we have a path and are ready to move, takeoff first
            if self.current_edge_index < len(self.path) - 1:
                self.state = FlightState.TAKING_OFF
                self.get_logger().info(f"[{self.robot_id}] TAKING OFF...")
                
        elif self.state == FlightState.TAKING_OFF:
            self.z += self.v_z * dt
            self.prop_angle += 15.0 * dt  # Spin props during takeoff
            if self.z >= self.target_z:
                self.z = self.target_z
                self.state = FlightState.FLYING
                self.get_logger().info(f"[{self.robot_id}] AIRBORNE - Target altitude reached.")
                
        elif self.state == FlightState.LANDING:
            self.z -= self.v_z * dt
            self.prop_angle += 10.0 * dt  # Spin props slower during landing
            # Reset tilt smoothly
            self.pitch *= 0.8
            self.roll  *= 0.8
            if self.z <= 0.0:
                self.z = 0.0
                self.state = FlightState.LANDED
                self.get_logger().info(f"[{self.robot_id}] LANDED.")
                
        elif self.state == FlightState.FLYING:
            self.prop_angle += 20.0 * dt # Spin fast during flight

        # ── 2. Horizontal Movement (Only when FLYING) ──────────────────────
        if self.state == FlightState.FLYING:
            if self.current_edge_index >= len(self.path) - 1:
                # Arrived at final destination, initiate landing
                self.state = FlightState.LANDING
                self.get_logger().info(f"[{self.robot_id}] ARRIVED - Initiating Vertical Landing.")
                return

            start_node = self.path[self.current_edge_index]
            end_node   = self.path[self.current_edge_index + 1]

            # ── 3. Reactive Distance-Based Collision Avoidance ──────────────────
            self._is_yielding = False
            self._yield_target_id = None
            
            # Simple Priority: Extract number from "robotN"
            def get_id_num(rid):
                try: return int(''.join(filter(str.isdigit, rid)))
                except: return 999
            
            my_num = get_id_num(self.robot_id)
            
            for other_id, other_pos in self._poses_of_others.items():
                if other_pos is None: continue
                
                # Check distance in 3D (including altitude)
                dx = other_pos.x - self._last_x
                dy = other_pos.y - self._last_y
                dz = other_pos.z - self.z
                dist = math.sqrt(dx*dx + dy*dy + dz*dz)
                
                if dist < self._safety_distance:
                    other_num = get_id_num(other_id)
                    # YIELD IF: Other has HIGHER priority (lower numerical ID)
                    # OR if they have the same ID (shouldn't happen)
                    if other_num < my_num:
                        self._is_yielding = True
                        self._yield_target_id = other_id
                        break
            
            if self._is_yielding:
                # Hover in place while yielding
                self.pitch *= 0.8; self.roll *= 0.8  # Level out
                if self._frame_count % 100 == 0:
                    self.get_logger().warn(f"[{self.robot_id}] YIELDING to {self._yield_target_id} (dist={dist:.2f}m)")
                return

            # Handle obstacles/deadlocks
            if not self._edge_started:
                if self._needs_reroute or self.gm.is_obstacle(end_node):
                    self._needs_reroute = False
                    self._reroute(force=True)
                    return

            # Cell-collision check
            if not self._edge_started:
                if self._is_cell_blocked(end_node):
                    if not self._waiting:
                        self._waiting = True
                        self._wait_start_time = now
                    else:
                        secs = (now - self._wait_start_time).nanoseconds / 1e9
                        if secs >= DEADLOCK_TIMEOUT:
                            self._reroute()
                    # Hover in place at current node while waiting
                    coords = self.gm.get_coords(start_node)
                    if coords:
                        self._publish_cell(start_node)
                        self._publish_pose(*coords)
                        self._last_x, self._last_y = coords
                    # Smoothly reset tilt while waiting
                    self.pitch *= 0.9; self.roll *= 0.9
                    return
                else:
                    if self._waiting:
                        self._waiting = False
                        self._wait_start_time = None
                    self._edge_started = True
                    self._publish_cell(start_node, end_node)

            p1   = self.gm.get_coords(start_node)
            p2   = self.gm.get_coords(end_node)
            dist = self.gm.get_distance(p1, p2)
            if dist == 0:
                self.current_edge_index += 1
                self.alpha = 0.0
                self._edge_started = False
                return

            # ── 4. Virtual Rabbit Target Advancement ──
            self.alpha += (self.speed * dt) / dist

            while self.alpha >= 1.0:
                self.alpha -= 1.0
                self.current_edge_index += 1
                self._edge_started = False

                if self.current_edge_index >= len(self.path) - 1:
                    dest = self.path[-1]
                    self.rabbit_x, self.rabbit_y = self.gm.get_coords(dest)
                    self._publish_cell(dest)
                    break

                start_node = self.path[self.current_edge_index]
                end_node   = self.path[self.current_edge_index + 1]
                p1 = self.gm.get_coords(start_node)
                p2 = self.gm.get_coords(end_node)
                dist = self.gm.get_distance(p1, p2)
                if dist == 0:
                    dist = 0.001

                if not self._is_cell_blocked(end_node) and not self.gm.is_obstacle(end_node):
                    self._edge_started = True
                    self._publish_cell(start_node, end_node)
                else:
                    self.alpha = 0.0
                    self._waiting = True
                    self._wait_start_time = self.get_clock().now()
                    self._publish_cell(start_node)
                    break

            if self.current_edge_index < len(self.path) - 1:
                cur  = self.path[self.current_edge_index]
                nxt  = self.path[self.current_edge_index + 1]
                rx, ry = self.gm.interpolate(cur, nxt, self.alpha)
                self.rabbit_x, self.rabbit_y = rx, ry
            else:
                dest = self.path[-1]
                self.rabbit_x, self.rabbit_y = self.gm.get_coords(dest)

            # Check if drone physically arrived
            drone_dist_to_final = math.sqrt((self.rabbit_x - self.x)**2 + (self.rabbit_y - self.y)**2)
            if self.current_edge_index >= len(self.path) - 1 and drone_dist_to_final < 0.15 and self.alpha >= 0.0:
                self.state = FlightState.LANDING
                self.get_logger().info(f"[{self.robot_id}] PHYSICALLY ARRIVED - Initiating Vertical Landing.")
                return

            # ── 5. Proportional-Derivative (PD) Physics Engine ──
            err_x = self.rabbit_x - self.x
            err_y = self.rabbit_y - self.y
            
            if self.current_edge_index < len(self.path) - 1:
                cur  = self.path[self.current_edge_index]
                nxt  = self.path[self.current_edge_index + 1]
                p1 = self.gm.get_coords(cur)
                p2 = self.gm.get_coords(nxt)
                ddx = p2[0] - p1[0]
                ddy = p2[1] - p1[1]
                ln = math.sqrt(ddx*ddx + ddy*ddy)
                rabbit_vx = (ddx / ln) * self.speed if ln > 0 else 0
                rabbit_vy = (ddy / ln) * self.speed if ln > 0 else 0
            else:
                rabbit_vx = 0.0
                rabbit_vy = 0.0
                
            kp = 3.5
            kd = 2.0
            ax = kp * err_x + kd * (rabbit_vx - self.vx)
            ay = kp * err_y + kd * (rabbit_vy - self.vy)
            
            self.vx += ax * dt
            self.vy += ay * dt
            
            # Cornering limit
            cur_speed = math.sqrt(self.vx**2 + self.vy**2)
            if cur_speed > self.speed * 1.5:
                self.vx = (self.vx / cur_speed) * (self.speed * 1.5)
                self.vy = (self.vy / cur_speed) * (self.speed * 1.5)
                
            self.x += self.vx * dt
            self.y += self.vy * dt
            
            # ── 6. Flight Dynamics & Tilt ──
            if cur_speed > 0.1:
                self.target_yaw = math.atan2(self.vy, self.vx)
                
            yaw_diff = angle_diff(self.target_yaw, self._current_yaw)
            yaw_spring = 15.0
            yaw_damp = 5.0
            yaw_accel = yaw_diff * yaw_spring - self.yaw_vel * yaw_damp
            self.yaw_vel += yaw_accel * dt
            self.yaw_vel = max(-3.0, min(3.0, self.yaw_vel))
            self._current_yaw += self.yaw_vel * dt
            
            # World to Body Accelerations
            cos_y = math.cos(self._current_yaw)
            sin_y = math.sin(self._current_yaw)
            body_ax = ax * cos_y + ay * sin_y
            body_ay = -ax * sin_y + ay * cos_y
            
            # Tilt is mapped to body_ax and body_ay
            g = 9.81
            self.target_pitch = math.atan2(body_ax, g) * 1.5
            self.target_roll  = -math.atan2(body_ay, g) * 1.5
            
            # Spring dampen tilt
            tilt_spring = 40.0
            tilt_damp = 8.0
            self.pitch_vel += ((self.target_pitch - self.pitch) * tilt_spring - self.pitch_vel * tilt_damp) * dt
            self.pitch += self.pitch_vel * dt
            self.roll_vel += ((self.target_roll - self.roll) * tilt_spring - self.roll_vel * tilt_damp) * dt
            self.roll += self.roll_vel * dt
            
            self._last_x, self._last_y = self.x, self.y
            self._publish_pose(self.x, self.y)
        else:
            # Landing or Taking Off or Landed
            if self.x is not None:
                self._last_x, self._last_y = self.x, self.y
                self._publish_pose(self.x, self.y)

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
        m = Marker()
        m.header.frame_id = 'map'
        m.header.stamp    = ts
        m.ns              = ns
        m.id              = mid
        m.type            = mtype
        m.action          = Marker.ADD
        m.lifetime.sec    = 0
        m.lifetime.nanosec = 0
        m.pose.orientation.w = 1.0
        return m

    def _publish_pose(self, x: float, y: float):
        p = Pose()
        p.position.x = x
        p.position.y = y
        p.position.z = self.z + self.hover_drift_z
        # Orient the main pose with yaw + pitch/roll tilt
        qx, qy, qz, qw = _quat_from_rpy(self.roll, self.pitch, self._current_yaw)
        p.orientation.x = qx
        p.orientation.y = qy
        p.orientation.z = qz
        p.orientation.w = qw
        self.pose_pub.publish(p)

    def _force_publish_markers(self, x: float, y: float):
        ts  = self.get_clock().now().to_msg()
        rid = self.robot_id
        yaw = self._current_yaw
        r, g, b = self.rgba

        ma = MarkerArray()

        # ── Visual dimensions ───────────────────────
        BODY_LX = 0.50
        BODY_LY = 0.50
        BODY_LZ = 0.16
        ARM_L   = 1.10
        ARM_R   = 0.07
        PROP_R  = 0.35
        PROP_H  = 0.02
        MOTOR_R = 0.10
        MOTOR_H = 0.15

        # Dim when waiting or landed
        body_a = 0.65 if self._waiting else 1.0
        prop_a = 0.3 if self.state == FlightState.FLYING else (0.6 if self.state in [FlightState.TAKING_OFF, FlightState.LANDING] else 0.9)


        # Overall orientation (Yaw + Pitch/Roll Tilt)
        bqx, bqy, bqz, bqw = _quat_from_rpy(self.roll, self.pitch, yaw)

        # ── 1. Central fuselage (CUBE) ──────────────────────────────────
        bd = self._mk(f'{rid}_body', 0, Marker.CUBE, ts)
        bd.pose.position.x = x; bd.pose.position.y = y; bd.pose.position.z = self.z + self.hover_drift_z
        bd.pose.orientation.x = bqx; bd.pose.orientation.y = bqy
        bd.pose.orientation.z = bqz; bd.pose.orientation.w = bqw
        bd.scale.x = BODY_LX; bd.scale.y = BODY_LY; bd.scale.z = BODY_LZ
        bd.color.r = r * 0.8; bd.color.g = g * 0.8; bd.color.b = b * 0.8; bd.color.a = body_a
        ma.markers.append(bd)

        # ── 2 & 3. Arms (CYLINDERs) ─────────────────────────────────────
        # Fore-aft arm
        faqx, faqy, faqz, faqw = _quat_from_rpy(self.roll, self.pitch + math.pi/2.0, yaw)
        fa = self._mk(f'{rid}_arm_fwd', 1, Marker.CYLINDER, ts)
        fa.pose.position.x = x; fa.pose.position.y = y; fa.pose.position.z = self.z + self.hover_drift_z + 0.05
        fa.pose.orientation.x = faqx; fa.pose.orientation.y = faqy
        fa.pose.orientation.z = faqz; fa.pose.orientation.w = faqw
        fa.scale.x = ARM_R*2; fa.scale.y = ARM_R*2; fa.scale.z = ARM_L
        fa.color.r = 0.15; fa.color.g = 0.15; fa.color.b = 0.15; fa.color.a = body_a
        ma.markers.append(fa)

        # Lateral arm
        laqx, laqy, laqz, laqw = _quat_from_rpy(self.roll, self.pitch + math.pi/2.0, yaw + math.pi/2.0)
        la = self._mk(f'{rid}_arm_lat', 2, Marker.CYLINDER, ts)
        la.pose.position.x = x; la.pose.position.y = y; la.pose.position.z = self.z + self.hover_drift_z + 0.05
        la.pose.orientation.x = laqx; la.pose.orientation.y = laqy
        la.pose.orientation.z = laqz; la.pose.orientation.w = laqw
        la.scale.x = ARM_R*2; la.scale.y = ARM_R*2; la.scale.z = ARM_L
        la.color.r = 0.15; la.color.g = 0.15; la.color.b = 0.15; la.color.a = body_a
        ma.markers.append(la)

        # ── 4–7. Four Propeller Discs (Animate with self.prop_angle) ────
        half = ARM_L / 2.0
        props = [
            ('FL', +1, +1, 3), ('FR', +1, -1, 4),
            ('RL', -1, +1, 5), ('RR', -1, -1, 6),
        ]
        
        # Propeller rotation math:
        # 1. Take global pose (x,y,z + bqx,y,z,w)
        # 2. Add local offset in rotated frame
        # 3. Apply spinning rotation (around local Z)
        
        for label, sf, sl, pid in props:
            # local offset in robot frame (before tilt)
            lx = sf * half
            ly = sl * half
            lz = 0.12
            
            # Apply tilt & yaw to local offset
            cos_y = math.cos(yaw); sin_y = math.sin(yaw)
            # Simple rotation (treating it as relatively stiff)
            ox = (lx * cos_y - ly * sin_y)
            oy = (lx * sin_y + ly * cos_y)
            
            # ── Motor cylinder ──
            mt = self._mk(f'{rid}_motor_{label}', pid + 10, Marker.CYLINDER, ts)
            mt.pose.position.x = x + ox
            mt.pose.position.y = y + oy
            mt.pose.position.z = self.z + self.hover_drift_z + lz - 0.05
            
            mqx, mqy, mqz, mqw = _quat_from_rpy(self.roll, self.pitch, yaw)
            mt.pose.orientation.x = mqx
            mt.pose.orientation.y = mqy
            mt.pose.orientation.z = mqz
            mt.pose.orientation.w = mqw
            
            mt.scale.x = MOTOR_R*2; mt.scale.y = MOTOR_R*2; mt.scale.z = MOTOR_H
            mt.color.r = 0.2; mt.color.g = 0.2; mt.color.b = 0.2; mt.color.a = body_a
            ma.markers.append(mt)
            
            # ── Propeller ──
            pr = self._mk(f'{rid}_prop_{label}', pid, Marker.CYLINDER, ts)
            pr.pose.position.x = x + ox
            pr.pose.position.y = y + oy
            pr.pose.position.z = self.z + self.hover_drift_z + lz
            
            # Spin animation: rotate propeller around Z based on prop_angle
            # and robot's tilt orientation
            pqx, pqy, pqz, pqw = _quat_from_rpy(self.roll, self.pitch, yaw + self.prop_angle * (1 if sf*sl > 0 else -1))
            pr.pose.orientation.x = pqx
            pr.pose.orientation.y = pqy
            pr.pose.orientation.z = pqz
            pr.pose.orientation.w = pqw
            
            pr.scale.x = PROP_R*2; pr.scale.y = PROP_R*2; pr.scale.z = PROP_H
            pr.color.r = r; pr.color.g = g; pr.color.b = b; pr.color.a = prop_a * body_a
            ma.markers.append(pr)

        # ── 8. Comm-range disk ───────────────────
        rng = self._mk(f'{rid}_range', 7, Marker.CYLINDER, ts)
        rng.pose.position.x = x; rng.pose.position.y = y; rng.pose.position.z = 0.01
        rng.scale.x = self.radius*2; rng.scale.y = self.radius*2; rng.scale.z = 0.01
        rng.color.r = r; rng.color.g = g; rng.color.b = b; rng.color.a = 0.15
        ma.markers.append(rng)

        # ── 9. Name label ────────────────────────
        txt = rid
        if self.state == FlightState.TAKING_OFF: txt += " [TAKEOFF]"
        elif self.state == FlightState.LANDING:  txt += " [LANDING]"
        elif self._is_yielding:                  txt += f" [YIELD -> {self._yield_target_id}]"
        elif self._waiting:                      txt += " [WAITING]"
        elif self.state == FlightState.FLYING:   txt += " [CRUISE]"

        lb = self._mk(f'{rid}_label', 8, Marker.TEXT_VIEW_FACING, ts)
        lb.pose.position.x = x; lb.pose.position.y = y; lb.pose.position.z = self.z + 0.8
        lb.scale.z = 0.35
        lb.color.r = 1.0; lb.color.g = 1.0; lb.color.b = 1.0; lb.color.a = 1.0
        lb.text = txt
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
