"""
Migration reporter — generates diffs, summaries, and HTML/Markdown reports.
"""

from __future__ import annotations

import difflib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from codemorph.migrator import TransformResult
from codemorph.validators import ValidationReport


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class FileReport:
    """Report for a single file."""
    source: Optional[str]
    target: str
    success: bool
    patterns: List[str] = field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0
    lines_unchanged: int = 0
    diff: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class MigrationReport:
    """Full migration report."""
    project_name: str = ""
    source_lang: str = ""
    target_lang: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    files: List[FileReport] = field(default_factory=list)
    validation: Optional[ValidationReport] = None
    total_files: int = 0
    successful_files: int = 0
    failed_files: int = 0
    total_lines_added: int = 0
    total_lines_removed: int = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def success_rate(self) -> float:
        if self.total_files == 0:
            return 0.0
        return self.successful_files / self.total_files


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------

class MigrationReporter:
    """Build reports from TransformResult lists and ValidationReports."""

    def __init__(self, *, project_name: str = ""):
        self.project_name = project_name

    # ---- public -----------------------------------------------------------

    def build_report(
        self,
        results: List[TransformResult],
        validation: Optional[ValidationReport] = None,
        *,
        source_lang: str = "python",
        target_lang: str = "typescript",
    ) -> MigrationReport:
        """Build a full report from transform results."""
        report = MigrationReport(
            project_name=self.project_name,
            source_lang=source_lang,
            target_lang=target_lang,
            start_time=time.time(),
            validation=validation,
        )

        for r in results:
            diff = self._compute_diff(r.original, r.transformed, r.source, r.target)
            added, removed, unchanged = self._count_lines(r.original, r.transformed)

            file_report = FileReport(
                source=str(r.source) if r.source else None,
                target=str(r.target),
                success=r.success,
                patterns=r.patterns_applied,
                lines_added=added,
                lines_removed=removed,
                lines_unchanged=unchanged,
                diff=diff,
                errors=r.errors,
                warnings=r.warnings,
            )
            report.files.append(file_report)
            report.total_files += 1
            if r.success:
                report.successful_files += 1
            else:
                report.failed_files += 1
            report.total_lines_added += added
            report.total_lines_removed += removed

        report.end_time = time.time()
        return report

    # ---- formats ----------------------------------------------------------

    def to_markdown(self, report: MigrationReport) -> str:
        """Generate a Markdown report."""
        lines: List[str] = []
        lines.append(f"# CodeMorph Migration Report: {report.project_name}")
        lines.append("")
        lines.append(f"**{report.source_lang} → {report.target_lang}**")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"| Metric | Value |")
        lines.append(f"|--------|-------|")
        lines.append(f"| Files processed | {report.total_files} |")
        lines.append(f"| Successful | {report.successful_files} |")
        lines.append(f"| Failed | {report.failed_files} |")
        lines.append(f"| Success rate | {report.success_rate:.0%} |")
        lines.append(f"| Lines added | +{report.total_lines_added} |")
        lines.append(f"| Lines removed | -{report.total_lines_removed} |")
        lines.append(f"| Duration | {report.duration:.1f}s |")
        lines.append("")

        # per-file details
        lines.append("## File Details")
        lines.append("")
        for f in report.files:
            icon = "✅" if f.success else "❌"
            lines.append(f"### {icon} {f.target}")
            if f.source:
                lines.append(f"Source: `{f.source}`")
            lines.append("")
            if f.patterns:
                lines.append(f"Patterns: {', '.join(f.patterns)}")
            lines.append(f"Lines: +{f.lines_added} / -{f.lines_removed} / ={f.lines_unchanged}")
            lines.append("")

            if f.errors:
                lines.append("**Errors:**")
                for e in f.errors:
                    lines.append(f"- {e}")
                lines.append("")

            if f.warnings:
                lines.append("**Warnings:**")
                for w in f.warnings:
                    lines.append(f"- {w}")
                lines.append("")

            if f.diff:
                lines.append("<details>")
                lines.append("<summary>Diff</summary>")
                lines.append("")
                lines.append("```diff")
                lines.append(f.diff)
                lines.append("```")
                lines.append("</details>")
                lines.append("")

        # validation
        if report.validation:
            lines.append("## Validation")
            lines.append("")
            lines.append(f"- Files checked: {report.validation.files_checked}")
            lines.append(f"- Errors: {len(report.validation.errors)}")
            lines.append(f"- Warnings: {len(report.validation.warnings)}")
            lines.append(f"- Result: {'✅ PASS' if report.validation.passed else '❌ FAIL'}")
            lines.append("")

        return "\n".join(lines)

    def to_json(self, report: MigrationReport) -> str:
        """Generate a JSON report."""
        data: Dict[str, Any] = {
            "project": report.project_name,
            "source_lang": report.source_lang,
            "target_lang": report.target_lang,
            "duration_seconds": round(report.duration, 2),
            "total_files": report.total_files,
            "successful_files": report.successful_files,
            "failed_files": report.failed_files,
            "success_rate": round(report.success_rate, 3),
            "lines_added": report.total_lines_added,
            "lines_removed": report.total_lines_removed,
            "files": [
                {
                    "source": f.source,
                    "target": f.target,
                    "success": f.success,
                    "patterns": f.patterns,
                    "lines_added": f.lines_added,
                    "lines_removed": f.lines_removed,
                    "errors": f.errors,
                    "warnings": f.warnings,
                }
                for f in report.files
            ],
        }
        if report.validation:
            data["validation"] = {
                "passed": report.validation.passed,
                "files_checked": report.validation.files_checked,
                "errors": len(report.validation.errors),
                "warnings": len(report.validation.warnings),
            }
        return json.dumps(data, indent=2)

    def to_terminal(self, report: MigrationReport) -> str:
        """Generate a compact terminal-friendly report."""
        lines: List[str] = []
        lines.append("")
        lines.append("  CodeMorph Migration Report")
        lines.append("=" * 55)
        lines.append(f"  Project  : {report.project_name}")
        lines.append(f"  Direction: {report.source_lang} → {report.target_lang}")
        lines.append(f"  Duration : {report.duration:.1f}s")
        lines.append("")
        lines.append(f"  Files : {report.successful_files}/{report.total_files} succeeded ({report.success_rate:.0%})")
        lines.append(f"  Lines : +{report.total_lines_added} / -{report.total_lines_removed}")
        lines.append("")

        for f in report.files:
            icon = "✓" if f.success else "✗"
            patterns = f" [{', '.join(f.patterns)}]" if f.patterns else ""
            lines.append(f"  {icon} {f.target}{patterns}")
            for e in f.errors:
                lines.append(f"    ✗ {e}")

        if report.validation:
            v = report.validation
            lines.append("")
            lines.append(f"  Validation: {'PASS' if v.passed else 'FAIL'}")
            lines.append(f"    Errors  : {len(v.errors)}")
            lines.append(f"    Warnings: {len(v.warnings)}")

        lines.append("")
        return "\n".join(lines)

    # ---- internals --------------------------------------------------------

    def _compute_diff(
        self, original: str, transformed: str,
        source: Optional[Path], target: Path,
    ) -> str:
        """Unified diff between original and transformed."""
        src_name = str(source) if source else "/dev/null"
        tgt_name = str(target)
        diff = difflib.unified_diff(
            original.splitlines(keepends=True),
            transformed.splitlines(keepends=True),
            fromfile=src_name,
            tofile=tgt_name,
        )
        return "".join(diff)

    def _count_lines(self, original: str, transformed: str) -> tuple:
        """Count added, removed, and unchanged lines."""
        orig_lines = set(original.splitlines())
        trans_lines = set(transformed.splitlines())
        added = len(trans_lines - orig_lines)
        removed = len(orig_lines - trans_lines)
        unchanged = len(orig_lines & trans_lines)
        return added, removed, unchanged
