"""
Graph Service — builds the dependency graph from persisted data
and executes all graph algorithms.

This is the analytical core of ArchPilot.
All algorithm results are cached in AnalysisResult for fast retrieval.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.graph_algorithms import (
    AdjList,
    GraphMetrics,
    build_impact_graph,
    compute_graph_metrics,
    detect_cycles,
    dfs_reachable,
    reverse_graph,
    tarjan_scc,
    topological_sort,
)
from app.core.constants import AnalysisType, COUPLING_THRESHOLD
from app.core.logging import get_logger
from app.db.models.models import AnalysisResult, Dependency, Repository, RepositoryFile
from app.schemas.schemas import (
    CycleDetectionResponse,
    DependencyEdge,
    DependencyGraphResponse,
    GraphMetricsResponse,
    GraphNode,
    ImpactAnalysisResponse,
    SCCResponse,
    TopologicalSortResponse,
)

logger = get_logger(__name__)


class GraphService:
    """
    Builds and analyzes dependency graphs for a repository.

    Graph representation: dict[str, list[str]] (adjacency list)
    where keys/values are file paths relative to repo root.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_dependency_graph(
        self, repository_id: str
    ) -> DependencyGraphResponse:
        """Build and return the full dependency graph."""
        graph, file_meta = await self._build_graph(repository_id)
        metrics = compute_graph_metrics(graph, COUPLING_THRESHOLD)
        cycles = detect_cycles(graph)
        cycle_files = {node for cycle in cycles for node in cycle}

        nodes = []
        for path, meta in file_meta.items():
            nodes.append(
                GraphNode(
                    id=path,
                    path=path,
                    file_type=meta["file_type"],
                    fan_in=metrics.fan_in.get(path, 0),
                    fan_out=metrics.fan_out.get(path, 0),
                    is_entry_point=path in metrics.entry_points,
                    is_dead_code=path in metrics.orphan_nodes,
                    centrality_score=round(metrics.pagerank.get(path, 0.0), 4),
                    in_cycle=path in cycle_files,
                )
            )

        edges = []
        for source, targets in graph.items():
            for target in targets:
                edges.append(DependencyEdge(source=source, target=target))

        return DependencyGraphResponse(
            repository_id=repository_id,
            nodes=nodes,
            edges=edges,
            adjacency_list=graph,
            node_count=metrics.node_count,
            edge_count=metrics.edge_count,
        )

    async def analyze_impact(
        self,
        repository_id: str,
        file_path: str,
        max_depth: int = 10,
    ) -> ImpactAnalysisResponse:
        """
        "What breaks if this file changes?"

        Reverses the dependency graph and performs BFS from the target file.
        """
        graph, file_meta = await self._build_graph(repository_id)
        total_files = len(file_meta)

        directly_affected, all_affected = build_impact_graph(graph, file_path, max_depth)

        impact_score = (len(all_affected) / max(total_files, 1)) * 100

        return ImpactAnalysisResponse(
            file_path=file_path,
            directly_affected=directly_affected,
            transitively_affected=all_affected,
            impact_score=round(impact_score, 2),
            affected_count=len(all_affected),
            total_file_count=total_files,
            impact_percentage=round(impact_score, 2),
        )

    async def detect_cycles_for_repo(
        self, repository_id: str
    ) -> CycleDetectionResponse:
        """Find all circular dependencies in the repository."""
        # Check cache
        cached = await self._get_cached_result(repository_id, AnalysisType.CYCLE_DETECTION)
        if cached:
            return CycleDetectionResponse(**cached)

        graph, _ = await self._build_graph(repository_id)
        cycles = detect_cycles(graph)
        files_in_cycles = list({node for cycle in cycles for node in cycle})

        result = CycleDetectionResponse(
            repository_id=repository_id,
            has_cycles=len(cycles) > 0,
            cycles=cycles,
            cycle_count=len(cycles),
            files_in_cycles=files_in_cycles,
        )

        await self._cache_result(
            repository_id, AnalysisType.CYCLE_DETECTION, result.model_dump(mode="json")
        )
        return result

    async def compute_scc(self, repository_id: str) -> SCCResponse:
        """Identify tightly coupled module clusters using Tarjan's SCC."""
        cached = await self._get_cached_result(repository_id, AnalysisType.SCC)
        if cached:
            return SCCResponse(**cached)

        graph, _ = await self._build_graph(repository_id)
        sccs = tarjan_scc(graph)

        # Sort by size descending
        sccs_sorted = sorted(sccs, key=len, reverse=True)
        tightly_coupled = [scc for scc in sccs_sorted if len(scc) > 1]

        result = SCCResponse(
            repository_id=repository_id,
            components=sccs_sorted,
            component_count=len(sccs_sorted),
            largest_scc_size=len(sccs_sorted[0]) if sccs_sorted else 0,
            tightly_coupled_modules=tightly_coupled,
        )

        await self._cache_result(
            repository_id, AnalysisType.SCC, result.model_dump(mode="json")
        )
        return result

    async def compute_topological_sort(
        self, repository_id: str
    ) -> TopologicalSortResponse:
        """Determine safe migration/refactoring order."""
        cached = await self._get_cached_result(repository_id, AnalysisType.TOPO_SORT)
        if cached:
            return TopologicalSortResponse(**cached)

        graph, _ = await self._build_graph(repository_id)
        order, cycle_groups = topological_sort(graph)

        result = TopologicalSortResponse(
            repository_id=repository_id,
            order=order,
            has_cycles=len(cycle_groups) > 0,
            cycle_groups=cycle_groups,
        )

        await self._cache_result(
            repository_id, AnalysisType.TOPO_SORT, result.model_dump(mode="json")
        )
        return result

    async def compute_metrics(
        self, repository_id: str
    ) -> GraphMetricsResponse:
        """Compute structural metrics over the dependency graph."""
        cached = await self._get_cached_result(repository_id, AnalysisType.DEPENDENCY_GRAPH)
        # Metrics are always freshly computed (fast enough)

        graph, file_meta = await self._build_graph(repository_id)
        metrics = compute_graph_metrics(graph, COUPLING_THRESHOLD)

        # Top depended-on files (highest fan-in)
        most_depended = sorted(
            [
                {
                    "path": path,
                    "fan_in": metrics.fan_in.get(path, 0),
                    "centrality": round(metrics.pagerank.get(path, 0.0), 4),
                }
                for path in file_meta
            ],
            key=lambda x: x["fan_in"],
            reverse=True,
        )[:20]

        # Most dependent files (highest fan-out)
        most_dependent = sorted(
            [
                {"path": path, "fan_out": metrics.fan_out.get(path, 0)}
                for path in file_meta
            ],
            key=lambda x: x["fan_out"],
            reverse=True,
        )[:20]

        return GraphMetricsResponse(
            repository_id=repository_id,
            most_depended_on=most_depended,
            most_dependent=most_dependent,
            orphan_files=metrics.orphan_nodes[:50],
            entry_points=metrics.entry_points[:20],
            dead_files=metrics.leaf_nodes[:20],
            average_fan_in=round(
                sum(metrics.fan_in.values()) / max(metrics.node_count, 1), 2
            ),
            average_fan_out=round(
                sum(metrics.fan_out.values()) / max(metrics.node_count, 1), 2
            ),
            graph_density=round(metrics.graph_density, 4),
            coupling_score=round(metrics.coupling_score, 2),
        )

    # ─── Internal Graph Builder ───────────────────────────────────────────────

    async def _build_graph(
        self, repository_id: str
    ) -> tuple[AdjList, dict[str, dict]]:
        """
        Load dependency data from DB and build adjacency list.

        Returns:
            (graph, file_metadata)
            - graph: {source_path: [target_path, ...]}
            - file_metadata: {path: {file_type, ...}}
        """
        # Load all files
        files_result = await self._db.execute(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository_id
            )
        )
        files = files_result.scalars().all()
        file_map: dict[str, str] = {f.id: f.path for f in files}
        file_meta: dict[str, dict] = {
            f.path: {"file_type": f.file_type, "size_bytes": f.size_bytes}
            for f in files
        }

        # Initialize all nodes (even isolated ones appear in graph)
        graph: AdjList = {f.path: [] for f in files}

        # Load all dependencies
        deps_result = await self._db.execute(
            select(Dependency).where(
                Dependency.repository_id == repository_id
            )
        )
        deps = deps_result.scalars().all()

        for dep in deps:
            source_path = file_map.get(dep.source_file_id)
            target_path = file_map.get(dep.target_file_id)
            if source_path and target_path and source_path != target_path:
                if target_path not in graph[source_path]:
                    graph[source_path].append(target_path)

        logger.info(
            "graph.built",
            nodes=len(graph),
            edges=sum(len(v) for v in graph.values()),
            repo_id=str(repository_id),
        )

        return graph, file_meta

    async def _get_cached_result(
        self, repository_id: str, analysis_type: AnalysisType
    ) -> Optional[dict]:
        result = await self._db.execute(
            select(AnalysisResult).where(
                AnalysisResult.repository_id == repository_id,
                AnalysisResult.analysis_type == analysis_type.value,
            )
        )
        row = result.scalar_one_or_none()
        return row.result_json if row else None

    async def _cache_result(
        self,
        repository_id: str,
        analysis_type: AnalysisType,
        data: dict,
    ) -> None:
        # Check if exists, update or insert
        result = await self._db.execute(
            select(AnalysisResult).where(
                AnalysisResult.repository_id == repository_id,
                AnalysisResult.analysis_type == analysis_type.value,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.result_json = data
        else:
            record = AnalysisResult(
                repository_id=repository_id,
                analysis_type=analysis_type.value,
                result_json=data,
            )
            self._db.add(record)

        await self._db.flush()