"""
Transform engine — converts files one at a time with full-codebase context.

Each file is transformed in the context of the entire project: the engine
provides the scanner's dependency graph, the planner's pattern list, and the
already-transformed output of upstream dependencies.
"""

from __future__ import annotations

import ast
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from codemorph.config import MigrationConfig
from codemorph.planner import MigrationPlan, MigrationStep, StepKind
from codemorph.patterns import PatternRegistry
from codemorph.scanner import CodebaseScanner, ProjectProfile


# ---------------------------------------------------------------------------
# Transformation result
# ---------------------------------------------------------------------------

@dataclass
class TransformResult:
    """Outcome of transforming a single file."""
    source: Optional[Path]
    target: Path
    success: bool
    original: str = ""
    transformed: str = ""
    patterns_applied: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class MigrationContext:
    """Shared context available to every transformation."""
    config: MigrationConfig
    profile: ProjectProfile
    transformed_files: Dict[Path, str] = field(default_factory=dict)  # already done
    global_symbols: Dict[str, str] = field(default_factory=dict)      # name -> file


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

class TransformEngine:
    """Execute a MigrationPlan, transforming files in dependency order."""

    def __init__(
        self,
        plan: MigrationPlan,
        config: MigrationConfig,
        profile: ProjectProfile,
        *,
        pattern_registry: Optional[PatternRegistry] = None,
    ):
        self.plan = plan
        self.config = config
        self.profile = profile
        self.registry = pattern_registry or PatternRegistry()
        self.context = MigrationContext(config=config, profile=profile)
        self.results: List[TransformResult] = []

    # ---- public -----------------------------------------------------------

    def run(self, *, dry_run: bool = False) -> List[TransformResult]:
        """Execute all steps in the plan. Returns list of results."""
        self.results = []
        for step in self.plan.steps:
            if step.kind == StepKind.TRANSFORM:
                result = self._transform_file(step, dry_run=dry_run)
            elif step.kind == StepKind.CREATE_FILE:
                result = self._create_config(step, dry_run=dry_run)
            elif step.kind == StepKind.RUN_VALIDATOR:
                result = self._run_validation(step)
            else:
                result = TransformResult(
                    source=step.source, target=step.target or Path("unknown"),
                    success=True, transformed="(skipped)"
                )
            self.results.append(result)
        return self.results

    def get_summary(self) -> str:
        """Return a human-readable summary of all results."""
        lines = ["Migration Results:", "=" * 60]
        ok = sum(1 for r in self.results if r.success)
        fail = len(self.results) - ok
        lines.append(f"  Succeeded : {ok}")
        lines.append(f"  Failed    : {fail}")
        lines.append("")
        for r in self.results:
            icon = "✓" if r.success else "✗"
            src = str(r.source) if r.source else "(generated)"
            lines.append(f"  {icon} {src} -> {r.target}")
            if r.patterns_applied:
                lines.append(f"    patterns: {', '.join(r.patterns_applied)}")
            for e in r.errors:
                lines.append(f"    error: {e}")
            for w in r.warnings:
                lines.append(f"    warning: {w}")
        return "\n".join(lines)

    # ---- file transformation ----------------------------------------------

    def _transform_file(self, step: MigrationStep, *, dry_run: bool) -> TransformResult:
        """Transform a single source file."""
        src_path = self.config.source_dir / step.source if step.source else None
        tgt_path = self.config.output_dir / step.target if step.target and self.config.output_dir else Path(step.target or "unknown")

        if src_path is None or not src_path.exists():
            return TransformResult(
                source=step.source, target=tgt_path,
                success=False, errors=[f"Source file not found: {src_path}"]
            )

        try:
            original = src_path.read_text(encoding="utf-8")
        except Exception as exc:
            return TransformResult(
                source=step.source, target=tgt_path,
                success=False, errors=[f"Read error: {exc}"]
            )

        transformed = original
        patterns_applied: List[str] = []
        warnings: List[str] = []

        # Apply each pattern in order
        for pattern_name in step.patterns:
            pattern = self.registry.get(pattern_name)
            if pattern is None:
                warnings.append(f"Pattern '{pattern_name}' not found — skipped")
                continue

            try:
                result_text, applied = pattern.apply(
                    transformed,
                    source_lang=self.plan.source_lang,
                    target_lang=self.plan.target_lang,
                    context=self.context,
                )
                if applied:
                    transformed = result_text
                    patterns_applied.append(pattern_name)
            except Exception as exc:
                warnings.append(f"Pattern '{pattern_name}' failed: {exc}")

        # Write output
        if not dry_run and self.config.output_dir:
            tgt_path.parent.mkdir(parents=True, exist_ok=True)
            tgt_path.write_text(transformed, encoding="utf-8")

        # Track in context
        if step.target:
            self.context.transformed_files[step.target] = transformed

        return TransformResult(
            source=step.source,
            target=tgt_path,
            success=True,
            original=original,
            transformed=transformed,
            patterns_applied=patterns_applied,
            warnings=warnings,
        )

    # ---- config file generation -------------------------------------------

    def _create_config(self, step: MigrationStep, *, dry_run: bool) -> TransformResult:
        """Generate configuration files for the target ecosystem."""
        tgt_path = self.config.output_dir / step.target if step.target and self.config.output_dir else Path(step.target or "unknown")
        content = ""

        if step.target and step.target.name == "tsconfig.json":
            content = textwrap.dedent("""\
                {
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
                    "sourceMap": true
                  },
                  "include": ["src/**/*"],
                  "exclude": ["node_modules", "dist"]
                }
            """)
        elif step.target and step.target.name == "package.json":
            content = textwrap.dedent("""\
                {
                  "name": "migrated-project",
                  "version": "1.0.0",
                  "scripts": {
                    "build": "tsc",
                    "test": "jest",
                    "lint": "eslint src/"
                  },
                  "devDependencies": {
                    "typescript": "^5.3.0",
                    "@types/node": "^20.0.0",
                    "jest": "^29.0.0",
                    "@types/jest": "^29.0.0",
                    "eslint": "^8.0.0"
                  }
                }
            """)

        if not dry_run and self.config.output_dir:
            tgt_path.parent.mkdir(parents=True, exist_ok=True)
            tgt_path.write_text(content, encoding="utf-8")

        return TransformResult(
            source=None, target=tgt_path, success=True, transformed=content
        )

    # ---- validation stub --------------------------------------------------

    def _run_validation(self, step: MigrationStep) -> TransformResult:
        """Placeholder — delegates to PostMigrationValidator."""
        return TransformResult(
            source=None,
            target=Path("validation"),
            success=True,
            transformed="(validation delegated to PostMigrationValidator)",
        )
