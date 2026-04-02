"""
Codebase scanner — detects languages, frameworks, imports, and project structure.

Builds a dependency graph so the migration planner knows the order to transform files.
"""

from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    """Metadata about a single source file."""
    path: Path
    language: str
    lines: int
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    frameworks: Set[str] = field(default_factory=set)
    complexity: int = 0  # rough cyclomatic estimate


@dataclass
class ProjectProfile:
    """Aggregated view of the entire codebase."""
    root: Path
    files: Dict[Path, FileInfo] = field(default_factory=dict)
    languages: Dict[str, int] = field(default_factory=dict)  # lang -> file count
    frameworks: Set[str] = field(default_factory=set)
    dependency_graph: Dict[Path, Set[Path]] = field(default_factory=dict)
    entry_points: List[Path] = field(default_factory=list)
    total_lines: int = 0


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

EXTENSION_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".go": "go",
    ".rb": "ruby",
    ".rs": "rust",
}

IGNORE_DIRS = {
    "__pycache__", "node_modules", ".git", ".tox", ".mypy_cache",
    "dist", "build", ".eggs", ".venv", "venv", "env",
}


# ---------------------------------------------------------------------------
# Python import parser
# ---------------------------------------------------------------------------

def _parse_python_imports(filepath: Path) -> List[str]:
    """Extract import names from a Python file using the ast module."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []

    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module.split(".")[0])
    return imports


# ---------------------------------------------------------------------------
# JS/TS import parser
# ---------------------------------------------------------------------------

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]"""
    r"""|require\s*\(\s*['"]([^'"]+)['"]\s*\))""",
    re.MULTILINE,
)


def _parse_js_imports(filepath: Path) -> List[str]:
    """Extract import/require targets from a JS/TS file."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    imports: List[str] = []
    for match in _JS_IMPORT_RE.finditer(text):
        target = match.group(1) or match.group(2)
        if target:
            # strip relative path prefixes
            if target.startswith("."):
                imports.append(target)
            else:
                imports.append(target.split("/")[0])
    return imports


# ---------------------------------------------------------------------------
# Framework detection
# ---------------------------------------------------------------------------

_FRAMEWORK_SIGNALS: Dict[str, Dict[str, List[str]]] = {
    "python": {
        "django": ["django", "DJANGO_SETTINGS_MODULE", "models.Model", "HttpResponse"],
        "flask": ["flask", "Flask(", "@app.route"],
        "fastapi": ["fastapi", "FastAPI(", "APIRouter"],
        "pytest": ["pytest", "conftest"],
        "sqlalchemy": ["sqlalchemy", "declarative_base"],
        "pandas": ["pandas", "DataFrame"],
    },
    "javascript": {
        "react": ["react", "React.", "jsx", "useState", "useEffect"],
        "nextjs": ["next", "next/router", "next/link"],
        "express": ["express", "app.get(", "app.post("],
        "vue": ["vue", "createApp", "defineComponent"],
        "angular": ["@angular/core", "Component(", "NgModule"],
    },
    "typescript": {
        "react": ["react", "React.", "jsx", "useState", "useEffect"],
        "nextjs": ["next", "next/router", "next/link"],
        "express": ["express", "app.get(", "app.post("],
        "vue": ["vue", "createApp", "defineComponent"],
        "angular": ["@angular/core", "Component(", "NgModule"],
        "nestjs": ["@nestjs/common", "@nestjs/core"],
    },
}


def _detect_frameworks(filepath: Path, language: str) -> Set[str]:
    """Heuristically detect frameworks used in a file."""
    try:
        text = filepath.read_text(encoding="utf-8").lower()
    except UnicodeDecodeError:
        return set()

    detected: Set[str] = set()
    signals = _FRAMEWORK_SIGNALS.get(language, {})
    for framework, patterns in signals.items():
        for pat in patterns:
            if pat.lower() in text:
                detected.add(framework)
                break
    return detected


# ---------------------------------------------------------------------------
# Complexity estimate
# ---------------------------------------------------------------------------

_BRANCH_KEYWORDS = re.compile(
    r"\b(if|elif|else|for|while|case|catch|&&|\?\?|\|\||\?)\b"
)


def _estimate_complexity(filepath: Path) -> int:
    """Quick cyclomatic-complexity proxy based on branch keywords."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 1
    return 1 + len(_BRANCH_KEYWORDS.findall(text))


# ---------------------------------------------------------------------------
# Main scanner
# ---------------------------------------------------------------------------

class CodebaseScanner:
    """Walk a project tree and build a ProjectProfile."""

    def __init__(self, root: str | Path, *, exclude: Optional[Set[str]] = None):
        self.root = Path(root).resolve()
        self.exclude = (exclude or set()) | IGNORE_DIRS

    # ---- public API -------------------------------------------------------

    def scan(self) -> ProjectProfile:
        """Run a full scan and return the project profile."""
        profile = ProjectProfile(root=self.root)

        for filepath in self._iter_source_files():
            rel = filepath.relative_to(self.root)
            lang = EXTENSION_MAP.get(filepath.suffix, "unknown")
            if lang == "unknown":
                continue

            imports = (
                _parse_python_imports(filepath)
                if lang == "python"
                else _parse_js_imports(filepath)
            )
            frameworks = _detect_frameworks(filepath, lang)
            complexity = _estimate_complexity(filepath)

            try:
                lines = len(filepath.read_text(encoding="utf-8").splitlines())
            except UnicodeDecodeError:
                lines = 0

            info = FileInfo(
                path=rel,
                language=lang,
                lines=lines,
                imports=imports,
                frameworks=frameworks,
                complexity=complexity,
            )
            profile.files[rel] = info
            profile.languages[lang] = profile.languages.get(lang, 0) + 1
            profile.frameworks |= frameworks
            profile.total_lines += lines

        profile.dependency_graph = self._build_dep_graph(profile)
        profile.entry_points = self._find_entry_points(profile)
        return profile

    # ---- internals --------------------------------------------------------

    def _iter_source_files(self):
        """Yield all source files under *self.root*, skipping ignored dirs."""
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in self.exclude]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix in EXTENSION_MAP:
                    yield p

    def _build_dep_graph(self, profile: ProjectProfile) -> Dict[Path, Set[Path]]:
        """Map each file to the set of local files it depends on."""
        # build lookup: module name -> file path
        module_map: Dict[str, Path] = {}
        for rel, info in profile.files.items():
            # treat file stem as module name
            stem = rel.stem
            module_map[stem] = rel

        graph: Dict[Path, Set[Path]] = {}
        for rel, info in profile.files.items():
            deps: Set[Path] = set()
            for imp in info.imports:
                if imp in module_map and module_map[imp] != rel:
                    deps.add(module_map[imp])
            graph[rel] = deps
        return graph

    def _find_entry_points(self, profile: ProjectProfile) -> List[Path]:
        """Heuristically identify entry-point files."""
        candidates = {"main.py", "app.py", "manage.py", "index.js", "index.ts", "server.js"}
        eps: List[Path] = []
        for rel in profile.files:
            if rel.name in candidates:
                eps.append(rel)
        return eps


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------

def scan_and_print(root: str = ".") -> ProjectProfile:
    """Convenience: scan and print a summary to stdout."""
    scanner = CodebaseScanner(root)
    profile = scanner.scan()

    print(f"\n  Project root : {profile.root}")
    print(f"  Total files  : {len(profile.files)}")
    print(f"  Total lines  : {profile.total_lines}")
    print(f"  Languages    : {profile.languages}")
    print(f"  Frameworks   : {profile.frameworks or '{none detected}'}")
    print(f"  Entry points : {profile.entry_points or '{none detected}'}")
    print()
    return profile
