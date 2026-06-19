"""
API Routes — all ArchPilot endpoints.

Route design:
- POST for analysis operations (they mutate state / trigger computation)
- GET for retrieval of already-computed results
- UUID path params for resource identification
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.database import get_db
from app.db.models.models import Repository
from app.schemas.schemas import (
    AIChatRequest,
    AIChatResponse,
    AnalysisStatusResponse,
    ArchitectureReportResponse,
    CycleDetectionResponse,
    DependencyGraphResponse,
    GraphMetricsResponse,
    ImpactAnalysisRequest,
    ImpactAnalysisResponse,
    RepositoryAnalyzeRequest,
    RepositoryMetadata,
    RepositorySummaryResponse,
    RepositoryTreeResponse,
    SCCResponse,
    TopologicalSortResponse,
)
from app.services.ai_service import AIService
from app.services.analysis_service import AnalysisService
from app.services.github_service import GitHubService
from app.services.graph_service import GraphService
from app.services.repository_service import RepositoryService

router = APIRouter()
logger = get_logger(__name__)


# ─── Dependency Providers ─────────────────────────────────────────────────────

async def get_github_service() -> GitHubService:
    service = GitHubService()
    try:
        yield service
    finally:
        await service.close()


def get_graph_service(db: AsyncSession = Depends(get_db)) -> GraphService:
    return GraphService(db)


def get_analysis_service(db: AsyncSession = Depends(get_db)) -> AnalysisService:
    return AnalysisService(db)


def get_ai_service(
    db: AsyncSession = Depends(get_db),
) -> AIService:
    graph_service = GraphService(db)
    analysis_service = AnalysisService(db)
    return AIService(graph_service, analysis_service)


# ─── Repository Routes ────────────────────────────────────────────────────────

@router.post(
    "/repositories/analyze",
    response_model=RepositoryMetadata,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger repository analysis",
)
async def analyze_repository(
    request: RepositoryAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    github: GitHubService = Depends(get_github_service),
) -> RepositoryMetadata:
    """
    Analyze a GitHub repository.

    Fetches metadata, traverses file tree, extracts dependencies,
    and builds the dependency graph. Returns immediately with repository metadata;
    full analysis status can be polled via GET /repositories/{id}/status.
    """
    service = RepositoryService(db, github)
    try:
        repo = await service.analyze_repository(request.url)
        await db.refresh(repo)
        return RepositoryMetadata.model_validate(repo)
    except Exception as e:
        logger.error("api.analyze_error", url=request.url, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


@router.get(
    "/repositories",
    response_model=list[RepositoryMetadata],
    summary="List all analyzed repositories",
)
async def list_repositories(
    db: AsyncSession = Depends(get_db),
) -> list[RepositoryMetadata]:
    result = await db.execute(
        select(Repository).order_by(Repository.created_at.desc()).limit(50)
    )
    repos = result.scalars().all()
    return [RepositoryMetadata.model_validate(r) for r in repos]


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositoryMetadata,
    summary="Get repository metadata",
)
async def get_repository(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> RepositoryMetadata:
    repo = await _get_repo_or_404(db, repository_id)
    return RepositoryMetadata.model_validate(repo)


@router.get(
    "/repositories/{repository_id}/summary",
    response_model=RepositorySummaryResponse,
    summary="Get repository summary with file and dependency counts",
)
async def get_repository_summary(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
    github: GitHubService = Depends(get_github_service),
) -> RepositorySummaryResponse:
    await _get_repo_or_404(db, repository_id)
    service = RepositoryService(db, github)
    summary = await service.get_summary(repository_id)

    return RepositorySummaryResponse(
        repository=RepositoryMetadata.model_validate(summary["repository"]),
        file_count=summary["file_count"],
        dependency_count=summary["dependency_count"],
        languages=summary["languages"],
        has_analysis=summary["has_analysis"],
    )


@router.get(
    "/repositories/{repository_id}/tree",
    response_model=RepositoryTreeResponse,
    summary="Get nested repository file tree",
)
async def get_repository_tree(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
    github: GitHubService = Depends(get_github_service),
) -> RepositoryTreeResponse:
    await _get_repo_or_404(db, repository_id)
    service = RepositoryService(db, github)
    tree = await service.get_repository_tree(repository_id)

    # Count totals
    def count_nodes(node: Any) -> tuple[int, int]:
        files = sum(1 for c in node.children if c.type == "file")
        dirs = sum(1 for c in node.children if c.type == "directory")
        for child in node.children:
            if child.type == "directory":
                cf, cd = count_nodes(child)
                files += cf
                dirs += cd
        return files, dirs

    total_files, total_dirs = count_nodes(tree)

    return RepositoryTreeResponse(
        repository_id=repository_id,
        tree=tree,
        total_files=total_files,
        total_dirs=total_dirs,
    )


@router.get(
    "/repositories/{repository_id}/status",
    response_model=AnalysisStatusResponse,
    summary="Get analysis status",
)
async def get_analysis_status(
    repository_id: str,
    db: AsyncSession = Depends(get_db),
) -> AnalysisStatusResponse:
    repo = await _get_repo_or_404(db, repository_id)
    return AnalysisStatusResponse(
        repository_id=repository_id,
        status=repo.status,
        completed_analyses=[],
        pending_analyses=[],
    )


# ─── Graph Analysis Routes ────────────────────────────────────────────────────

@router.get(
    "/repositories/{repository_id}/graph",
    response_model=DependencyGraphResponse,
    summary="Get full dependency graph",
)
async def get_dependency_graph(
    repository_id: str,
    graph_service: GraphService = Depends(get_graph_service),
) -> DependencyGraphResponse:
    return await graph_service.get_dependency_graph(repository_id)


@router.post(
    "/repositories/{repository_id}/impact",
    response_model=ImpactAnalysisResponse,
    summary="Analyze what breaks if a file changes",
)
async def analyze_impact(
    repository_id: str,
    request: ImpactAnalysisRequest,
    graph_service: GraphService = Depends(get_graph_service),
) -> ImpactAnalysisResponse:
    """
    "What breaks if this file changes?"

    Performs DFS on reversed dependency graph to find all transitively
    affected files if the specified file were modified.
    """
    return await graph_service.analyze_impact(
        repository_id=repository_id,
        file_path=request.file_path,
        max_depth=request.max_depth,
    )


@router.get(
    "/repositories/{repository_id}/cycles",
    response_model=CycleDetectionResponse,
    summary="Detect circular dependencies",
)
async def detect_cycles(
    repository_id: str,
    graph_service: GraphService = Depends(get_graph_service),
) -> CycleDetectionResponse:
    return await graph_service.detect_cycles_for_repo(repository_id)


@router.get(
    "/repositories/{repository_id}/scc",
    response_model=SCCResponse,
    summary="Identify tightly coupled module clusters (Strongly Connected Components)",
)
async def get_scc(
    repository_id: str,
    graph_service: GraphService = Depends(get_graph_service),
) -> SCCResponse:
    return await graph_service.compute_scc(repository_id)


@router.get(
    "/repositories/{repository_id}/topo-sort",
    response_model=TopologicalSortResponse,
    summary="Get safe migration/refactoring order (Topological Sort)",
)
async def get_topological_sort(
    repository_id: str,
    graph_service: GraphService = Depends(get_graph_service),
) -> TopologicalSortResponse:
    return await graph_service.compute_topological_sort(repository_id)


@router.get(
    "/repositories/{repository_id}/metrics",
    response_model=GraphMetricsResponse,
    summary="Get graph structural metrics and centrality",
)
async def get_metrics(
    repository_id: str,
    graph_service: GraphService = Depends(get_graph_service),
) -> GraphMetricsResponse:
    return await graph_service.compute_metrics(repository_id)


# ─── Architecture Intelligence Routes ─────────────────────────────────────────

@router.get(
    "/repositories/{repository_id}/report",
    response_model=ArchitectureReportResponse,
    summary="Generate full architecture intelligence report",
)
async def get_architecture_report(
    repository_id: str,
    analysis_service: AnalysisService = Depends(get_analysis_service),
) -> ArchitectureReportResponse:
    """
    Comprehensive architecture analysis:
    - Health score (0-100)
    - Risk findings (critical/high/medium/low)
    - Decomposition suggestions
    - Full metric suite
    """
    return await analysis_service.generate_architecture_report(repository_id)


# ─── AI Chat Routes ───────────────────────────────────────────────────────────

@router.post(
    "/repositories/{repository_id}/chat",
    response_model=AIChatResponse,
    summary="Ask the AI architect about this repository",
)
async def chat_with_ai(
    repository_id: str,
    request: AIChatRequest,
    ai_service: AIService = Depends(get_ai_service),
) -> AIChatResponse:
    """
    Ask architecture questions, grounded in deterministic analysis.

    Examples:
    - "What breaks if auth.py changes?"
    - "Which modules should I refactor first?"
    - "Explain the dependency structure of the payment module"
    - "How should I decompose this monolith?"
    """
    return await ai_service.answer_question(
        repository_id=repository_id,
        question=request.question,
        context_file_path=request.context_file_path,
    )


# ─── Helper ───────────────────────────────────────────────────────────────────

async def _get_repo_or_404(db: AsyncSession, repository_id: str) -> Repository:
    result = await db.execute(
        select(Repository).where(Repository.id == repository_id)
    )
    repo = result.scalar_one_or_none()
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository {repository_id} not found",
        )
    return repo