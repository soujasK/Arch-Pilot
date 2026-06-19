"""
JavaScript / TypeScript dependency extractors using regex-based parsing.

Design decision: Regex over a full JS/TS AST parser.
Why: Adding a full TS compiler as a Python dependency is heavy.
Regex covers ~95% of real-world import patterns adequately.
For the remaining 5% (dynamic imports, computed paths), we accept the miss.
"""

import re
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


class JavaScriptParser:
    """
    Extracts ES module and CommonJS dependencies from .js/.jsx files.
    """

    # ES Module imports
    ES_IMPORT_PATTERN = re.compile(
        r"""(?:import\s+(?:type\s+)?(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]|"""
        r"""export\s+(?:type\s+)?[\w{}\s*,]+\s+from\s+['"]([^'"]+)['"])""",
        re.MULTILINE,
    )

    # CommonJS require()
    REQUIRE_PATTERN = re.compile(
        r"""(?:require|import)\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        re.MULTILINE,
    )

    # Dynamic import()
    DYNAMIC_IMPORT_PATTERN = re.compile(
        r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
        re.MULTILINE,
    )

    def extract_imports(
        self,
        source_code: str,
        file_path: str,
        all_project_files: set[str],
    ) -> list[str]:
        """Extract and resolve JS/JSX imports."""
        raw_imports = self._collect_raw_imports(source_code)
        return self._resolve_to_project_files(raw_imports, file_path, all_project_files)

    def _collect_raw_imports(self, source: str) -> list[str]:
        imports: list[str] = []

        for pattern in [self.ES_IMPORT_PATTERN, self.REQUIRE_PATTERN, self.DYNAMIC_IMPORT_PATTERN]:
            for match in pattern.finditer(source):
                # Some groups may be None depending on which alternative matched
                for group in match.groups():
                    if group:
                        imports.append(group)

        return list(set(imports))

    def _is_external(self, import_path: str) -> bool:
        """External imports start with a package name, not ./ or ../"""
        return not import_path.startswith(".")

    def _resolve_to_project_files(
        self,
        raw_imports: list[str],
        file_path: str,
        all_project_files: set[str],
    ) -> list[str]:
        resolved: list[str] = []
        file_dir = str(Path(file_path).parent)

        for import_path in raw_imports:
            if self._is_external(import_path):
                continue  # Skip node_modules / package imports

            candidates = self._get_candidates(import_path, file_path)
            for candidate in candidates:
                if candidate in all_project_files and candidate != file_path:
                    resolved.append(candidate)
                    break

        return list(set(resolved))

    def _get_candidates(self, import_path: str, file_path: str) -> list[str]:
        """
        Resolve a relative import path to candidate absolute paths.
        """
        base_dir = Path(file_path).parent
        raw_path = (base_dir / import_path).resolve()

        # Normalize: remove the leading / to get relative-to-root path
        # We need paths relative to repo root for comparison
        str_path = str(raw_path)

        # Try common JS resolution order
        candidates = []
        extensions = [".js", ".jsx", ".ts", ".tsx", ".mjs"]

        # Direct match
        candidates.append(import_path.lstrip("./"))

        # With extensions
        for ext in extensions:
            candidates.append(f"{import_path.lstrip('./')}{ext}")
            candidates.append(f"{import_path.lstrip('./')}/index{ext}")

        # Normalize with Path arithmetic (handles ../ etc.)
        file_path_obj = Path(file_path)
        for suffix in ["", ".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.ts"]:
            try:
                resolved = str(
                    (file_path_obj.parent / (import_path + suffix)).resolve()
                ).lstrip("/")
                candidates.append(resolved)
            except Exception:
                pass

        return candidates


class TypeScriptParser(JavaScriptParser):
    """
    Extends JS parser with TypeScript-specific patterns.

    Adds:
    - `import type` statements
    - Triple-slash references
    - Path alias resolution (basic @ support)
    """

    TS_TRIPLE_SLASH = re.compile(
        r'///\s*<reference\s+path=["\']([^"\']+)["\']',
        re.MULTILINE,
    )

    def extract_imports(
        self,
        source_code: str,
        file_path: str,
        all_project_files: set[str],
    ) -> list[str]:
        # Get base JS imports
        resolved = super().extract_imports(source_code, file_path, all_project_files)

        # Add triple-slash references
        triple_slash_paths = [
            m.group(1) for m in self.TS_TRIPLE_SLASH.finditer(source_code)
        ]
        if triple_slash_paths:
            additional = self._resolve_to_project_files(
                triple_slash_paths, file_path, all_project_files
            )
            resolved.extend(additional)

        return list(set(resolved))

    def _is_external(self, import_path: str) -> bool:
        """Also filter out @types/* and common TS aliases."""
        if import_path.startswith("@types/"):
            return True
        # @ imports could be aliases (like @/components) — treat as internal
        if import_path.startswith("@/"):
            return False
        return super()._is_external(import_path)
