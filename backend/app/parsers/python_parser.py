"""
Python dependency extractor using AST parsing.

Design decision: Use AST, not regex.
AST parsing handles edge cases that regex misses:
- Multi-line imports
- Conditional imports
- Star imports
- Aliased imports

Falls back to regex only when AST parsing fails (syntax errors in source).
"""

import ast
import re
from pathlib import Path
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class PythonParser:
    """
    Extracts import dependencies from Python source files.

    Returns resolved file paths (relative to repo root) when possible.
    Falls back to module names for third-party/stdlib imports.
    """

    # Standard library modules (partial list — used for filtering)
    STDLIB_MODULES = frozenset({
        "os", "sys", "re", "ast", "io", "abc", "copy", "math", "json",
        "time", "datetime", "pathlib", "typing", "collections", "itertools",
        "functools", "contextlib", "dataclasses", "enum", "logging",
        "threading", "multiprocessing", "asyncio", "concurrent", "subprocess",
        "socket", "http", "urllib", "email", "html", "xml", "csv", "sqlite3",
        "unittest", "hashlib", "hmac", "secrets", "base64", "struct",
        "pickle", "shelve", "tempfile", "shutil", "glob", "fnmatch",
        "platform", "signal", "traceback", "warnings", "inspect", "types",
    })

    def extract_imports(
        self,
        source_code: str,
        file_path: str,
        all_project_files: set[str],
    ) -> list[str]:
        """
        Parse Python source and return list of dependency file paths.

        Only returns intra-project dependencies (files that exist in the repo).
        Third-party and stdlib imports are filtered out.
        """
        try:
            tree = ast.parse(source_code)
            raw_imports = self._extract_from_ast(tree, file_path)
        except SyntaxError:
            logger.warning("python_parser.syntax_error", file=file_path)
            raw_imports = self._extract_from_regex(source_code)

        return self._resolve_to_project_files(
            raw_imports, file_path, all_project_files
        )

    def _extract_from_ast(
        self, tree: ast.Module, file_path: str
    ) -> list[tuple[str, Optional[str]]]:
        """
        Walk AST and collect (module_name, from_module) tuples.
        """
        imports: list[tuple[str, Optional[str]]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((alias.name, None))

            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    # Absolute import: from module import x
                    imports.append((node.module, None))
                elif node.level and node.level > 0:
                    # Relative import: from .module import x
                    base = self._resolve_relative_base(file_path, node.level)
                    module = f"{base}.{node.module}" if node.module else base
                    imports.append((module, "relative"))

        return imports

    def _extract_from_regex(self, source: str) -> list[tuple[str, Optional[str]]]:
        """Fallback regex extraction when AST fails."""
        imports = []
        patterns = [
            r'^import\s+([\w.]+)',
            r'^from\s+([\w.]+)\s+import',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, source, re.MULTILINE):
                imports.append((match.group(1), None))
        return imports

    def _resolve_relative_base(self, file_path: str, level: int) -> str:
        """Compute the base package for a relative import."""
        parts = file_path.replace("/", ".").replace("\\", ".").rstrip(".py").split(".")
        # Level 1 = current package, level 2 = parent package, etc.
        base_parts = parts[: -(level)]
        return ".".join(base_parts) if base_parts else ""

    def _resolve_to_project_files(
        self,
        raw_imports: list[tuple[str, Optional[str]]],
        file_path: str,
        all_project_files: set[str],
    ) -> list[str]:
        """
        Convert module names to actual file paths within the project.

        Strategy:
        1. Convert module.path to module/path.py
        2. Check if that file exists in project files
        3. Also check __init__.py for package imports
        """
        resolved: list[str] = []

        for module_name, import_type in raw_imports:
            # Filter stdlib
            root_module = module_name.split(".")[0]
            if root_module in self.STDLIB_MODULES:
                continue

            # Try to resolve to a project file
            candidates = self._get_candidates(module_name)
            for candidate in candidates:
                # Check both with and without leading path separators
                for project_file in all_project_files:
                    if (
                        project_file.endswith(candidate)
                        or project_file == candidate
                    ):
                        # Don't add self-references
                        if project_file != file_path:
                            resolved.append(project_file)
                        break

        return list(set(resolved))  # Deduplicate

    def _get_candidates(self, module_name: str) -> list[str]:
        """Generate candidate file paths for a module name."""
        path = module_name.replace(".", "/")
        return [
            f"{path}.py",
            f"{path}/__init__.py",
        ]
