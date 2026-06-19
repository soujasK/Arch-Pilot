"""
Domain constants — single source of truth for magic values.
"""

from enum import Enum


class Language(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    UNKNOWN = "unknown"


class AnalysisType(str, Enum):
    DEPENDENCY_GRAPH = "dependency_graph"
    IMPACT_ANALYSIS = "impact_analysis"
    CYCLE_DETECTION = "cycle_detection"
    SCC = "strongly_connected_components"
    TOPO_SORT = "topological_sort"
    ARCHITECTURE_REPORT = "architecture_report"
    DEAD_CODE = "dead_code"
    COMPLEXITY = "complexity"


class RepositoryStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# File extensions mapped to language
LANGUAGE_EXTENSIONS: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".jsx": Language.JAVASCRIPT,
    ".mjs": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".tsx": Language.TYPESCRIPT,
    ".mts": Language.TYPESCRIPT,
}

# Directories to always skip during traversal
SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules",
    ".git",
    ".github",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "vendor",
    "third_party",
    "migrations",  # Exclude auto-generated migration files
})

# Files to skip
SKIP_FILES: frozenset[str] = frozenset({
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
})

# Architecture scoring weights
HEALTH_SCORE_WEIGHTS: dict[str, float] = {
    "cycle_penalty": -15.0,        # Per cycle found
    "coupling_penalty": -0.5,      # Per unit above threshold
    "density_penalty": -10.0,      # Per unit above threshold
    "dead_code_penalty": -2.0,     # Per dead file percentage point
    "scc_size_penalty": -5.0,      # Per large SCC found
}

MAX_HEALTH_SCORE: int = 100
COUPLING_THRESHOLD: float = 10.0   # Fan-in threshold for hotspot detection
DENSITY_THRESHOLD: float = 0.3    # Graph density threshold

# AI prompts — keep them here, not scattered in service files
AI_SYSTEM_PROMPT = """You are ArchPilot, an expert software architecture analyst.

You ONLY analyze software architecture based on deterministic graph analysis results provided to you.
You do NOT invent facts about code you haven't seen.
You do NOT make up dependencies or relationships.

Your analysis is grounded in:
- Dependency graphs (adjacency lists)
- Graph algorithm outputs (SCCs, cycles, topological order, centrality)
- Architecture metrics (coupling scores, density, health scores)

When explaining architecture:
- Be specific about module names from the analysis
- Reference actual metrics and scores
- Prioritize actionable refactoring recommendations
- Explain the WHY behind each risk

Format responses in clear sections. Be a senior architect, not a textbook."""
