"""
Unit tests for graph algorithms.

These tests are pure Python — no DB, no HTTP, no mocks.
The decoupling of algorithm logic from infrastructure makes this possible.
"""

import pytest

from app.algorithms.graph_algorithms import (
    bfs_distances,
    bfs_layers,
    build_impact_graph,
    compute_graph_metrics,
    detect_cycles,
    dfs_reachable,
    reverse_graph,
    tarjan_scc,
    topological_sort,
)


# ─── Test Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def simple_graph():
    """
    A → B → D
    A → C → D
    """
    return {
        "A": ["B", "C"],
        "B": ["D"],
        "C": ["D"],
        "D": [],
    }


@pytest.fixture
def cyclic_graph():
    """
    A → B → C → A (cycle)
    D → E (no cycle)
    """
    return {
        "A": ["B"],
        "B": ["C"],
        "C": ["A"],
        "D": ["E"],
        "E": [],
    }


@pytest.fixture
def complex_graph():
    """
    Simulates a realistic module dependency graph.
    """
    return {
        "main.py": ["app.py", "config.py"],
        "app.py": ["auth.py", "database.py"],
        "auth.py": ["database.py", "models.py"],
        "database.py": ["config.py"],
        "models.py": ["database.py"],
        "config.py": [],
        "utils.py": [],  # Orphan
    }


# ─── DFS Tests ────────────────────────────────────────────────────────────────

class TestDFS:
    def test_reachable_from_root(self, simple_graph):
        result = dfs_reachable(simple_graph, "A")
        assert result == {"B", "C", "D"}

    def test_reachable_from_leaf(self, simple_graph):
        result = dfs_reachable(simple_graph, "D")
        assert result == set()

    def test_reachable_excludes_start(self, simple_graph):
        result = dfs_reachable(simple_graph, "A")
        assert "A" not in result

    def test_reachable_from_middle(self, simple_graph):
        result = dfs_reachable(simple_graph, "B")
        assert result == {"D"}

    def test_reachable_in_cycle(self, cyclic_graph):
        """DFS should handle cycles without infinite loop."""
        result = dfs_reachable(cyclic_graph, "A")
        assert "B" in result
        assert "C" in result


# ─── BFS Tests ────────────────────────────────────────────────────────────────

class TestBFS:
    def test_distances_from_root(self, simple_graph):
        distances = bfs_distances(simple_graph, "A")
        assert distances["A"] == 0
        assert distances["B"] == 1
        assert distances["C"] == 1
        assert distances["D"] == 2

    def test_layers(self, simple_graph):
        layers = bfs_layers(simple_graph, "A")
        assert layers[0] == ["A"]
        assert set(layers[1]) == {"B", "C"}
        assert layers[2] == ["D"]

    def test_single_node(self):
        graph = {"A": []}
        distances = bfs_distances(graph, "A")
        assert distances == {"A": 0}


# ─── Cycle Detection Tests ────────────────────────────────────────────────────

class TestCycleDetection:
    def test_no_cycles(self, simple_graph):
        cycles = detect_cycles(simple_graph)
        assert cycles == []

    def test_detects_simple_cycle(self, cyclic_graph):
        cycles = detect_cycles(cyclic_graph)
        assert len(cycles) >= 1
        # Check that the cycle contains A, B, C
        cycle_files = {node for cycle in cycles for node in cycle}
        assert "A" in cycle_files or "B" in cycle_files or "C" in cycle_files

    def test_detects_self_loop(self):
        graph = {"A": ["A"]}
        cycles = detect_cycles(graph)
        assert len(cycles) >= 1

    def test_complex_graph_no_false_positives(self, complex_graph):
        """Complex acyclic graph should have no cycles."""
        cycles = detect_cycles(complex_graph)
        assert cycles == []

    def test_multiple_cycles(self):
        graph = {
            "A": ["B"],
            "B": ["A"],  # Cycle 1: A ↔ B
            "C": ["D"],
            "D": ["C"],  # Cycle 2: C ↔ D
        }
        cycles = detect_cycles(graph)
        assert len(cycles) >= 2


# ─── Tarjan's SCC Tests ───────────────────────────────────────────────────────

class TestTarjanSCC:
    def test_each_node_is_own_scc_in_dag(self, simple_graph):
        sccs = tarjan_scc(simple_graph)
        # No node should appear in an SCC with another node
        multi_node_sccs = [s for s in sccs if len(s) > 1]
        assert multi_node_sccs == []

    def test_cycle_forms_scc(self, cyclic_graph):
        sccs = tarjan_scc(cyclic_graph)
        # A, B, C should be in the same SCC
        multi_sccs = [set(s) for s in sccs if len(s) > 1]
        assert any({"A", "B", "C"} == s for s in multi_sccs)

    def test_all_nodes_covered(self, complex_graph):
        sccs = tarjan_scc(complex_graph)
        all_nodes_in_sccs = {node for scc in sccs for node in scc}
        assert all_nodes_in_sccs == set(complex_graph.keys())

    def test_empty_graph(self):
        sccs = tarjan_scc({})
        assert sccs == []


# ─── Topological Sort Tests ───────────────────────────────────────────────────

class TestTopologicalSort:
    def test_valid_order_simple(self, simple_graph):
        order, cycle_groups = topological_sort(simple_graph)
        assert cycle_groups == []

        # Verify ordering: for every edge u→v, u appears before v
        pos = {node: i for i, node in enumerate(order)}
        for u, neighbors in simple_graph.items():
            for v in neighbors:
                assert pos[u] < pos[v], f"{u} should come before {v}"

    def test_cycle_detected(self, cyclic_graph):
        order, cycle_groups = topological_sort(cyclic_graph)
        # Nodes in cycles can't be sorted
        assert len(cycle_groups) > 0
        # Non-cyclic nodes (D, E) should still appear in order
        assert "D" in order or "E" in order

    def test_complex_graph_ordering(self, complex_graph):
        order, cycle_groups = topological_sort(complex_graph)
        assert cycle_groups == []

        # config.py should come before everything that depends on it
        pos = {node: i for i, node in enumerate(order)}
        assert pos["config.py"] < pos["database.py"]
        assert pos["database.py"] < pos["auth.py"]


# ─── Graph Metrics Tests ──────────────────────────────────────────────────────

class TestGraphMetrics:
    def test_node_and_edge_count(self, simple_graph):
        metrics = compute_graph_metrics(simple_graph)
        assert metrics.node_count == 4
        assert metrics.edge_count == 4  # A→B, A→C, B→D, C→D

    def test_fan_in_calculation(self, simple_graph):
        metrics = compute_graph_metrics(simple_graph)
        assert metrics.fan_in["D"] == 2  # B and C both point to D
        assert metrics.fan_in["A"] == 0
        assert metrics.fan_in["B"] == 1

    def test_fan_out_calculation(self, simple_graph):
        metrics = compute_graph_metrics(simple_graph)
        assert metrics.fan_out["A"] == 2
        assert metrics.fan_out["D"] == 0

    def test_entry_points(self, simple_graph):
        metrics = compute_graph_metrics(simple_graph)
        assert "A" in metrics.entry_points  # No incoming deps, has outgoing

    def test_orphan_detection(self, complex_graph):
        metrics = compute_graph_metrics(complex_graph)
        assert "utils.py" in metrics.orphan_nodes  # No incoming, no outgoing

    def test_pagerank_normalized(self, complex_graph):
        metrics = compute_graph_metrics(complex_graph)
        assert all(0.0 <= v <= 1.0 for v in metrics.pagerank.values())

    def test_high_fan_in_is_hotspot(self):
        """Files with fan-in >= threshold should be hotspots."""
        graph = {f"consumer_{i}": ["shared.py"] for i in range(15)}
        graph["shared.py"] = []
        metrics = compute_graph_metrics(graph, coupling_threshold=10.0)
        assert "shared.py" in metrics.hotspot_nodes

    def test_empty_graph(self):
        metrics = compute_graph_metrics({})
        assert metrics.node_count == 0
        assert metrics.edge_count == 0
        assert metrics.coupling_score == 0.0


# ─── Impact Analysis Tests ────────────────────────────────────────────────────

class TestImpactAnalysis:
    def test_impact_of_leaf(self, complex_graph):
        """config.py is a dependency of many — changes should have high impact."""
        directly, all_affected = build_impact_graph(complex_graph, "config.py")
        # database.py directly imports config.py
        assert "database.py" in directly
        # main.py transitively depends on config through app → database
        assert "main.py" in all_affected

    def test_impact_of_root(self, complex_graph):
        """main.py has no dependents."""
        directly, all_affected = build_impact_graph(complex_graph, "main.py")
        assert directly == []
        assert all_affected == []

    def test_reverse_graph(self, simple_graph):
        rev = reverse_graph(simple_graph)
        # In original: A→B. In reversed: B→A
        assert "A" in rev["B"]
        # D has no outgoing in original, so D→nothing. But B→D reversed means D→B? No.
        # D appears as a target in B and C, so in reversed: D→B, D→C
        assert "B" in rev.get("D", []) or "C" in rev.get("D", [])
