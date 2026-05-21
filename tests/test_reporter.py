"""Tests for the migration reporter."""

from pathlib import Path

import pytest

from codemorph.migrator import TransformResult
from codemorph.reporter import FileReport, MigrationReporter, MigrationReport
from codemorph.validators import ValidationReport


@pytest.fixture
def sample_results() -> list:
    return [
        TransformResult(
            source=Path("main.py"),
            target=Path("main.ts"),
            success=True,
            original="def hello():\n    print('hello')\n",
            transformed="function hello() {\n    console.log('hello');\n}\n",
            patterns_applied=["python_to_js_base"],
        ),
        TransformResult(
            source=Path("utils.py"),
            target=Path("utils.ts"),
            success=True,
            original="import json\nx = None\n",
            transformed="// migrated: import json\nx = null\n",
            patterns_applied=["python_to_js_base"],
        ),
        TransformResult(
            source=Path("broken.py"),
            target=Path("broken.ts"),
            success=False,
            original="def broken(\n",
            transformed="",
            errors=["Syntax error in source file"],
        ),
    ]


class TestMigrationReporter:
    def test_build_report(self, sample_results):
        reporter = MigrationReporter(project_name="test-project")
        report = reporter.build_report(sample_results)

        assert report.total_files == 3
        assert report.successful_files == 2
        assert report.failed_files == 1
        assert report.project_name == "test-project"

    def test_markdown_output(self, sample_results):
        reporter = MigrationReporter(project_name="test")
        report = reporter.build_report(sample_results)
        md = reporter.to_markdown(report)

        assert "# CodeMorph Migration Report" in md
        assert "test" in md
        assert "main.ts" in md
        assert "```diff" in md

    def test_json_output(self, sample_results):
        reporter = MigrationReporter(project_name="test")
        report = reporter.build_report(sample_results)
        json_str = reporter.to_json(report)

        import json
        data = json.loads(json_str)
        assert data["project"] == "test"
        assert data["total_files"] == 3
        assert data["successful_files"] == 2

    def test_terminal_output(self, sample_results):
        reporter = MigrationReporter(project_name="test")
        report = reporter.build_report(sample_results)
        terminal = reporter.to_terminal(report)

        assert "CodeMorph Migration Report" in terminal
        assert "✓" in terminal
        assert "✗" in terminal

    def test_file_report_diff(self, sample_results):
        reporter = MigrationReporter()
        report = reporter.build_report(sample_results)

        main_report = next(f for f in report.files if f.target == "main.ts")
        assert main_report.lines_added > 0
        assert main_report.lines_removed > 0

    def test_empty_report(self):
        reporter = MigrationReporter()
        report = reporter.build_report([])
        assert report.total_files == 0
        assert report.success_rate == 0.0

    def test_with_validation(self, sample_results):
        reporter = MigrationReporter(project_name="test")
        validation = ValidationReport(files_checked=3, passed=True)
        report = reporter.build_report(sample_results, validation)

        assert report.validation is not None
        assert report.validation.passed is True
