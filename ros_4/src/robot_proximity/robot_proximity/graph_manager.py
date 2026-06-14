import math
from collections import deque

class GraphManager:
    def __init__(self):
        # ── Grid dimensions: 10 columns × 8 rows = 80 cells (A1 … H10) ─────
        self.cell_size = 2.0
        self.num_cols  = 10
        self.num_rows  = 8
        self.row_letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

        # Build node dictionary
        self.rows  = []
        self.nodes = {}
        for r_idx, letter in enumerate(self.row_letters):
            row = []
            for c_idx in range(self.num_cols):
                name = f"{letter}{c_idx + 1}"
                x    = c_idx * self.cell_size
                y    = r_idx * self.cell_size
                self.nodes[name] = (x, y)
                row.append(name)
            self.rows.append(row)

        # ── Obstacles (10 × 8 grid, spread to keep graph fully connected) ───
        # Rows A and H are kept fully clear so there is always a perimeter path.
        self.obstacles = [
            'B4',   # row B, col 4
            'B8',   # row B, col 8
            'C2',   # row C, col 2
            'C6',   # row C, col 6
            'D5',   # row D, col 5
            'D9',   # row D, col 9
            'E3',   # row E, col 3
            'E7',   # row E, col 7
            'F2',   # row F, col 2
            'F6',   # row F, col 6
            'G4',   # row G, col 4
            'G9',   # row G, col 9
        ]

        self.edges = []
        self._adj = {}
        self.update_obstacles(self.obstacles)

    def update_obstacles(self, new_obstacles):
        self.obstacles = list(new_obstacles)
        
        # Rebuild edges
        self.edges = []
        for row in self.rows:
            for i in range(len(row) - 1):
                n1, n2 = row[i], row[i + 1]
                if n1 not in self.obstacles and n2 not in self.obstacles:
                    self.edges.append((n1, n2))

        for col_idx in range(self.num_cols):
            for row_idx in range(self.num_rows - 1):
                n1 = self.rows[row_idx][col_idx]
                n2 = self.rows[row_idx + 1][col_idx]
                if n1 not in self.obstacles and n2 not in self.obstacles:
                    self.edges.append((n1, n2))

        # Rebuild adjacency
        self._adj = {n: [] for n in self.nodes}
        for n1, n2 in self.edges:
            self._adj[n1].append(n2)
            self._adj[n2].append(n1)

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_coords(self, node_id):
        return self.nodes.get(node_id)

    def is_obstacle(self, node_id):
        return node_id in self.obstacles

    def is_edge(self, n1, n2):
        return (n1, n2) in self.edges or (n2, n1) in self.edges

    def interpolate(self, start_node, end_node, alpha):
        p1 = self.nodes[start_node]
        p2 = self.nodes[end_node]
        return (p1[0] + (p2[0] - p1[0]) * alpha,
                p1[1] + (p2[1] - p1[1]) * alpha)

    def get_distance(self, p1, p2):
        return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

    # ── BFS pathfinding ───────────────────────────────────────────────────────

    def find_path(self, start, end):
        """BFS shortest path from start to end. Returns node list or None."""
        if start == end:
            return [start]
        if start not in self._adj or end not in self._adj:
            return None
        visited = {start}
        queue   = deque([(start, [start])])
        while queue:
            cur, path = queue.popleft()
            for nb in self._adj[cur]:
                if nb == end:
                    return path + [nb]
                if nb not in visited:
                    visited.add(nb)
                    queue.append((nb, path + [nb]))
        return None

    def find_path_excluding(self, start, end, excluded_nodes=None):
        """BFS avoiding excluded_nodes (used for deadlock rerouting)."""
        excluded = set(excluded_nodes or [])
        excluded.discard(start)
        excluded.discard(end)
        if start == end:
            return [start]
        if start not in self._adj or end not in self._adj:
            return None
        visited = {start}
        queue   = deque([(start, [start])])
        while queue:
            cur, path = queue.popleft()
            for nb in self._adj[cur]:
                if nb in excluded or nb in visited:
                    continue
                if nb == end:
                    return path + [nb]
                visited.add(nb)
                queue.append((nb, path + [nb]))
        return None

    def resolve_path(self, waypoints):
        """Resolve a list of waypoints into a valid edge-by-edge path,
        automatically BFS-routing around any obstacle waypoints."""
        if not waypoints:
            return []

        # Skip leading obstacles
        start_idx = 0
        while start_idx < len(waypoints) and self.is_obstacle(waypoints[start_idx]):
            start_idx += 1
        if start_idx >= len(waypoints):
            return []

        resolved = [waypoints[start_idx]]

        for i in range(start_idx, len(waypoints) - 1):
            src = resolved[-1]
            dst = waypoints[i + 1]
            if self.is_obstacle(dst):
                continue
            if src == dst:
                continue
            if self.is_edge(src, dst):
                resolved.append(dst)
            else:
                sub = self.find_path(src, dst)
                if sub:
                    resolved.extend(sub[1:])
                # else: unreachable, halt at src

        return resolved
