import math

class GraphManager:
    def __init__(self):
        # Nodes: ID -> (x, y) - 5x4 Grid (20 nodes)
        self.nodes = {
            'A': (0.0, 0.0), 'B': (2.0, 0.0), 'C': (4.0, 0.0), 'D': (6.0, 0.0), 'E': (8.0, 0.0),
            'F': (0.0, 2.0), 'G': (2.0, 2.0), 'H': (4.0, 2.0), 'I': (6.0, 2.0), 'J': (8.0, 2.0),
            'K': (0.0, 4.0), 'L': (2.0, 4.0), 'M': (4.0, 4.0), 'NodeN': (6.0, 4.0), 'O': (8.0, 4.0),
            'P': (0.0, 6.0), 'Q': (2.0, 6.0), 'R': (4.0, 6.0), 'S': (6.0, 6.0), 'T': (8.0, 6.0)
        }
        
        # Grid dimensions for connectivity logic
        rows = [
            ['A', 'B', 'C', 'D', 'E'],
            ['F', 'G', 'H', 'I', 'J'],
            ['K', 'L', 'M', 'NodeN', 'O'],
            ['P', 'Q', 'R', 'S', 'T']
        ]
        
        self.edges = []
        # Horizontal
        for row in rows:
            for i in range(len(row) - 1):
                self.edges.append((row[i], row[i+1]))
        
        # Vertical
        for col_idx in range(5):
            for row_idx in range(3):
                self.edges.append((rows[row_idx][col_idx], rows[row_idx+1][col_idx]))
        
        # Diagonals (\ slope)
        for row_idx in range(3):
            for col_idx in range(4):
                self.edges.append((rows[row_idx][col_idx], rows[row_idx+1][col_idx+1]))
        
        # Diagonals (/ slope)
        for row_idx in range(3):
            for col_idx in range(1, 5):
                self.edges.append((rows[row_idx][col_idx], rows[row_idx+1][col_idx-1]))
        

    def get_coords(self, node_id):
        return self.nodes.get(node_id)

    def is_edge(self, n1, n2):
        """Check if an edge exists between two nodes (bidirectional check)."""
        return (n1, n2) in self.edges or (n2, n1) in self.edges

    def interpolate(self, start_node, end_node, alpha):
        """
        Interpolate between two nodes. alpha is [0, 1]
        """
        p1 = self.nodes[start_node]
        p2 = self.nodes[end_node]
        x = p1[0] + (p2[0] - p1[0]) * alpha
        y = p1[1] + (p2[1] - p1[1]) * alpha
        return (x, y)

    def get_distance(self, p1, p2):
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
