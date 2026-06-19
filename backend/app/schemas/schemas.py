"""
Pydantic v2 schemas — strict validation at API boundaries.

Separate Request/Response schemas prevent accidentally exposing internal fields.
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ─── Repository Schemas ──────────────────────────────────────────────────────

class RepositoryAnalyzeRequest(BaseModel):
    url: str = Field(..., description="GitHub repository URL")

    @field_validator("url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if "github.com" not in v:
            raise ValueError("Only GitHub repositories are supported")
        # Normalize https://github.com/owner/repo
        parts = v.replace("https://", "").replace("http://", "").split("/")
        if len(parts) < 3:
            raise ValueError("URL must be in format: https://github.com/owner/repo")
        return v


class RepositoryMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner: str
    name: str
    url: str
    description: Optional[str] = None
    language: Optional[str] = None
    stars: int
    forks: int
    status: str
    default_branch: str
    created_at: datetime
    updated_at: datetime


class RepositorySummaryResponse(BaseModel):
    repository: RepositoryMetadata
    file_count: int
    dependency_count: int
    languages: dict[str, int]  # language -> file count
    has_analysis: bool


# ─── Graph / Dependency Schemas ───────────────────────────────────────────────

class DependencyEdge(BaseModel):
    source: str
    target: str
    import_statement: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    path: str
    file_type: str
    fan_in: int = 0           # Incoming edges = how many depend on this
    fan_out: int = 0          # Outgoing edges = how many this depends on
    is_entry_point: bool = False
    is_dead_code: bool = False
    centrality_score: float = 0.0
    in_cycle: bool = False


class DependencyGraphResponse(BaseModel):
    repository_id: uuid.UUID
    nodes: list[GraphNode]
    edges: list[DependencyEdge]
    adjacency_list: dict[str, list[str]]
    node_count: int
    edge_count: int


# ─── Algorithm Result Schemas ─────────────────────────────────────────────────

class ImpactAnalysisRequest(BaseModel):
    repository_id: uuid.UUID
    file_path: str = Field(..., description="Path of the file to analyze impact for")
    max_depth: int = Field(default=10, ge=1, le=50)


class ImpactAnalysisResponse(BaseModel):
    file_path: str
    directly_affected: list[str]      # Files that directly import this
    transitively_affected: list[str]  # All files in impact blast radius
    impact_score: float               # 0-100, how critical this file is
    affected_count: int
    total_file_count: int
    impact_percentage: float


class CycleDetectionResponse(BaseModel):
    repository_id: uuid.UUID
    has_cycles: bool
    cycles: list[list[str]]           # Each cycle is an ordered list of file paths
    cycle_count: int
    files_in_cycles: list[str]


class SCCResponse(BaseModel):
    repository_id: uuid.UUID
    components: list[list[str]]       # Each SCC is a list of file paths
    component_count: int
    largest_scc_size: int
    tightly_coupled_modules: list[list[str]]  # SCCs with >1 node


class TopologicalSortResponse(BaseModel):
    repository_id: uuid.UUID
    order: list[str]                  # Files in safe migration order
    has_cycles: bool
    cycle_groups: list[list[str]]     # Groups that must be handled together


class GraphMetricsResponse(BaseModel):
    repository_id: uuid.UUID
    most_depended_on: list[dict[str, Any]]   # [{path, fan_in, centrality}]
    most_dependent: list[dict[str, Any]]     # [{path, fan_out}]
    orphan_files: list[str]                  # No incoming or outgoing deps
    entry_points: list[str]                  # No incoming deps, has outgoing
    dead_files: list[str]                    # No outgoing deps, no incoming
    average_fan_in: float
    average_fan_out: float
    graph_density: float                     # edges / max_possible_edges
    coupling_score: float                    # 0-100, higher = more coupled


# ─── Architecture Intelligence Schemas ────────────────────────────────────────

class ArchitectureRisk(BaseModel):
    severity: str       # "critical" | "high" | "medium" | "low"
    category: str       # "circular_dependency" | "hotspot" | "dead_code" | etc.
    title: str
    description: str
    affected_files: list[str]
    recommendation: str


class ArchitectureReportResponse(BaseModel):
    repository_id: uuid.UUID
    health_score: int           # 0-100
    health_label: str           # "Critical" | "Poor" | "Fair" | "Good" | "Excellent"
    risks: list[ArchitectureRisk]
    metrics: dict[str, Any]
    decomposition_suggestions: list[dict[str, Any]]
    generated_at: datetime


# ─── AI Chat Schemas ──────────────────────────────────────────────────────────

class AIChatRequest(BaseModel):
    repository_id: uuid.UUID
    question: str = Field(..., min_length=3, max_length=2000)
    context_file_path: Optional[str] = None   # Optional focus file


class AIChatResponse(BaseModel):
    answer: str
    grounded_in: list[str]      # Which analysis types informed this answer
    repository_id: uuid.UUID


# ─── Repository Tree Schema ───────────────────────────────────────────────────

class TreeNode(BaseModel):
    name: str
    path: str
    type: str           # "file" | "directory"
    file_type: Optional[str] = None
    children: list["TreeNode"] = []
    size_bytes: int = 0
    has_dependencies: bool = False


TreeNode.model_rebuild()  # Required for self-referential model


class RepositoryTreeResponse(BaseModel):
    repository_id: uuid.UUID
    tree: TreeNode
    total_files: int
    total_dirs: int


# ─── Analysis Status Schema ───────────────────────────────────────────────────

class AnalysisStatusResponse(BaseModel):
    repository_id: uuid.UUID
    status: str
    completed_analyses: list[str]
    pending_analyses: list[str]
    error_message: Optional[str] = None