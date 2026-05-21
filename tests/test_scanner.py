"""Tests for the codebase scanner."""

import tempfile
from pathlib import Path

import pytest

from codemorph.scanner import (
    CodebaseScanner,
    FileInfo,
    ProjectProfile,
    _detect_frameworks,
    _estimate_complexity,
    _parse_js_imports,
    _parse_python_imports,
)


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    """Create a sample Python project for testing."""
    (tmp_path / "main.py").write_text(
        'import os\nimport sys\nfrom flask import Flask\n\napp = Flask(__name__)\n\n'
        '@app.route("/")\ndef index():\n    return "Hello"\n\n'
        'if __name__ == "__main__":\n    app.run(debug=True)\n'
    )
    (tmp_path / "utils.py").write_text(
        'import json\nimport re\n\ndef parse_data(text):\n    """Parse input text."""\n'
        '    return json.loads(text)\n\ndef format_output(data):\n    return json.dumps(data)\n'
    )
    (tmp_path / "models.py").write_text(
        'from sqlalchemy import Column, Integer, String\nfrom sqlalchemy.ext.declarative import declarative_base\n\n'
        'Base = declarative_base()\n\nclass User(Base):\n    __tablename__ = "users"\n'
        '    id = Column(Integer, primary_key=True)\n    name = Column(String)\n'
    )
    (tmp_path / "requirements.txt").write_text("flask==2.0\nsqlalchemy==1.4\n")
    return tmp_path


@pytest.fixture
def js_project(tmp_path: Path) -> Path:
    """Create a sample JS project."""
    (tmp_path / "index.js").write_text(
        'const express = require("express");\nconst path = require("path");\n\n'
        'const app = express();\n\napp.get("/", (req, res) => {\n    res.json({ hello: "world" });\n});\n\n'
        'app.listen(3000);\n'
    )
    (tmp_path / "utils.js").write_text(
        'import { readFile } from "fs/promises";\n\nexport async function loadData(path) {\n'
        '    return JSON.parse(await readFile(path, "utf-8"));\n}\n'
    )
    return tmp_path


class TestPythonImportParser:
    def test_basic_imports(self, sample_project: Path):
        imports = _parse_python_imports(sample_project / "main.py")
        assert "os" in imports
        assert "sys" in imports
        assert "flask" in imports

    def test_from_imports(self, sample_project: Path):
        imports = _parse_python_imports(sample_project / "models.py")
        assert "sqlalchemy" in imports

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.py"
        f.write_text("")
        assert _parse_python_imports(f) == []


class TestJSImportParser:
    def test_require(self, js_project: Path):
        imports = _parse_js_imports(js_project / "index.js")
        assert "express" in imports

    def test_es_import(self, js_project: Path):
        imports = _parse_js_imports(js_project / "utils.js")
        assert "fs/promises" in imports or "fs" in imports


class TestFrameworkDetection:
    def test_flask_detected(self, sample_project: Path):
        frameworks = _detect_frameworks(sample_project / "main.py", "python")
        assert "flask" in frameworks

    def test_sqlalchemy_detected(self, sample_project: Path):
        frameworks = _detect_frameworks(sample_project / "models.py", "python")
        assert "sqlalchemy" in frameworks

    def test_express_detected(self, js_project: Path):
        frameworks = _detect_frameworks(js_project / "index.js", "javascript")
        assert "express" in frameworks


class TestComplexity:
    def test_simple_function(self, tmp_path: Path):
        f = tmp_path / "simple.py"
        f.write_text("def foo():\n    return 1\n")
        assert _estimate_complexity(f) == 1

    def test_branching(self, tmp_path: Path):
        f = tmp_path / "branchy.py"
        f.write_text("def foo(x):\n    if x > 0:\n        for i in range(x):\n            if i % 2 == 0:\n                print(i)\n")
        complexity = _estimate_complexity(f)
        assert complexity >= 3


class TestCodebaseScanner:
    def test_scan_finds_files(self, sample_project: Path):
        scanner = CodebaseScanner(sample_project)
        profile = scanner.scan()
        assert len(profile.files) == 3  # main.py, utils.py, models.py
        assert profile.languages.get("python") == 3

    def test_scan_detects_frameworks(self, sample_project: Path):
        scanner = CodebaseScanner(sample_project)
        profile = scanner.scan()
        assert "flask" in profile.frameworks

    def test_scan_dependency_graph(self, sample_project: Path):
        scanner = CodebaseScanner(sample_project)
        profile = scanner.scan()
        # main.py depends on nothing local (os, sys, flask are external)
        main_deps = profile.dependency_graph.get(Path("main.py"), set())
        assert len(main_deps) == 0

    def test_scan_entry_points(self, sample_project: Path):
        scanner = CodebaseScanner(sample_project)
        profile = scanner.scan()
        assert Path("main.py") in profile.entry_points

    def test_scan_js_project(self, js_project: Path):
        scanner = CodebaseScanner(js_project)
        profile = scanner.scan()
        assert len(profile.files) == 2
        assert "javascript" in profile.languages

    def test_exclude_dirs(self, tmp_path: Path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text("x = 1\n")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "cached.py").write_text("y = 2\n")
        scanner = CodebaseScanner(tmp_path)
        profile = scanner.scan()
        assert len(profile.files) == 1
