"""
Analysis Service — transforms raw graph metrics into architecture intelligence.

This service answers the "so what?" question:
- Not just "there are 3 cycles" but "auth.py ↔ user.py creates a security boundary violation"
- Not just "high fan-in" but "PaymentService is a deployment risk — 14 files depend on it"

Health score algorithm:
  Start at 100, apply penalty for each risk factor found.
  Score = max(0, 100 + Σ(penalties))
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.graph_algorithms import (
    compute_graph_metrics,
    detect_cycles,
    tarjan_scc,
    topological_sort,
)
from app.core.constants import (
    AnalysisType,
    COUPLING_THRESHOLD,
    HEALTH_SCORE_WEIGHTS,
    MAX_HEALTH_SCORE,
)
from app.core.logging import get_logger
from app.schemas.schemas import ArchitectureReportResponse, ArchitectureRisk
from app.services.graph_service import GraphService

logger = get_logger(__name__)


class AnalysisService:
    """
    Produces architecture intelligence reports from graph analysis.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._graph_service = GraphService(db)

    async def generate_architecture_report(
        self, repository_id: str
    ) -> ArchitectureReportResponse:
        """
        Full architecture intelligence report.

        Computes all graph analyses and synthesizes into a scored report with
        prioritized, actionable risk findings.
        """
        logger.info("analysis.report_start", repo_id=str(repository_id))

        # Build graph and run all analyses
        graph, file_meta = await self._graph_service._build_graph(repository_id)

        if not graph:
            return self._empty_report(repository_id)

        metrics = compute_graph_metrics(graph, COUPLING_THRESHOLD)
        cycles = detect_cycles(graph)
        sccs = tarjan_scc(graph)
        topo_order, cycle_groups = topological_sort(graph)

        # Generate risk findings
        risks: list[ArchitectureRisk] = []

        # 1. Circular dependencies
        risks.extend(self._detect_circular_dep_risks(cycles))

        # 2. Hotspot / high fan-in files
        risks.extend(self._detect_hotspot_risks(metrics))

        # 3. Tightly coupled module clusters (large SCCs)
        risks.extend(self._detect_coupling_risks(sccs))

        # 4. Dead code / orphan files
        risks.extend(self._detect_dead_code_risks(metrics))

        # 5. High graph density
        risks.extend(self._detect_density_risks(metrics))

        # Compute health score
        health_score = self._compute_health_score(
            risks, metrics, cycles, sccs
        )
        health_label = self._health_label(health_score)

        # Sort risks by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        risks.sort(key=lambda r: severity_order.get(r.severity, 4))

        # Decomposition suggestions
        decomposition = self._suggest_decomposition(sccs, metrics, graph)

        report = ArchitectureReportResponse(
            repository_id=repository_id,
            health_score=health_score,
            health_label=health_label,
            risks=risks,
            metrics={
                "node_count": metrics.node_count,
                "edge_count": metrics.edge_count,
                "graph_density": round(metrics.graph_density, 4),
                "coupling_score": round(metrics.coupling_score, 2),
                "cycle_count": len(cycles),
                "scc_count": len(sccs),
                "large_scc_count": len([s for s in sccs if len(s) > 1]),
                "entry_points": len(metrics.entry_points),
                "orphan_files": len(metrics.orphan_nodes),
                "hotspot_count": len(metrics.hotspot_nodes),
                "average_fan_in": round(
                    sum(metrics.fan_in.values()) / max(metrics.node_count, 1), 2
                ),
                "average_fan_out": round(
                    sum(metrics.fan_out.values()) / max(metrics.node_count, 1), 2
                ),
            },
            decomposition_suggestions=decomposition,
            generated_at=datetime.utcnow(),
        )

        logger.info(
            "analysis.report_complete",
            repo_id=str(repository_id),
            health_score=health_score,
            risk_count=len(risks),
        )

        return report

    # ─── Risk Detectors ───────────────────────────────────────────────────────

    def _detect_circular_dep_risks(
        self, cycles: list[list[str]]
    ) -> list[ArchitectureRisk]:
        risks = []
        for cycle in cycles[:10]:  # Cap at 10 most important cycles
            cycle_str = " → ".join(cycle[:4])
            if len(cycle) > 4:
                cycle_str += f" → ... ({len(cycle)} files)"

            severity = "critical" if len(cycle) <= 3 else "high"

            risks.append(
                ArchitectureRisk(
                    severity=severity,
                    category="circular_dependency",
                    title=f"Circular Dependency: {cycle[0]} ↔ {cycle[-1]}",
                    description=(
                        f"Circular dependency detected: {cycle_str}. "
                        f"This creates a tightly coupled cluster that prevents independent "
                        f"testing, deployment, and refactoring of these modules."
                    ),
                    affected_files=cycle,
                    recommendation=(
                        f"Extract the shared interface or contract into a separate module "
                        f"that both {cycle[0]} and {cycle[-1]} depend on. "
                        f"Consider dependency inversion: introduce an abstract layer."
                    ),
                )
            )
        return risks

    def _detect_hotspot_risks(self, metrics: Any) -> list[ArchitectureRisk]:
        risks = []

        # Sort hotspots by fan-in descending
        hotspots = sorted(
            [(path, metrics.fan_in.get(path, 0)) for path in metrics.hotspot_nodes],
            key=lambda x: x[1],
            reverse=True,
        )

        for path, fan_in in hotspots[:5]:
            severity = "critical" if fan_in > COUPLING_THRESHOLD * 2 else "high"
            risks.append(
                ArchitectureRisk(
                    severity=severity,
                    category="hotspot",
                    title=f"Architecture Hotspot: {path}",
                    description=(
                        f"{path} has {fan_in} modules depending on it — "
                        f"making it a single point of failure. Any breaking change "
                        f"here cascades through {fan_in} dependents."
                    ),
                    affected_files=[path],
                    recommendation=(
                        f"Consider splitting {path} into smaller, more focused modules. "
                        f"Introduce an interface layer to decouple dependents. "
                        f"Ensure comprehensive tests before any modification."
                    ),
                )
            )
        return risks

    def _detect_coupling_risks(
        self, sccs: list[list[str]]
    ) -> list[ArchitectureRisk]:
        risks = []
        large_sccs = [s for s in sccs if len(s) > 2]

        for scc in large_sccs[:5]:
            severity = "high" if len(scc) <= 5 else "critical"
            risks.append(
                ArchitectureRisk(
                    severity=severity,
                    category="tight_coupling",
                    title=f"Tightly Coupled Module Cluster ({len(scc)} files)",
                    description=(
                        f"A cluster of {len(scc)} files form a strongly connected component — "
                        f"they mutually depend on each other and cannot be independently "
                        f"deployed or tested. This is a monolith smell."
                    ),
                    affected_files=scc,
                    recommendation=(
                        f"Analyze this cluster for domain boundaries. "
                        f"Extract a well-defined interface module that others depend on, "
                        f"then break remaining circular links one at a time. "
                        f"Consider if this cluster represents a single cohesive bounded context "
                        f"that should be co-located as a service."
                    ),
                )
            )
        return risks

    def _detect_dead_code_risks(self, metrics: Any) -> list[ArchitectureRisk]:
        risks = []
        if len(metrics.orphan_nodes) > 5:
            severity = "medium" if len(metrics.orphan_nodes) < 20 else "high"
            risks.append(
                ArchitectureRisk(
                    severity=severity,
                    category="dead_code",
                    title=f"{len(metrics.orphan_nodes)} Potentially Dead Files",
                    description=(
                        f"{len(metrics.orphan_nodes)} files have no imports and are imported by "
                        f"nothing — they may be dead code, utility scripts, or forgotten modules. "
                        f"Dead code increases cognitive overhead and maintenance burden."
                    ),
                    affected_files=metrics.orphan_nodes[:15],
                    recommendation=(
                        "Audit these files: determine if they are entry points (scripts, tests), "
                        "dynamically loaded, or truly unused. Remove dead code to simplify the codebase."
                    ),
                )
            )
        return risks

    def _detect_density_risks(self, metrics: Any) -> list[ArchitectureRisk]:
        risks = []
        if metrics.graph_density > 0.15:
            severity = "high" if metrics.graph_density > 0.3 else "medium"
            risks.append(
                ArchitectureRisk(
                    severity=severity,
                    category="high_density",
                    title=f"High Dependency Density ({metrics.graph_density:.2%})",
                    description=(
                        f"The dependency graph has a density of {metrics.graph_density:.2%} — "
                        f"significantly above the healthy threshold of 5-10%. "
                        f"This indicates that modules are broadly coupled rather than following "
                        f"layered architecture principles."
                    ),
                    affected_files=[],
                    recommendation=(
                        "Enforce strict architectural layers (e.g., Controller → Service → Repository). "
                        "Introduce module boundaries and use dependency injection to reduce coupling. "
                        "Consider linting rules that enforce import direction constraints."
                    ),
                )
            )
        return risks

    # ─── Health Score ─────────────────────────────────────────────────────────

    def _compute_health_score(
        self,
        risks: list[ArchitectureRisk],
        metrics: Any,
        cycles: list,
        sccs: list,
    ) -> int:
        score = float(MAX_HEALTH_SCORE)

        # Penalty per cycle
        score += HEALTH_SCORE_WEIGHTS["cycle_penalty"] * min(len(cycles), 5)

        # Coupling penalty
        if metrics.coupling_score > 30:
            excess = metrics.coupling_score - 30
            score += HEALTH_SCORE_WEIGHTS["coupling_penalty"] * excess

        # Graph density penalty
        if metrics.graph_density > 0.1:
            excess = (metrics.graph_density - 0.1) * 100
            score += HEALTH_SCORE_WEIGHTS["density_penalty"] * excess

        # Large SCC penalty
        large_sccs = [s for s in sccs if len(s) > 2]
        score += HEALTH_SCORE_WEIGHTS["scc_size_penalty"] * len(large_sccs)

        # Dead code penalty
        dead_pct = (len(metrics.orphan_nodes) / max(metrics.node_count, 1)) * 100
        if dead_pct > 10:
            score += HEALTH_SCORE_WEIGHTS["dead_code_penalty"] * (dead_pct - 10)

        return max(0, min(MAX_HEALTH_SCORE, int(score)))

    def _health_label(self, score: int) -> str:
        if score >= 90:
            return "Excellent"
        elif score >= 75:
            return "Good"
        elif score >= 55:
            return "Fair"
        elif score >= 35:
            return "Poor"
        else:
            return "Critical"

    def _suggest_decomposition(
        self,
        sccs: list[list[str]],
        metrics: Any,
        graph: dict,
    ) -> list[dict[str, Any]]:
        """
        Suggest how to decompose a monolith into services.

        Strategy: Use SCC clusters + entry point / hotspot analysis to identify
        natural service boundaries.
        """
        suggestions = []

        # Each large SCC is a candidate bounded context
        for i, scc in enumerate([s for s in sccs if len(s) >= 3][:5]):
            # Find the "root" of this cluster (highest internal fan-in)
            cluster_files = set(scc)
            root = max(
                scc,
                key=lambda f: sum(
                    1 for neighbor in graph.get(f, []) if neighbor in cluster_files
                ),
            )
            suggestions.append({
                "type": "bounded_context",
                "title": f"Extract Service: {root.split('/')[-1].replace('.py','').replace('.ts','')}",
                "description": (
                    f"Files {', '.join(s.split('/')[-1] for s in scc[:3])} "
                    f"{'and others' if len(scc) > 3 else ''} form a natural service boundary."
                ),
                "files": scc,
                "confidence": "high" if len(scc) > 5 else "medium",
            })

        # Entry points as service API candidates
        for entry in metrics.entry_points[:3]:
            suggestions.append({
                "type": "api_boundary",
                "title": f"API Entry Point: {entry}",
                "description": f"{entry} has no incoming dependencies — candidate for a service public API.",
                "files": [entry],
                "confidence": "medium",
            })

        return suggestions

    def _empty_report(self, repository_id: str) -> ArchitectureReportResponse:
        return ArchitectureReportResponse(
            repository_id=repository_id,
            health_score=100,
            health_label="Excellent",
            risks=[],
            metrics={},
            decomposition_suggestions=[],
            generated_at=datetime.utcnow(),
        )