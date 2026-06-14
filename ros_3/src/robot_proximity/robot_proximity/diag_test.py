from robot_proximity.graph_manager import GraphManager
import sys

def test():
    gm = GraphManager()
    paths_to_test = [
        ('robot1', 'A1,A2,A3,A4,A5,A6,A7,B7,C7,D7,E7'),
        ('robot3', 'A1,A2,B2,C2,C3,C4,C5,D5,E5,E6,E7'),
        ('robot5', 'A3,B3,C3,D3,E3,E4,D4,C4,B4,A4,A5')
    ]

    for rid, path_str in paths_to_test:
        print(f"\nTesting {rid}: {path_str}")
        waypoints = [p.strip() for p in path_str.split(',') if p.strip()]
        resolved = gm.resolve_path(waypoints)
        print(f"Resolved: {' -> '.join(resolved)}")

        errors = []
        for i, node in enumerate(resolved):
            if gm.is_obstacle(node):
                errors.append(f"  ERROR: Node {node} at index {i} is an OBSTACLE!")
        
        for i in range(len(resolved) - 1):
            n1, n2 = resolved[i], resolved[i+1]
            if not gm.is_edge(n1, n2):
                errors.append(f"  ERROR: No edge between {n1} and {n2} (non-adjacent)!")
        
        if not errors:
            print("  Path is VALID (no obstacles, all movements are adjacent).")
        else:
            for e in errors:
                print(e)

if __name__ == "__main__":
    test()
