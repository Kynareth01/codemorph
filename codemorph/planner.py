"""
Migration planner — decides the order and steps for transforming a codebase.

Given a ProjectProfile from the scanner, produces an ordered list of
MigrationStep objects that the TransformEngine can execute.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from codemorph.scanner import FileInfo, ProjectProfile


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class StepKind(Enum):
    """Types of migration steps."""
    TRANSFORM = auto()      # code transformation
    CREATE_FILE = auto()    # generate a new file (e.g. tsconfig.json)
    DELETE_FILE = auto()    # remove an obsolete source file
    RUN_VALIDATOR = auto()  # syntax / test / type check
    COPY = auto()           # unchanged file carried over as-is


@dataclass
class MigrationStep:
    """A single atomic action in the migration plan."""
    kind: StepKind
    source: Optional[Path] = None
    target: Optional[Path] = None
    description: str = ""
    dependencies: List[int] = field(default_factory=list)  # indices of prior steps
    priority: int = 0  # lower = earlier
    patterns: List[str] = field(default_factory=list)  # pattern names to apply


@dataclass
class MigrationPlan:
    """The complete ordered plan."""
    steps: List[MigrationStep] = field(default_factory=list)
    source_lang: str = "python"
    target_lang: str = "typescript"
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable overview."""
        lines = [f"Migration plan: {self.source_lang} -> {self.target_lang}"]
        lines.append(f"  Steps   : {len(self.steps)}")
        lines.append(f"  Warnings: {len(self.warnings)}")
        for i, step in enumerate(self.steps):
            deps = f" (after {step.dependencies})" if step.dependencies else ""
            lines.append(f"  [{i}] {step.kind.name}: {step.description}{deps}")
        for w in self.warnings:
            lines.append(f"  ⚠  {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extension mapping
# ---------------------------------------------------------------------------

_LANG_EXT = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
}

_TS_CONFIG_TEMPLATE = """{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "lib": ["ES2020"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
"""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class MigrationPlanner:
    """Build a MigrationPlan from a ProjectProfile."""

    def __init__(
        self,
        profile: ProjectProfile,
        source_lang: str = "python",
        target_lang: str = "typescript",
    ):
        self.profile = profile
        self.source_lang = source_lang
        self.target_lang = target_lang

    # ---- public -----------------------------------------------------------

    def plan(self) -> MigrationPlan:
        """Generate the full migration plan."""
        mp = MigrationPlan(
            source_lang=self.source_lang,
            target_lang=self.target_lang,
        )

        # 1. topological order based on dependency graph
        ordered = self._topo_sort()

        # 2. one transform step per source file
        src_ext = _LANG_EXT.get(self.source_lang, ".py")
        tgt_ext = _LANG_EXT.get(self.target_lang, ".ts")

        step_index: Dict[Path, int] = {}
        for rel in ordered:
            info = self.profile.files[rel]
            target_rel = rel.with_suffix(tgt_ext)

            idx = len(mp.steps)
            step_index[rel] = idx

            dep_indices = [
                step_index[d] for d in self.profile.dependency_graph.get(rel, set()) if d in step_index
            ]

            patterns = self._pick_patterns(info)

            mp.steps.append(MigrationStep(
                kind=StepKind.TRANSFORM,
                source=rel,
                target=target_rel,
                description=f"Transform {rel} ({info.language} -> {self.target_lang})",
                dependencies=dep_indices,
                priority=idx,
                patterns=patterns,
            ))

        # 3. generate config files for the target ecosystem
        if self.target_lang == "typescript":
            mp.steps.append(MigrationStep(
                kind=StepKind.CREATE_FILE,
                target=Path("tsconfig.json"),
                description="Generate tsconfig.json",
                priority=len(mp.steps),
            ))
            mp.steps.append(MigrationStep(
                kind=StepKind.CREATE_FILE,
                target=Path("package.json"),
                description="Generate package.json with TypeScript deps",
                priority=len(mp.steps),
            ))

        # 4. final validation pass
        mp.steps.append(MigrationStep(
            kind=StepKind.RUN_VALIDATOR,
            description="Run post-migration validation (syntax, types, tests)",
            priority=len(mp.steps),
        ))

        # 5. warnings for files with high complexity
        for rel, info in self.profile.files.items():
            if info.complexity > 30:
                mp.warnings.append(
                    f"{rel}: high complexity ({info.complexity}) — manual review recommended"
                )
            if not info.imports and info.language == "python":
                mp.warnings.append(f"{rel}: no imports detected — verify it's a standalone module")

        return mp

    # ---- internals --------------------------------------------------------

    def _topo_sort(self) -> List[Path]:
        """Topological sort of files so dependencies are processed first."""
        graph = self.profile.dependency_graph
        all_files = set(self.profile.files.keys())

        # Kahn's algorithm
        in_degree: Dict[Path, int] = {f: 0 for f in all_files}
        for deps in graph.values():
            for d in deps:
                if d in in_degree:
                    in_degree[d] += 1

        # min-heap by path name for determinism
        queue: List[Tuple[str, Path]] = []
        for f, deg in in_degree.items():
            if deg == 0:
                heapq.heappush(queue, (str(f), f))

        result: List[Path] = []
        while queue:
            _, node = heapq.heappop(queue)
            result.append(node)
            for dep_of in graph.get(node, set()):
                if dep_of in in_degree:
                    in_degree[dep_of] -= 1
                    if in_degree[dep_of] == 0:
                        heapq.heappush(queue, (str(dep_of), dep_of))

        if len(result) != len(all_files):
            # cycle detected — append remaining in alphabetical order
            remaining = sorted(all_files - set(result), key=str)
            result.extend(remaining)

        return result

    def _pick_patterns(self, info: FileInfo) -> List[str]:
        """Decide which transformation patterns to apply to a file."""
        patterns: List[str] = []

        # language-specific
        if info.language == "python":
            patterns.append("python_to_js_base")
            if "flask" in info.frameworks:
                patterns.append("flask_to_express")
            if "django" in info.frameworks:
                patterns.append("django_to_express")
            if "fastapi" in info.frameworks:
                patterns.append("fastapi_to_express")

        # general
        if self.target_lang == "typescript":
            patterns.append("add_type_annotations")

        return patterns
