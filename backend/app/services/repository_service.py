"""
Repository Service — orchestrates the full repository analysis pipeline.

Pipeline:
  1. Parse and validate GitHub URL
  2. Fetch repo metadata → persist Repository record
  3. Traverse file tree → persist RepositoryFile records
  4. Fetch file contents → extract imports
  5. Persist Dependency records
  6. Trigger graph analysis

Design: Each step is independently resumable.
If a repo was already analyzed, return cached results.
"""

import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import LANGUAGE_EXTENSIONS, SKIP_DIRS, SKIP_FILES, Language
from app.core.logging import get_logger
from app.db.models.models import AnalysisResult, Dependency, Repository, RepositoryFile
from app.parsers.js_ts_parser import JavaScriptParser, TypeScriptParser
from app.parsers.python_parser import PythonParser
from app.schemas.schemas import TreeNode
from app.services.github_service import GitHubService

logger = get_logger(__name__)


class RepositoryService:
    """
    Orchestrates repository intake and dependency extraction.
    Coordinates between GitHub API, parsers, and persistence layer.
    """

    def __init__(self, db: AsyncSession, github: GitHubService) -> None:
        self._db = db
        self._github = github
        self._python_parser = PythonParser()
        self._js_parser = JavaScriptParser()
        self._ts_parser = TypeScriptParser()

    async def analyze_repository(self, url: str) -> Repository:
        """
        Full repository intake pipeline.
        Returns existing repository if already analyzed.
        """
        owner, repo_name = self._github.parse_url(url)

        # Check if already exists
        existing = await self._get_repository_by_name(owner, repo_name)
        if existing and existing.status == "completed":
            logger.info("repository.cache_hit", owner=owner, repo=repo_name)
            return existing

        logger.info("repository.analysis_start", owner=owner, repo=repo_name)

        # Fetch metadata from GitHub
        metadata = await self._github.get_repository_metadata(owner, repo_name)

        # Persist or update repository record
        repository = await self._upsert_repository(metadata, "processing")

        try:
            # Traverse and persist file tree
            await self._process_file_tree(repository, owner, repo_name, metadata["default_branch"])

            # Extract and persist dependencies
            await self._extract_dependencies(repository, owner, repo_name, metadata["default_branch"])

            repository.status = "completed"
            await self._db.flush()

            logger.info(
                "repository.analysis_complete",
                owner=owner,
                repo=repo_name,
                repo_id=str(repository.id),
            )

        except Exception as e:
            repository.status = "failed"
            await self._db.flush()
            logger.error(
                "repository.analysis_failed",
                owner=owner,
                repo=repo_name,
                error=str(e),
            )
            raise

        return repository

    async def get_repository_tree(self, repository_id: str) -> TreeNode:
        """Build a nested tree structure from flat file list."""
        result = await self._db.execute(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository_id
            )
        )
        files = result.scalars().all()

        return self._build_tree_node(files, repository_id)

    def _build_tree_node(
        self, files: list[RepositoryFile], repository_id: str
    ) -> TreeNode:
        """
        Convert flat file list to nested TreeNode structure.

        Algorithm: Insert each path into a trie-like dict, then serialize.
        """
        # Build nested dict structure
        root: dict[str, Any] = {"__files__": [], "__dirs__": {}}

        for f in files:
            parts = Path(f.path).parts
            current = root

            # Navigate/create directory nodes
            for part in parts[:-1]:
                if part not in current["__dirs__"]:
                    current["__dirs__"][part] = {"__files__": [], "__dirs__": {}}
                current = current["__dirs__"][part]

            # Add file to current directory
            current["__files__"].append(f)

        def serialize(node: dict, path: str = "", name: str = "root") -> TreeNode:
            children = []

            # Add directories first
            for dir_name, dir_node in sorted(node["__dirs__"].items()):
                dir_path = f"{path}/{dir_name}" if path else dir_name
                children.append(serialize(dir_node, dir_path, dir_name))

            # Then files
            for file in sorted(node["__files__"], key=lambda f: f.path):
                file_name = Path(file.path).name
                children.append(
                    TreeNode(
                        name=file_name,
                        path=file.path,
                        type="file",
                        file_type=file.file_type,
                        size_bytes=file.size_bytes,
                        has_dependencies=len(file.outbound_deps) > 0,
                    )
                )

            return TreeNode(
                name=name,
                path=path or "/",
                type="directory",
                children=children,
            )

        return serialize(root)

    async def get_summary(self, repository_id: str) -> dict[str, Any]:
        """Get repository summary statistics."""
        repo_result = await self._db.execute(
            select(Repository).where(Repository.id == repository_id)
        )
        repo = repo_result.scalar_one_or_none()
        if not repo:
            return {}

        files_result = await self._db.execute(
            select(RepositoryFile).where(RepositoryFile.repository_id == repository_id)
        )
        files = files_result.scalars().all()

        deps_result = await self._db.execute(
            select(Dependency).where(Dependency.repository_id == repository_id)
        )
        dep_count = len(deps_result.scalars().all())

        # Language distribution
        lang_counts: dict[str, int] = {}
        for f in files:
            lang_counts[f.file_type] = lang_counts.get(f.file_type, 0) + 1

        return {
            "repository": repo,
            "file_count": len(files),
            "dependency_count": dep_count,
            "languages": lang_counts,
            "has_analysis": repo.status == "completed",
        }

    # ─── Private Pipeline Methods ─────────────────────────────────────────────

    async def _process_file_tree(
        self,
        repository: Repository,
        owner: str,
        repo_name: str,
        branch: str,
    ) -> None:
        """Fetch tree from GitHub and persist RepositoryFile records."""
        tree = await self._github.get_repository_tree(owner, repo_name, branch)

        # Clear existing files for this repo (re-analysis)
        existing = await self._db.execute(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository.id
            )
        )
        for f in existing.scalars().all():
            await self._db.delete(f)

        file_count = 0
        for item in tree:
            if item.get("type") != "blob":
                continue  # Skip tree (directory) nodes

            path = item.get("path", "")
            if not self._should_include_file(path):
                continue

            ext = Path(path).suffix.lower()
            file_type = LANGUAGE_EXTENSIONS.get(ext, Language.UNKNOWN).value

            if file_type == Language.UNKNOWN.value:
                continue  # Only index files we can parse

            db_file = RepositoryFile(
                repository_id=repository.id,
                path=path,
                file_type=file_type,
                size_bytes=item.get("size", 0),
            )
            self._db.add(db_file)
            file_count += 1

            if file_count >= settings.GITHUB_MAX_FILES_PER_REPO:
                logger.warning(
                    "repository.file_limit_reached",
                    limit=settings.GITHUB_MAX_FILES_PER_REPO,
                )
                break

        await self._db.flush()
        logger.info(
            "repository.files_persisted",
            count=file_count,
            repo_id=str(repository.id),
        )

    async def _extract_dependencies(
        self,
        repository: Repository,
        owner: str,
        repo_name: str,
        branch: str,
    ) -> None:
        """Fetch file contents, extract imports, persist Dependency records."""
        # Get all persisted files
        files_result = await self._db.execute(
            select(RepositoryFile).where(
                RepositoryFile.repository_id == repository.id
            )
        )
        files = files_result.scalars().all()
        file_map: dict[str, RepositoryFile] = {f.path: f for f in files}
        all_paths = set(file_map.keys())

        if not files:
            logger.warning("repository.no_files", repo_id=str(repository.id))
            return

        # Batch fetch file contents
        paths = [f.path for f in files]
        logger.info(
            "repository.fetching_contents",
            file_count=len(paths),
            repo_id=str(repository.id),
        )

        contents = await self._github.get_file_contents_batch(
            owner, repo_name, paths, branch, concurrency=8
        )

        # Extract dependencies
        dep_count = 0
        from app.core.config import settings as app_settings

        for file in files:
            source = contents.get(file.path)
            if not source:
                continue

            file.line_count = source.count("\n") + 1

            # Select appropriate parser
            if file.file_type == Language.PYTHON.value:
                imports = self._python_parser.extract_imports(
                    source, file.path, all_paths
                )
            elif file.file_type == Language.JAVASCRIPT.value:
                imports = self._js_parser.extract_imports(
                    source, file.path, all_paths
                )
            elif file.file_type == Language.TYPESCRIPT.value:
                imports = self._ts_parser.extract_imports(
                    source, file.path, all_paths
                )
            else:
                continue

            for target_path in imports:
                target_file = file_map.get(target_path)
                if not target_file:
                    continue

                dep = Dependency(
                    repository_id=repository.id,
                    source_file_id=file.id,
                    target_file_id=target_file.id,
                    import_statement=target_path,
                )
                self._db.add(dep)
                dep_count += 1

        await self._db.flush()
        logger.info(
            "repository.dependencies_extracted",
            dep_count=dep_count,
            repo_id=str(repository.id),
        )

    async def _upsert_repository(
        self, metadata: dict[str, Any], status: str
    ) -> Repository:
        existing = await self._get_repository_by_name(
            metadata["owner"], metadata["name"]
        )
        if existing:
            existing.status = status
            existing.stars = metadata["stars"]
            existing.description = metadata["description"]
            await self._db.flush()
            return existing

        repo = Repository(
            owner=metadata["owner"],
            name=metadata["name"],
            url=metadata["url"],
            description=metadata["description"],
            language=metadata["language"],
            stars=metadata["stars"],
            forks=metadata["forks"],
            default_branch=metadata["default_branch"],
            status=status,
        )
        self._db.add(repo)
        await self._db.flush()
        return repo

    async def _get_repository_by_name(
        self, owner: str, name: str
    ) -> Optional[Repository]:
        result = await self._db.execute(
            select(Repository).where(
                Repository.owner == owner,
                Repository.name == name,
            )
        )
        return result.scalar_one_or_none()

    def _should_include_file(self, path: str) -> bool:
        """Filter out files/dirs that shouldn't be analyzed."""
        parts = Path(path).parts

        # Check for skip dirs
        for part in parts[:-1]:
            if part in SKIP_DIRS:
                return False

        # Check for skip files
        filename = parts[-1]
        if filename in SKIP_FILES:
            return False

        return True


# Import at bottom to avoid circular import
from app.core.config import settings