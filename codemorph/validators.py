"""
Post-migration validators — verify syntax, type-correctness, and test pass rates.

Run these after TransformEngine finishes to catch regressions before you commit.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class Severity(Enum):
    ERROR = auto()
    WARNING = auto()
    INFO = auto()


@dataclass
class ValidationIssue:
    """A single issue found by a validator."""
    severity: Severity
    message: str
    rule: str = ""
    file: Optional[Path] = None
    line: Optional[int] = None
    column: Optional[int] = None


@dataclass
class ValidationReport:
    """Aggregated report from all validators."""
    issues: List[ValidationIssue] = field(default_factory=list)
    files_checked: int = 0
    passed: bool = True

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    def summary(self) -> str:
        lines = [
            "Validation Report",
            "=" * 50,
            f"  Files checked : {self.files_checked}",
            f"  Errors        : {len(self.errors)}",
            f"  Warnings      : {len(self.warnings)}",
            f"  Overall       : {'PASS' if self.passed else 'FAIL'}",
        ]
        for issue in self.issues:
            icon = {"ERROR": "✗", "WARNING": "⚠", "INFO": "·"}.get(issue.severity.name, "?")
            loc = str(issue.file) if issue.file else "<unknown>"
            if issue.line:
                loc += f":{issue.line}"
            lines.append(f"  {icon} [{issue.rule}] {loc} — {issue.message}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

class SyntaxValidator:
    """Check that generated files have valid syntax."""

    def validate(self, files: Dict[Path, str]) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        for path, content in files.items():
            suffix = path.suffix.lower()
            if suffix == ".py":
                issues.extend(self._check_python(path, content))
            elif suffix in (".js", ".mjs", ".cjs"):
                issues.extend(self._check_js(path, content))
            elif suffix in (".ts", ".tsx"):
                issues.extend(self._check_ts(path, content))
        return issues

    def _check_python(self, path: Path, content: str) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        try:
            ast.parse(content)
        except SyntaxError as exc:
            issues.append(ValidationIssue(
                file=path, line=exc.lineno, column=exc.offset,
                severity=Severity.ERROR, message=str(exc.msg), rule="syntax/python"
            ))
        return issues

    def _check_js(self, path: Path, content: str) -> List[ValidationIssue]:
        """Best-effort JS syntax check via Node.js."""
        issues: List[ValidationIssue] = []
        try:
            result = subprocess.run(
                ["node", "--check", str(path)],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                issues.append(ValidationIssue(
                    file=path, severity=Severity.ERROR,
                    message=result.stderr.strip()[:200], rule="syntax/javascript"
                ))
        except FileNotFoundError:
            issues.append(ValidationIssue(
                file=path, severity=Severity.WARNING,
                message="Node.js not installed — skipping JS syntax check",
                rule="syntax/javascript"
            ))
        except subprocess.TimeoutExpired:
            issues.append(ValidationIssue(
                file=path, severity=Severity.WARNING,
                message="Syntax check timed out", rule="syntax/javascript"
            ))
        return issues

    def _check_ts(self, path: Path, content: str) -> List[ValidationIssue]:
        """Best-effort TS syntax check via tsc."""
        issues: List[ValidationIssue] = []
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "--pretty", "false", str(path)],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                for line in result.stdout.strip().splitlines()[:20]:
                    issues.append(ValidationIssue(
                        file=path, severity=Severity.ERROR,
                        message=line[:200], rule="syntax/typescript"
                    ))
        except FileNotFoundError:
            issues.append(ValidationIssue(
                file=path, severity=Severity.WARNING,
                message="tsc not installed — skipping TS type check",
                rule="syntax/typescript"
            ))
        except subprocess.TimeoutExpired:
            issues.append(ValidationIssue(
                file=path, severity=Severity.WARNING,
                message="TypeScript check timed out", rule="syntax/typescript"
            ))
        return issues


class TestValidator:
    """Run the project's test suite and report results."""

    def validate(self, project_dir: Path) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        # detect test runner
        if (project_dir / "pytest.ini").exists() or (project_dir / "pyproject.toml").exists():
            return self._run_pytest(project_dir)
        if (project_dir / "package.json").exists():
            return self._run_jest(project_dir)

        issues.append(ValidationIssue(
            file=None, severity=Severity.WARNING,
            message="No test runner detected — skipping test validation",
            rule="tests/runner"
        ))
        return issues

    def _run_pytest(self, project_dir: Path) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--tb=short", "-q"],
                capture_output=True, text=True, timeout=120, cwd=project_dir,
            )
            if result.returncode != 0:
                # parse failures
                for line in result.stdout.splitlines():
                    if "FAILED" in line:
                        issues.append(ValidationIssue(
                            file=None, severity=Severity.ERROR,
                            message=line.strip(), rule="tests/pytest"
                        ))
                if not issues:
                    issues.append(ValidationIssue(
                        file=None, severity=Severity.ERROR,
                        message=f"pytest exited with code {result.returncode}",
                        rule="tests/pytest"
                    ))
        except FileNotFoundError:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="pytest not found — skipping", rule="tests/pytest"
            ))
        except subprocess.TimeoutExpired:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="pytest timed out", rule="tests/pytest"
            ))
        return issues

    def _run_jest(self, project_dir: Path) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        try:
            result = subprocess.run(
                ["npx", "jest", "--json", "--forceExit"],
                capture_output=True, text=True, timeout=120, cwd=project_dir,
            )
            if result.returncode != 0:
                try:
                    data = json.loads(result.stdout)
                    for suite in data.get("testResults", []):
                        for test in suite.get("assertionResults", []):
                            if test.get("status") == "failed":
                                msg = "; ".join(test.get("failureMessages", ["unknown failure"]))
                                issues.append(ValidationIssue(
                                    file=Path(suite.get("name", "")),
                                    severity=Severity.ERROR,
                                    message=msg[:200], rule="tests/jest"
                                ))
                except (json.JSONDecodeError, KeyError):
                    issues.append(ValidationIssue(
                        file=None, severity=Severity.ERROR,
                        message=result.stderr[:200] or "Jest failed", rule="tests/jest"
                    ))
        except FileNotFoundError:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="jest not found — skipping", rule="tests/jest"
            ))
        except subprocess.TimeoutExpired:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="jest timed out", rule="tests/jest"
            ))
        return issues


class TypeValidator:
    """Run type checkers (mypy for Python, tsc for TypeScript)."""

    def validate(self, project_dir: Path, language: str) -> List[ValidationIssue]:
        if language == "python":
            return self._run_mypy(project_dir)
        if language in ("typescript", "javascript"):
            return self._run_tsc(project_dir)
        return []

    def _run_mypy(self, project_dir: Path) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        try:
            result = subprocess.run(
                [sys.executable, "-m", "mypy", "--ignore-missing-imports", "."],
                capture_output=True, text=True, timeout=120, cwd=project_dir,
            )
            for line in result.stdout.splitlines():
                if ": error:" in line:
                    parts = line.split(":", 3)
                    fp = Path(parts[0]) if len(parts) > 0 else None
                    ln = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else None
                    msg = parts[3].strip() if len(parts) > 3 else line
                    issues.append(ValidationIssue(
                        file=fp, line=ln, severity=Severity.ERROR,
                        message=msg, rule="types/mypy"
                    ))
                elif ": warning:" in line:
                    parts = line.split(":", 3)
                    fp = Path(parts[0]) if len(parts) > 0 else None
                    ln = int(parts[1]) if len(parts) > 1 and parts[1].strip().isdigit() else None
                    msg = parts[3].strip() if len(parts) > 3 else line
                    issues.append(ValidationIssue(
                        file=fp, line=ln, severity=Severity.WARNING,
                        message=msg, rule="types/mypy"
                    ))
        except FileNotFoundError:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="mypy not found — skipping", rule="types/mypy"
            ))
        except subprocess.TimeoutExpired:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="mypy timed out", rule="types/mypy"
            ))
        return issues

    def _run_tsc(self, project_dir: Path) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "--pretty", "false"],
                capture_output=True, text=True, timeout=60, cwd=project_dir,
            )
            for line in result.stdout.splitlines():
                parts = line.split(":", 3)
                if len(parts) >= 3:
                    fp = Path(parts[0]) if parts[0].strip() else None
                    ln = int(parts[1]) if parts[1].strip().isdigit() else None
                    msg = parts[3].strip() if len(parts) > 3 else line
                    issues.append(ValidationIssue(
                        file=fp, line=ln, severity=Severity.ERROR,
                        message=msg, rule="types/tsc"
                    ))
        except FileNotFoundError:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="tsc not found — skipping", rule="types/tsc"
            ))
        except subprocess.TimeoutExpired:
            issues.append(ValidationIssue(
                file=None, severity=Severity.WARNING,
                message="tsc timed out", rule="types/tsc"
            ))
        return issues


# ---------------------------------------------------------------------------
# Aggregate validator
# ---------------------------------------------------------------------------

class PostMigrationValidator:
    """Run all validators and produce a combined report."""

    def __init__(self, project_dir: Path):
        self.project_dir = Path(project_dir)
        self.syntax = SyntaxValidator()
        self.tests = TestValidator()
        self.types = TypeValidator()

    def validate(
        self,
        files: Optional[Dict[Path, str]] = None,
        language: str = "typescript",
    ) -> ValidationReport:
        """Run all validators. If files dict is provided, check syntax on those."""
        report = ValidationReport()

        # Syntax
        if files:
            syntax_issues = self.syntax.validate(files)
            report.issues.extend(syntax_issues)
            report.files_checked += len(files)
        else:
            # scan the output directory
            files_found = self._collect_files(language)
            contents: Dict[Path, str] = {}
            for f in files_found:
                try:
                    contents[f] = f.read_text(encoding="utf-8")
                except Exception:
                    pass
            syntax_issues = self.syntax.validate(contents)
            report.issues.extend(syntax_issues)
            report.files_checked += len(contents)

        # Types
        type_issues = self.types.validate(self.project_dir, language)
        report.issues.extend(type_issues)

        # Tests
        test_issues = self.tests.validate(self.project_dir)
        report.issues.extend(test_issues)

        report.passed = all(i.severity != Severity.ERROR for i in report.issues)
        return report

    def _collect_files(self, language: str) -> List[Path]:
        ext_map = {
            "python": ".py",
            "javascript": ".js",
            "typescript": ".ts",
        }
        ext = ext_map.get(language, ".ts")
        return sorted(self.project_dir.rglob(f"*{ext}"))
