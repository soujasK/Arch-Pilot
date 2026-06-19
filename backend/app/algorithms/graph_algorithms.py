"""
Core graph algorithms operating on plain adjacency lists.

Design decision: All algorithms take dict[str, list[str]] (adjacency list)
as input. This decouples algorithm logic from ORM/persistence entirely —
unit testable with no DB dependency.

Algorithms implemented:
- DFS (iterative, avoids Python recursion limit on large graphs)
- BFS
- Cycle Detection (DFS coloring)
- Tarjan's SCC (iterative)
- Kahn's Topological Sort
- Graph Centrality Metrics
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional


AdjList = dict[str, list[str]]


# ─── DFS ─────────────────────────────────────────────────────────────────────

def dfs_reachable(graph: AdjList, start: str) -> set[str]:
    """
    Iterative DFS from start node.
    Returns all nodes reachable from start (excluding start itself).

    Use case: Impact analysis — "what breaks if {start} changes?"
    """
    visited: set[str] = set()
    stack = [start]

    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                stack.append(neighbor)

    visited.discard(start)
    return visited


def dfs_path(graph: AdjList, start: str, end: str) -> Optional[list[str]]:
    """
    Find any path from start to end using DFS.
    Returns path as list of nodes, or None if no path exists.
    """
    stack: list[tuple[str, list[str]]] = [(start, [start])]
    visited: set[str] = set()

    while stack:
        node, path = stack.pop()
        if node == end:
            return path
        if node in visited:
            continue
        visited.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                stack.append((neighbor, path + [neighbor]))

    return None


# ─── BFS ─────────────────────────────────────────────────────────────────────

def bfs_distances(graph: AdjList, start: str) -> dict[str, int]:
    """
    BFS from start. Returns {node: shortest_distance} for all reachable nodes.

    Use case: Dependency layer analysis — how far is each module from an entry point?
    """
    distances: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])

    while queue:
        node = queue.popleft()
        current_dist = distances[node]
        for neighbor in graph.get(node, []):
            if neighbor not in distances:
                distances[neighbor] = current_dist + 1
                queue.append(neighbor)

    return distances


def bfs_layers(graph: AdjList, start: str) -> list[list[str]]:
    """
    BFS returning nodes grouped by distance layer.
    Layer 0 = [start], Layer 1 = direct deps, etc.

    Use case: Visualizing dependency depth.
    """
    layers: list[list[str]] = [[start]]
    visited = {start}
    current_layer = [start]

    while current_layer:
        next_layer = []
        for node in current_layer:
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_layer.append(neighbor)
        if next_layer:
            layers.append(next_layer)
        current_layer = next_layer

    return layers


# ─── Cycle Detection ─────────────────────────────────────────────────────────

def detect_cycles(graph: AdjList) -> list[list[str]]:
    """
    Detect all cycles in a directed graph using DFS with coloring.

    Colors: 0=unvisited, 1=in-stack (gray), 2=done (black)

    Returns list of cycles, each represented as an ordered list of nodes.
    Note: For large graphs, we extract representative cycles (not all permutations).
    """
    color: dict[str, int] = {node: 0 for node in graph}
    parent: dict[str, Optional[str]] = {node: None for node in graph}
    cycles: list[list[str]] = []
    seen_cycle_sets: set[frozenset] = set()

    def extract_cycle(cycle_start: str, current: str) -> list[str]:
        """Trace back through parent pointers to extract cycle."""
        cycle = [current]
        node = current
        while node != cycle_start:
            node = parent[node]  # type: ignore
            cycle.append(node)
        cycle.reverse()
        return cycle

    for start_node in graph:
        if color[start_node] != 0:
            continue

        stack = [(start_node, iter(graph.get(start_node, [])))]
        color[start_node] = 1

        while stack:
            node, neighbors = stack[-1]
            try:
                neighbor = next(neighbors)
                if color.get(neighbor, 0) == 0:
                    color[neighbor] = 1
                    parent[neighbor] = node
                    stack.append((neighbor, iter(graph.get(neighbor, []))))
                elif color.get(neighbor, 0) == 1:
                    # Back edge found — cycle detected
                    cycle = extract_cycle(neighbor, node)
                    cycle_set = frozenset(cycle)
                    if cycle_set not in seen_cycle_sets:
                        seen_cycle_sets.add(cycle_set)
                        cycles.append(cycle)
            except StopIteration:
                node, _ = stack.pop()
                color[node] = 2

    return cycles


# ─── Tarjan's SCC ─────────────────────────────────────────────────────────────

@dataclass
class _TarjanState:
    index_counter: int = 0
    stack: list[str] = field(default_factory=list)
    on_stack: set[str] = field(default_factory=set)
    index: dict[str, int] = field(default_factory=dict)
    lowlink: dict[str, int] = field(default_factory=dict)
    sccs: list[list[str]] = field(default_factory=list)


def tarjan_scc(graph: AdjList) -> list[list[str]]:
    """
    Iterative Tarjan's Strongly Connected Components algorithm.

    Returns list of SCCs, each as a list of node IDs.
    SCCs with >1 node represent tightly coupled modules.

    Time: O(V + E), Space: O(V)
    """
    state = _TarjanState()
    all_nodes = set(graph.keys())
    for neighbors in graph.values():
        all_nodes.update(neighbors)

    def strongconnect(start: str) -> None:
        # Iterative version to avoid Python recursion limits
        call_stack: list[tuple[str, int]] = [(start, 0)]
        state.index[start] = state.lowlink[start] = state.index_counter
        state.index_counter += 1
        state.stack.append(start)
        state.on_stack.add(start)

        while call_stack:
            v, i = call_stack[-1]
            neighbors = graph.get(v, [])

            if i < len(neighbors):
                w = neighbors[i]
                call_stack[-1] = (v, i + 1)

                if w not in state.index:
                    state.index[w] = state.lowlink[w] = state.index_counter
                    state.index_counter += 1
                    state.stack.append(w)
                    state.on_stack.add(w)
                    call_stack.append((w, 0))
                elif w in state.on_stack:
                    state.lowlink[v] = min(state.lowlink[v], state.index[w])
            else:
                call_stack.pop()
                if call_stack:
                    parent_v = call_stack[-1][0]
                    state.lowlink[parent_v] = min(state.lowlink[parent_v], state.lowlink[v])

                # Root of SCC
                if state.lowlink[v] == state.index[v]:
                    scc: list[str] = []
                    while True:
                        w = state.stack.pop()
                        state.on_stack.discard(w)
                        scc.append(w)
                        if w == v:
                            break
                    state.sccs.append(scc)

    for node in all_nodes:
        if node not in state.index:
            strongconnect(node)

    return state.sccs


# ─── Topological Sort (Kahn's Algorithm) ─────────────────────────────────────

def topological_sort(graph: AdjList) -> tuple[list[str], list[list[str]]]:
    """
    Kahn's algorithm for topological sort.

    Returns:
        (sorted_order, cycle_groups)
        - sorted_order: files in safe build/migration order
        - cycle_groups: nodes that couldn't be sorted due to cycles

    Time: O(V + E)
    """
    all_nodes: set[str] = set(graph.keys())
    for neighbors in graph.values():
        all_nodes.update(neighbors)

    in_degree: dict[str, int] = {node: 0 for node in all_nodes}
    for node in graph:
        for neighbor in graph.get(node, []):
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    queue: deque[str] = deque(
        node for node in all_nodes if in_degree.get(node, 0) == 0
    )
    sorted_order: list[str] = []

    while queue:
        node = queue.popleft()
        sorted_order.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Nodes not in sorted_order are in cycles
    sorted_set = set(sorted_order)
    cycle_nodes = [n for n in all_nodes if n not in sorted_set]

    # Group cycle nodes by their SCC
    if cycle_nodes:
        cycle_subgraph = {
            n: [nb for nb in graph.get(n, []) if nb in cycle_nodes]
            for n in cycle_nodes
        }
        cycle_groups = [
            scc for scc in tarjan_scc(cycle_subgraph) if len(scc) > 1
        ]
    else:
        cycle_groups = []

    return sorted_order, cycle_groups


# ─── Graph Metrics & Centrality ───────────────────────────────────────────────

@dataclass
class GraphMetrics:
    node_count: int
    edge_count: int
    graph_density: float
    fan_in: dict[str, int]             # node -> incoming edge count
    fan_out: dict[str, int]            # node -> outgoing edge count
    pagerank: dict[str, float]         # Approximated importance score
    coupling_score: float              # 0-100, architecture coupling level
    orphan_nodes: list[str]
    entry_points: list[str]            # Fan-in=0, fan-out>0
    leaf_nodes: list[str]              # Fan-out=0 (pure dependencies)
    hotspot_nodes: list[str]           # High fan-in nodes


def compute_graph_metrics(graph: AdjList, coupling_threshold: float = 10.0) -> GraphMetrics:
    """
    Compute structural metrics over the dependency graph.

    PageRank approximation: iterative power method (20 iterations sufficient for convergence).
    """
    all_nodes: set[str] = set(graph.keys())
    for neighbors in graph.values():
        all_nodes.update(neighbors)

    n = len(all_nodes)
    if n == 0:
        return GraphMetrics(
            node_count=0, edge_count=0, graph_density=0.0,
            fan_in={}, fan_out={}, pagerank={}, coupling_score=0.0,
            orphan_nodes=[], entry_points=[], leaf_nodes=[], hotspot_nodes=[]
        )

    # Fan-in / fan-out
    fan_out: dict[str, int] = {node: len(graph.get(node, [])) for node in all_nodes}
    fan_in: dict[str, int] = defaultdict(int)
    edge_count = 0

    for node in graph:
        for neighbor in graph.get(node, []):
            fan_in[neighbor] += 1
            edge_count += 1

    fan_in_complete = {node: fan_in.get(node, 0) for node in all_nodes}

    # Graph density: actual_edges / max_possible_edges
    max_edges = n * (n - 1)
    density = edge_count / max_edges if max_edges > 0 else 0.0

    # Iterative PageRank (damping=0.85, 20 iterations)
    damping = 0.85
    pagerank: dict[str, float] = {node: 1.0 / n for node in all_nodes}

    # Build reverse graph for PageRank
    reverse_graph: dict[str, list[str]] = defaultdict(list)
    for node in graph:
        for neighbor in graph.get(node, []):
            reverse_graph[neighbor].append(node)

    for _ in range(20):
        new_rank: dict[str, float] = {}
        for node in all_nodes:
            incoming_sum = sum(
                pagerank[pred] / max(fan_out.get(pred, 1), 1)
                for pred in reverse_graph.get(node, [])
            )
            new_rank[node] = (1 - damping) / n + damping * incoming_sum
        pagerank = new_rank

    # Normalize PageRank to 0-1
    max_rank = max(pagerank.values()) if pagerank else 1.0
    if max_rank > 0:
        pagerank = {k: v / max_rank for k, v in pagerank.items()}

    # Classify nodes
    orphan_nodes = [
        n for n in all_nodes
        if fan_in_complete[n] == 0 and fan_out.get(n, 0) == 0
    ]
    entry_points = [
        n for n in all_nodes
        if fan_in_complete[n] == 0 and fan_out.get(n, 0) > 0
    ]
    leaf_nodes = [
        n for n in all_nodes
        if fan_out.get(n, 0) == 0 and fan_in_complete[n] > 0
    ]
    hotspot_nodes = [
        n for n in all_nodes
        if fan_in_complete[n] >= coupling_threshold
    ]

    # Coupling score: normalized measure of architectural coupling
    if n > 1:
        avg_fan_in = sum(fan_in_complete.values()) / n
        max_possible_fan_in = n - 1
        coupling_score = min(100.0, (avg_fan_in / max_possible_fan_in) * 100 * 5)
    else:
        coupling_score = 0.0

    return GraphMetrics(
        node_count=n,
        edge_count=edge_count,
        graph_density=density,
        fan_in=fan_in_complete,
        fan_out=dict(fan_out),
        pagerank=pagerank,
        coupling_score=coupling_score,
        orphan_nodes=orphan_nodes,
        entry_points=entry_points,
        leaf_nodes=leaf_nodes,
        hotspot_nodes=hotspot_nodes,
    )


def reverse_graph(graph: AdjList) -> AdjList:
    """
    Build the transpose of a directed graph.
    Used for impact analysis: "who depends on me?" instead of "who do I depend on?"
    """
    reversed_: AdjList = defaultdict(list)
    for node in graph:
        for neighbor in graph.get(node, []):
            reversed_[neighbor].append(node)
    # Ensure all original nodes exist in reversed graph
    for node in graph:
        if node not in reversed_:
            reversed_[node] = []
    return dict(reversed_)


def build_impact_graph(
    forward_graph: AdjList, file_path: str, max_depth: int = 10
) -> tuple[list[str], list[str]]:
    """
    Compute what breaks if file_path changes.

    Strategy: reverse the dependency graph, then DFS from file_path.
    In the reversed graph, edge A->B means "A depends on B",
    so DFS from file_path finds everything that imports it (transitively).

    Returns:
        (directly_affected, all_transitively_affected)
    """
    rev = reverse_graph(forward_graph)

    directly_affected = rev.get(file_path, [])

    # BFS with depth limit for transitive impact
    visited: set[str] = {file_path}
    queue: deque[tuple[str, int]] = deque([(file_path, 0)])
    all_affected: list[str] = []

    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for dependent in rev.get(node, []):
            if dependent not in visited:
                visited.add(dependent)
                all_affected.append(dependent)
                queue.append((dependent, depth + 1))

    return directly_affected, all_affected
