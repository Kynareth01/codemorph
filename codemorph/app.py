"""
CodeMorph CLI — scan, migrate, and validate commands.

Usage:
    codemorph scan [DIR]
    codemorph migrate [DIR] [--target TARGET] [--dry-run]
    codemorph validate [DIR]
    codemorph patterns
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Optional

from codemorph.config import MigrationConfig, load_preset
from codemorph.migrator import TransformEngine
from codemorph.patterns import PatternRegistry
from codemorph.planner import MigrationPlanner
from codemorph.reporter import MigrationReporter
from codemorph.scanner import CodebaseScanner, scan_and_print
from codemorph.validators import PostMigrationValidator


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> int:
    """Scan a codebase and print the profile."""
    root = Path(args.dir).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 1

    profile = scan_and_print(str(root))
    if args.json:
        data = {
            "root": str(profile.root),
            "total_files": len(profile.files),
            "total_lines": profile.total_lines,
            "languages": profile.languages,
            "frameworks": list(profile.frameworks),
            "entry_points": [str(e) for e in profile.entry_points],
        }
        print(json.dumps(data, indent=2))
    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Run a full migration."""
    source_dir = Path(args.dir).resolve()
    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory", file=sys.stderr)
        return 1

    # Build config
    config = MigrationConfig(
        source_lang=args.source,
        target_lang=args.target,
        source_dir=source_dir,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    if args.output:
        config.output_dir = Path(args.output).resolve()
    config.resolve_paths()

    # Scan
    print(f"\n  Scanning {source_dir}...")
    scanner = CodebaseScanner(source_dir)
    profile = scanner.scan()
    print(f"  Found {len(profile.files)} files, {profile.total_lines} lines")

    # Plan
    print(f"  Planning {config.source_lang} → {config.target_lang} migration...")
    planner = MigrationPlanner(profile, config.source_lang, config.target_lang)
    plan = planner.plan()
    print(f"  Plan: {len(plan.steps)} steps")
    if plan.warnings:
        for w in plan.warnings:
            print(f"  ⚠  {w}")

    # Execute
    print(f"  {'[DRY RUN] ' if config.dry_run else ''}Executing migration...")
    start = time.time()
    registry = PatternRegistry()
    engine = TransformEngine(plan, config, profile, pattern_registry=registry)
    results = engine.run(dry_run=config.dry_run)
    elapsed = time.time() - start

    # Validate
    validation = None
    if config.run_validators and not config.dry_run:
        print("  Running post-migration validation...")
        validator = PostMigrationValidator(config.output_dir or source_dir)
        validation = validator.validate(language=config.target_lang)

    # Report
    reporter = MigrationReporter(project_name=source_dir.name)
    report = reporter.build_report(results, validation, source_lang=config.source_lang, target_lang=config.target_lang)
    print(reporter.to_terminal(report))

    if args.report:
        report_path = Path(args.report)
        if report_path.suffix == ".json":
            report_path.write_text(reporter.to_json(report), encoding="utf-8")
        else:
            report_path.write_text(reporter.to_markdown(report), encoding="utf-8")
        print(f"  Report saved to {report_path}")

    print(f"  Done in {elapsed:.1f}s\n")
    return 0 if report.failed_files == 0 else 1


def cmd_validate(args: argparse.Namespace) -> int:
    """Run post-migration validation on an existing directory."""
    project_dir = Path(args.dir).resolve()
    if not project_dir.is_dir():
        print(f"Error: {project_dir} is not a directory", file=sys.stderr)
        return 1

    print(f"\n  Validating {project_dir}...")
    validator = PostMigrationValidator(project_dir)
    report = validator.validate(language=args.language)

    print(report.summary())
    print()
    return 0 if report.passed else 1


def cmd_patterns(args: argparse.Namespace) -> int:
    """List all registered migration patterns."""
    registry = PatternRegistry()
    print(registry.summary())
    print(f"\n  Total: {len(registry.list_patterns())} patterns\n")
    return 0


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codemorph",
        description="CodeMorph — AI-powered code migration tool",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan
    scan_parser = subparsers.add_parser("scan", help="Scan a codebase")
    scan_parser.add_argument("dir", nargs="?", default=".", help="Directory to scan")
    scan_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run a migration")
    migrate_parser.add_argument("dir", nargs="?", default=".", help="Source directory")
    migrate_parser.add_argument("--source", default="python", help="Source language")
    migrate_parser.add_argument("--target", default="typescript", help="Target language")
    migrate_parser.add_argument("--output", "-o", help="Output directory")
    migrate_parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    migrate_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    migrate_parser.add_argument("--report", help="Save report to file (.md or .json)")

    # validate
    validate_parser = subparsers.add_parser("validate", help="Validate migrated code")
    validate_parser.add_argument("dir", nargs="?", default=".", help="Directory to validate")
    validate_parser.add_argument("--language", default="typescript", help="Language to validate")

    # patterns
    subparsers.add_parser("patterns", help="List available migration patterns")

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    commands = {
        "scan": cmd_scan,
        "migrate": cmd_migrate,
        "validate": cmd_validate,
        "patterns": cmd_patterns,
    }
    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
