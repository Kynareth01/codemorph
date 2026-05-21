"""Tests for the migration planner."""

from pathlib import Path

import pytest

from codemorph.planner import MigrationPlanner, MigrationPlan, StepKind
from codemorph.scanner import CodebaseScanner, ProjectProfile


@pytest.fixture
def multi_file_project(tmp_path: Path) -> Path:
    """Create a project with inter-file dependencies."""
    (tmp_path / "models.py").write_text(
        "class User:\n    def __init__(self, name):\n        self.name = name\n"
    )
    (tmp_path / "utils.py").write_text(
        "import json\n\ndef serialize(data):\n    return json.dumps(data)\n"
    )
    (tmp_path / "main.py").write_text(
        "from models import User\nfrom utils import serialize\n\n"
        "u = User('Alice')\nprint(serialize(u))\n"
    )
    return tmp_path


class TestMigrationPlanner:
    def test_basic_plan(self, multi_file_project: Path):
        scanner = CodebaseScanner(multi_file_project)
        profile = scanner.scan()
        planner = MigrationPlanner(profile)
        plan = planner.plan()

        assert isinstance(plan, MigrationPlan)
        assert len(plan.steps) > 0
        assert plan.source_lang == "python"
        assert plan.target_lang == "typescript"

    def test_dependency_ordering(self, multi_file_project: Path):
        scanner = CodebaseScanner(multi_file_project)
        profile = scanner.scan()
        planner = MigrationPlanner(profile)
        plan = planner.plan()

        # Find the indices of models.py and main.py
        models_idx = None
        main_idx = None
        for i, step in enumerate(plan.steps):
            if step.source == Path("models.py"):
                models_idx = i
            if step.source == Path("main.py"):
                main_idx = i

        assert models_idx is not None
        assert main_idx is not None
        # models.py should come before main.py
        assert models_idx < main_idx

    def test_transform_steps_have_patterns(self, multi_file_project: Path):
        scanner = CodebaseScanner(multi_file_project)
        profile = scanner.scan()
        planner = MigrationPlanner(profile)
        plan = planner.plan()

        for step in plan.steps:
            if step.kind == StepKind.TRANSFORM:
                assert len(step.patterns) > 0
                assert "python_to_js_base" in step.patterns

    def test_tsconfig_generated_for_typescript(self, multi_file_project: Path):
        scanner = CodebaseScanner(multi_file_project)
        profile = scanner.scan()
        planner = MigrationPlanner(profile, target_lang="typescript")
        plan = planner.plan()

        tsconfig_steps = [s for s in plan.steps if s.target and s.target.name == "tsconfig.json"]
        assert len(tsconfig_steps) == 1

    def test_no_tsconfig_for_javascript(self, multi_file_project: Path):
        scanner = CodebaseScanner(multi_file_project)
        profile = scanner.scan()
        planner = MigrationPlanner(profile, target_lang="javascript")
        plan = planner.plan()

        tsconfig_steps = [s for s in plan.steps if s.target and s.target.name == "tsconfig.json"]
        assert len(tsconfig_steps) == 0

    def test_validation_step_always_present(self, multi_file_project: Path):
        scanner = CodebaseScanner(multi_file_project)
        profile = scanner.scan()
        planner = MigrationPlanner(profile)
        plan = planner.plan()

        val_steps = [s for s in plan.steps if s.kind == StepKind.RUN_VALIDATOR]
        assert len(val_steps) == 1

    def test_summary(self, multi_file_project: Path):
        scanner = CodebaseScanner(multi_file_project)
        profile = scanner.scan()
        planner = MigrationPlanner(profile)
        plan = planner.plan()

        summary = plan.summary()
        assert "Migration plan" in summary
        assert "python" in summary
        assert "typescript" in summary

    def test_high_complexity_warning(self, tmp_path: Path):
        # Create a file with many branches
        code = "def complex(x):\n"
        for i in range(35):
            code += f"    if x > {i}:\n        x -= 1\n"
        code += "    return x\n"
        (tmp_path / "complex.py").write_text(code)

        scanner = CodebaseScanner(tmp_path)
        profile = scanner.scan()
        planner = MigrationPlanner(profile)
        plan = planner.plan()

        assert any("complexity" in w.lower() for w in plan.warnings)
