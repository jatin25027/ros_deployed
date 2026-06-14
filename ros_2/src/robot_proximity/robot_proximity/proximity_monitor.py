import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose
from std_srvs.srv import Trigger
import math
from functools import partial

# ─────────────────────────────────────────────
#  Formatted printing helpers
# ─────────────────────────────────────────────
LINE_W = 60

def _box_top():
    return "+" + "-" * LINE_W + "+"

def _box_bot():
    return "+" + "-" * LINE_W + "+"

def _box_mid():
    return "|" + "-" * LINE_W + "|"

def _box_line(text=""):
    text = str(text)
    if len(text) > LINE_W - 2:
        text = text[:LINE_W - 5] + "..."
    return "| " + text.ljust(LINE_W - 2) + " |"


class ProximityMonitor(Node):
    def __init__(self):
        # Initialize state BEFORE calling super().__init__()
        self.poses = {}
        self.comm_clients = {}
        self.last_comm_time = {}
        self.threshold = 10.0
        self.robot_ids = []
        self.comm_cooldown = 1.0
        self.interaction_count = 0

        super().__init__('proximity_monitor')
        self.get_logger().info("PROXIMITY MONITOR STARTING")

        try:
            self.declare_parameter('threshold', 10.0)
            self.declare_parameter('robot_ids', 'robot1,robot2,robot3,robot4')

            self.threshold = float(self.get_parameter('threshold').value)
            ids_val = self.get_parameter('robot_ids').value

            if isinstance(ids_val, list):
                self.robot_ids = [str(rid).strip() for rid in ids_val]
            else:
                self.robot_ids = [rid.strip() for rid in str(ids_val).split(',') if rid.strip()]

            self.get_logger().info(f"Tracking: {self.robot_ids}  |  Threshold: {self.threshold}")

            for rid in self.robot_ids:
                self.poses[rid] = None
                self.create_subscription(
                    Pose,
                    f'/{rid}/pose',
                    partial(self.pose_callback, robot_id=rid),
                    10
                )
                self.comm_clients[rid] = self.create_client(Trigger, f'/{rid}/communicate')

            self.create_timer(0.2, self.check_proximity)
            self.get_logger().info("PROXIMITY MONITOR READY")

        except Exception as e:
            self.get_logger().error(f"INIT ERROR: {e}")

    def pose_callback(self, msg, robot_id):
        self.poses[robot_id] = msg.position

    def check_proximity(self):
        try:
            active = {rid: p for rid, p in self.poses.items() if p is not None}

            if not hasattr(self, '_loop_cnt'):
                self._loop_cnt = 0
            self._loop_cnt += 1
            if self._loop_cnt % 25 == 0:
                self.get_logger().info(f"[HEARTBEAT] Active robots: {list(active.keys())}")

            if len(active) < 2:
                return

            robot_list = list(active.keys())
            for i in range(len(robot_list)):
                for j in range(i + 1, len(robot_list)):
                    r1, r2 = robot_list[i], robot_list[j]
                    p1, p2 = active[r1], active[r2]

                    dist = math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

                    if dist < self.threshold:
                        pair = tuple(sorted((r1, r2)))
                        now = self.get_clock().now().to_msg().sec
                        if (now - self.last_comm_time.get(pair, 0)) >= self.comm_cooldown:
                            self.interaction_count += 1
                            self._log_proximity(r1, r2, dist)
                            self.trigger_comm(r1, r2, dist)
                            self.last_comm_time[pair] = now

        except Exception as e:
            self.get_logger().error(f"Check Error: {e}")

    def trigger_comm(self, source, target, distance):
        client = self.comm_clients.get(target)
        if not client:
            self.get_logger().error(f"Client for {target} not found!")
            return

        if not client.wait_for_service(timeout_sec=0.2):
            self.get_logger().warn(f"Service {target}/communicate not available!")
            return

        self._log_talk(source, target, distance)

        req = Trigger.Request()
        future = client.call_async(req)
        future.add_done_callback(partial(self.response_callback, s=source, t=target, d=distance))

    def response_callback(self, future, s, t, d):
        try:
            response = future.result()
            self._log_reply(t, s, d, response.message)
        except Exception as e:
            self.get_logger().error(f"Comm failed for {s}->{t}: {e}")

    # ─────────────────────────────────────────────
    #  Pretty-print helpers
    # ─────────────────────────────────────────────
    def _log_proximity(self, r1, r2, dist):
        lines = [
            "",
            _box_top(),
            _box_line(f"PROXIMITY DETECTED   (Interaction #{self.interaction_count})"),
            _box_mid(),
            _box_line(f"Robot A :  {r1}"),
            _box_line(f"Robot B :  {r2}"),
            _box_line(f"Distance:  {dist:.2f} units  (threshold {self.threshold})"),
            _box_bot(),
        ]
        self.get_logger().info("\n".join(lines))

    def _log_talk(self, source, target, dist):
        lines = [
            "",
            _box_top(),
            _box_line(f"COMMUNICATION REQUEST  #{self.interaction_count}"),
            _box_mid(),
            _box_line(f"Sender   :  {source}"),
            _box_line(f"Receiver :  {target}"),
            _box_line(f"Direction:  {source}  -->  {target}"),
            _box_line(f"Distance :  {dist:.2f} units"),
            _box_mid(),
            _box_line(f'Message  :  "Hii this is {source}"'),
            _box_bot(),
        ]
        self.get_logger().info("\n".join(lines))

    def _log_reply(self, responder, original_sender, dist, msg_text):
        lines = [
            "",
            _box_top(),
            _box_line(f"COMMUNICATION RESPONSE  #{self.interaction_count}"),
            _box_mid(),
            _box_line(f"Responder :  {responder}"),
            _box_line(f"Reply To  :  {original_sender}"),
            _box_line(f"Direction :  {responder}  <--  {original_sender}  (reply)"),
            _box_line(f"Distance  :  {dist:.2f} units"),
            _box_mid(),
            _box_line(f'Message   :  "{msg_text}"'),
            _box_bot(),
        ]
        self.get_logger().info("\n".join(lines))


def main(args=None):
    rclpy.init(args=args)
    try:
        node = ProximityMonitor()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        rclpy.shutdown()

if __name__ == '__main__':
    main()
