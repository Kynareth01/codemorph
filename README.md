# CodeMorph

We had 15K lines of Python that needed to become TypeScript. Doing it by hand
would have taken 3 months. This tool did it in a weekend.

CodeMorph is an AI-powered code migration tool that converts codebases between
languages and frameworks. It scans your project, plans the migration in
dependency order, transforms files with full-codebase context, and validates
the output — all automatically.

## What It Does

```
┌─────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐     ┌──────────┐
│  Scan   │────▶│  Plan    │────▶│ Transform │────▶│ Validate │────▶│  Report  │
│ (langs, │     │ (step    │     │ (file-by- │     │ (syntax, │     │ (diffs,  │
│  deps)  │     │  order)  │     │  file)    │     │  types)  │     │  stats)  │
└─────────┘     └──────────┘     └───────────┘     └──────────┘     └──────────┘
```

### Supported Conversions

| Source | Target | Status |
|--------|--------|--------|
| Python | TypeScript | ✅ Full support |
| Python | JavaScript | ✅ Full support |
| JavaScript | TypeScript | ✅ Full support |
| Flask | Express.js | ✅ Pattern-based |
| FastAPI | Express.js | ✅ Pattern-based |
| Django | Express.js | ✅ Pattern-based |
| Flask | FastAPI | 🔜 Planned |

### 16 Built-in Migration Patterns

| # | Pattern | Description |
|---|---------|-------------|
| 1 | `python_to_js_base` | Core Python → JS/TS syntax conversion |
| 2 | `add_type_annotations` | Infer and add TypeScript types |
| 3 | `flask_to_express` | Flask routes → Express.js |
| 4 | `fastapi_to_express` | FastAPI → Express.js |
| 5 | `django_to_express` | Django views → Express.js |
| 6 | `remove_type_hints` | Strip Python type annotations |
| 7 | `snake_to_camel` | snake_case → camelCase identifiers |
| 8 | `dict_to_object` | Python dicts → JS objects |
| 9 | `string_format_to_template` | .format() → template literals |
| 10 | `async_await` | Python async/await → JS async/await |
| 11 | `try_except_to_try_catch` | try/except → try/catch |
| 12 | `class_method_to_prototype` | Python class → JS class syntax |
| 13 | `for_in_to_foreach` | for x in y → for (const x of y) |
| 14 | `decorator_to_middleware` | @decorator → middleware pattern |
| 15 | `list_to_spread` | Python list ops → JS array methods |
| 16 | `set_to_js_set` | Python set → JS Set |

## Quick Start

### Installation

```bash
pip install codemorph
```

Or from source:

```bash
git clone https://github.com/Kynareth01/codemorph.git
cd codemorph
pip install -e ".[dev]"
```

### Scan a Project

```bash
codemorph scan ./my-python-project
```

Output:

```
  Project root : /home/user/my-python-project
  Total files  : 47
  Total lines  : 15,234
  Languages    : {'python': 45, 'javascript': 2}
  Frameworks   : {'flask', 'sqlalchemy'}
  Entry points : ['main.py', 'manage.py']
```

### Run a Migration

```bash
codemorph migrate ./my-python-project --target typescript --output ./ts-project
```

Dry run (preview without writing files):

```bash
codemorph migrate ./my-python-project --target typescript --dry-run
```

### Validate Migrated Code

```bash
codemorph validate ./ts-project --language typescript
```

### List Available Patterns

```bash
codemorph patterns
```

## Programmatic API

```python
from codemorph import (
    CodebaseScanner,
    MigrationPlanner,
    TransformEngine,
    PostMigrationValidator,
    PatternRegistry,
    MigrationReporter,
)
from codemorph.config import MigrationConfig

# 1. Scan
scanner = CodebaseScanner("./my-python-project")
profile = scanner.scan()
print(f"Found {len(profile.files)} files across {profile.languages}")

# 2. Configure
config = MigrationConfig(
    source_lang="python",
    target_lang="typescript",
    source_dir="./my-python-project",
    output_dir="./ts-project",
)
config.resolve_paths()

# 3. Plan
planner = MigrationPlanner(profile, config.source_lang, config.target_lang)
plan = planner.plan()
print(plan.summary())

# 4. Execute
registry = PatternRegistry()
engine = TransformEngine(plan, config, profile, pattern_registry=registry)
results = engine.run()

# 5. Validate
validator = PostMigrationValidator(config.output_dir)
validation = validator.validate(language="typescript")

# 6. Report
reporter = MigrationReporter(project_name="my-python-project")
report = reporter.build_report(results, validation)
print(reporter.to_terminal(report))
print(reporter.to_markdown(report))  # also: .to_json()
```

## How It Works

### 1. Codebase Scanner

Walks your project tree and detects:
- **Languages** by file extension
- **Frameworks** by import patterns and keywords
- **Imports/dependencies** via AST parsing (Python) or regex (JS/TS)
- **Entry points** by filename heuristics
- **Complexity** by branch-count estimation

### 2. Migration Planner

Takes the scan output and produces an ordered plan:
- **Topological sort** ensures dependencies are migrated before dependents
- **Pattern selection** picks the right transformation rules per file
- **Config generation** creates tsconfig.json, package.json, etc.
- **Warnings** flag high-complexity files for manual review

### 3. Transform Engine

Executes the plan file-by-file with full context:
- Each file is transformed in order
- Upstream results are available as context
- Multiple patterns compose in sequence
- Dry-run mode previews without writing

### 4. Post-Migration Validators

Three validation layers:
- **Syntax** — Python AST, Node --check, tsc --noEmit
- **Types** — mypy (Python), tsc strict mode (TypeScript)
- **Tests** — pytest, jest

### 5. Migration Reporter

Generates reports in three formats:
- **Terminal** — compact summary for CLI use
- **Markdown** — detailed report with diffs (great for PRs)
- **JSON** — machine-readable for CI/CD pipelines

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CODEMORPH_SOURCE_LANG` | `python` | Source language |
| `CODEMORPH_TARGET_LANG` | `typescript` | Target language |
| `CODEMORPH_SOURCE_DIR` | `.` | Source directory |
| `CODEMORPH_OUTPUT_DIR` | (auto) | Output directory |
| `CODEMORPH_DRY_RUN` | `false` | Preview mode |
| `CODEMORPH_VERBOSE` | `false` | Verbose output |
| `CODEMORPH_MAX_WORKERS` | `4` | Parallel workers |

### Presets

```python
from codemorph.config import load_preset

config = load_preset("python-to-typescript")
config = load_preset("python-to-javascript")
config = load_preset("javascript-to-typescript")
config = load_preset("flask-to-fastapi")
```

## Docker

```bash
docker build -t codemorph .
docker run -v $(pwd):/workspace codemorph scan /workspace
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=codemorph --cov-report=term-missing

# Type checking
mypy codemorph

# Linting
ruff check codemorph/
```

## Example: Flask → Express

### Before (Python/Flask)

```python
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/api/users", methods=["GET"])
def get_users():
    return jsonify(users)

@app.route("/api/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = next((u for u in users if u["id"] == user_id), None)
    if user is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(user)

if __name__ == "__main__":
    app.run(debug=True)
```

### After (TypeScript/Express)

```typescript
import express, { Request, Response } from "express";

const app = express();
app.use(express.json());

interface User {
    id: number;
    name: string;
    email: string;
}

const users: User[] = [
    { id: 1, name: "Alice", email: "alice@example.com" },
];

app.get("/api/users", (req: Request, res: Response) => {
    res.json(users);
});

app.get("/api/users/:userId", (req: Request, res: Response) => {
    const userId = parseInt(req.params.userId);
    const user = users.find((u) => u.id === userId);
    if (!user) {
        res.status(404).json({ error: "Not found" });
        return;
    }
    res.json(user);
});

app.listen(3000, () => console.log("Server running on port 3000"));
```

## License

MIT License. See [LICENSE](LICENSE) for details.
