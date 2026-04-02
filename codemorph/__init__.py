"""
CodeMorph — AI-powered code migration tool.

Supports Python↔JavaScript conversions, framework upgrades,
and large-scale refactors with full-codebase context awareness.
"""

__version__ = "0.1.0"
__author__ = "CodeMorph Contributors"

from codemorph.scanner import CodebaseScanner
from codemorph.planner import MigrationPlanner
from codemorph.migrator import TransformEngine
from codemorph.validators import PostMigrationValidator
from codemorph.patterns import PatternRegistry
from codemorph.reporter import MigrationReporter

__all__ = [
    "CodebaseScanner",
    "MigrationPlanner",
    "TransformEngine",
    "PostMigrationValidator",
    "PatternRegistry",
    "MigrationReporter",
]
