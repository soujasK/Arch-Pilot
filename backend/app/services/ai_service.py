"""
AI Service — LLM integration layer for architecture explanations.

Design principle: AI explains graph analysis results, it does NOT analyze raw code.

The service:
1. Loads all deterministic analysis results for the repository
2. Builds a structured context document from these results
3. Passes context + user question to the LLM
4. Returns grounded explanation

Provider abstraction: Any OpenAI-compatible API works (OpenAI, Anthropic via proxy,
local Ollama, etc.) — just configure OPENAI_BASE_URL.
"""

import uuid
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.constants import AI_SYSTEM_PROMPT
from app.core.logging import get_logger
from app.schemas.schemas import AIChatResponse
from app.services.analysis_service import AnalysisService
from app.services.graph_service import GraphService

logger = get_logger(__name__)


class AIService:
    """
    OpenAI-compatible LLM provider for architecture explanations.
    Context is built from deterministic graph analysis, not raw code.
    """

    def __init__(self, graph_service: GraphService, analysis_service: AnalysisService) -> None:
        self._graph_service = graph_service
        self._analysis_service = analysis_service

    async def answer_question(
        self,
        repository_id: str,
        question: str,
        context_file_path: Optional[str] = None,
    ) -> AIChatResponse:
        """
        Answer an architecture question grounded in graph analysis data.
        """
        if not settings.OPENAI_API_KEY:
            return AIChatResponse(
                answer=(
                    "AI analysis is not configured. Set OPENAI_API_KEY in your environment. "
                    "The deterministic graph analysis features work without an AI key — "
                    "use the Dependency Graph, Impact Analysis, and Architecture Report tabs."
                ),
                grounded_in=[],
                repository_id=repository_id,
            )

        # Build context from all available analyses
        context, grounded_in = await self._build_context(
            repository_id, question, context_file_path
        )

        # Call LLM
        try:
            answer = await self._call_llm(question, context)
        except Exception as e:
            logger.error("ai.llm_error", error=str(e))
            answer = (
                f"Unable to reach AI provider: {str(e)}. "
                "The deterministic analysis results are still available in other tabs."
            )

        return AIChatResponse(
            answer=answer,
            grounded_in=grounded_in,
            repository_id=repository_id,
        )

    async def _build_context(
        self,
        repository_id: str,
        question: str,
        context_file_path: Optional[str],
    ) -> tuple[str, list[str]]:
        """
        Assemble analysis context document for the LLM prompt.

        Only loads the analyses most relevant to the question.
        """
        sections: list[str] = []
        grounded_in: list[str] = []

        try:
            # Always include architecture report
            report = await self._analysis_service.generate_architecture_report(repository_id)
            sections.append(self._format_report_context(report))
            grounded_in.append("architecture_report")

            # Include graph metrics
            graph_metrics = await self._graph_service.compute_metrics(repository_id)
            sections.append(self._format_metrics_context(graph_metrics))
            grounded_in.append("graph_metrics")

            # Include cycle data if cycles exist
            cycles = await self._graph_service.detect_cycles_for_repo(repository_id)
            if cycles.has_cycles:
                sections.append(self._format_cycle_context(cycles))
                grounded_in.append("cycle_detection")

            # Include SCC data
            scc = await self._graph_service.compute_scc(repository_id)
            if scc.tightly_coupled_modules:
                sections.append(self._format_scc_context(scc))
                grounded_in.append("scc_analysis")

            # File-specific impact analysis if context file provided
            if context_file_path:
                impact = await self._graph_service.analyze_impact(
                    repository_id, context_file_path
                )
                sections.append(self._format_impact_context(impact))
                grounded_in.append("impact_analysis")

            # If question mentions a specific file, add its impact
            elif any(keyword in question.lower() for keyword in ["what breaks", "impact", "depends", "change"]):
                # Try to extract file mention from question
                topo = await self._graph_service.compute_topological_sort(repository_id)
                sections.append(self._format_topo_context(topo))
                grounded_in.append("topological_sort")

        except Exception as e:
            logger.error("ai.context_build_error", error=str(e))

        context = "\n\n".join(sections)
        return context, grounded_in

    def _format_report_context(self, report: Any) -> str:
        risks_text = "\n".join(
            f"  [{r.severity.upper()}] {r.title}: {r.description[:200]}"
            for r in report.risks[:10]
        )
        return f"""## Architecture Health Report
Health Score: {report.health_score}/100 ({report.health_label})

Key Metrics:
- Total files: {report.metrics.get('node_count', 0)}
- Dependencies: {report.metrics.get('edge_count', 0)}
- Circular dependencies: {report.metrics.get('cycle_count', 0)}
- Architecture hotspots: {report.metrics.get('hotspot_count', 0)}
- Graph density: {report.metrics.get('graph_density', 0):.2%}
- Coupling score: {report.metrics.get('coupling_score', 0):.1f}/100

Top Risks:
{risks_text or '  None detected.'}"""

    def _format_metrics_context(self, metrics: Any) -> str:
        top_depended = "\n".join(
            f"  {m['path']} (fan-in: {m['fan_in']}, centrality: {m['centrality']})"
            for m in metrics.most_depended_on[:10]
        )
        return f"""## Structural Metrics
Most critical files (highest dependency fan-in):
{top_depended}

Graph density: {metrics.graph_density:.4f}
Coupling score: {metrics.coupling_score:.1f}/100
Orphan/dead files: {len(metrics.orphan_files)}
Entry points: {len(metrics.entry_points)}"""

    def _format_cycle_context(self, cycles: Any) -> str:
        cycle_text = "\n".join(
            f"  Cycle {i+1}: {' → '.join(c[:5])}{'...' if len(c)>5 else ''}"
            for i, c in enumerate(cycles.cycles[:5])
        )
        return f"""## Circular Dependencies ({cycles.cycle_count} found)
{cycle_text}"""

    def _format_scc_context(self, scc: Any) -> str:
        scc_text = "\n".join(
            f"  Cluster of {len(s)} files: {', '.join(s[:4])}{'...' if len(s)>4 else ''}"
            for s in scc.tightly_coupled_modules[:5]
        )
        return f"""## Tightly Coupled Module Clusters (Strongly Connected Components)
{scc_text}"""

    def _format_impact_context(self, impact: Any) -> str:
        return f"""## Impact Analysis for {impact.file_path}
Impact score: {impact.impact_score:.1f}/100
Direct dependents ({len(impact.directly_affected)}): {', '.join(impact.directly_affected[:5])}
Transitive dependents ({impact.affected_count}): affects {impact.impact_percentage:.1f}% of codebase"""

    def _format_topo_context(self, topo: Any) -> str:
        return f"""## Safe Migration Order (Topological Sort)
Has cycles preventing full sort: {topo.has_cycles}
First files to migrate (leaf dependencies): {', '.join(topo.order[:10])}
Last files (most depended-upon): {', '.join(topo.order[-10:])}"""

    async def _call_llm(self, question: str, context: str) -> str:
        """Call OpenAI-compatible API."""
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": settings.AI_MODEL,
            "messages": [
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"## Repository Analysis Data\n\n{context}\n\n## Question\n\n{question}",
                },
            ],
            "max_tokens": settings.AI_MAX_TOKENS,
            "temperature": settings.AI_TEMPERATURE,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{settings.OPENAI_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                raise Exception(
                    f"LLM API error {response.status_code}: {response.text[:200]}"
                )

            data = response.json()
            return data["choices"][0]["message"]["content"]