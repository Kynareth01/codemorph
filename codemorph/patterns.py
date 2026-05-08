"""
Migration patterns — 16 built-in rules for common code transformations.

Each Pattern has an `apply(code, source_lang, target_lang, context)` method
that returns (transformed_code, was_applied).
"""

from __future__ import annotations

import re
import textwrap
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class Pattern(ABC):
    """Base class for all migration patterns."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def apply(
        self,
        code: str,
        *,
        source_lang: str = "python",
        target_lang: str = "typescript",
        context: Any = None,
    ) -> Tuple[str, bool]:
        """Transform code. Returns (new_code, was_applied)."""
        ...


# ---------------------------------------------------------------------------
# 1. Python → JS/TS base
# ---------------------------------------------------------------------------

class PythonToJSBase(Pattern):
    """Core Python → JavaScript/TypeScript conversion rules."""
    name = "python_to_js_base"
    description = "Convert Python syntax to JS/TS equivalents"

    _FUNC_RE = re.compile(r"^(\s*)def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*\w+)?\s*:", re.MULTILINE)
    _CLASS_RE = re.compile(r"^(\s*)class\s+(\w+)\s*(?:\([^)]*\))?\s*:", re.MULTILINE)
    _SELF_RE = re.compile(r"\bself\.")
    _NONE_RE = re.compile(r"\bNone\b")
    _TRUE_RE = re.compile(r"\bTrue\b")
    _FALSE_RE = re.compile(r"\bFalse\b")
    _AND_RE = re.compile(r"\band\b")
    _OR_RE = re.compile(r"\bor\b")
    _NOT_RE = re.compile(r"\bnot\s+")
    _PRINT_RE = re.compile(r"\bprint\s*\(([^)]*)\)")
    _LEN_RE = re.compile(r"\blen\s*\(([^)]*)\)")
    _LIST_COMP_RE = re.compile(r"\[([^[\]]+)\s+for\s+(\w+)\s+in\s+([^\]]+)\]")
    _FSTRING_RE = re.compile(r"""f(['"].*?['"])""")
    _RANGE_RE = re.compile(r"\brange\s*\(([^)]*)\)")
    _LAMBDA_RE = re.compile(r"lambda\s+([^:]+):\s*(.+)")
    _COMMENT_RE = re.compile(r"#\s*(.*)")
    _DOCSTRING_RE = re.compile(r'"""(.*?)"""', re.DOTALL)
    _EXCEPT_RE = re.compile(r"except\s+(\w+)?\s*(?:as\s+\w+)?\s*:")
    _RAISE_RE = re.compile(r"\braise\s+(\w+)\s*\(([^)]*)\)")
    _WITH_RE = re.compile(r"with\s+(.+?)\s+as\s+(\w+)\s*:")
    _IMPORT_FROM_RE = re.compile(r"from\s+[\w.]+\s+import\s+(.+)")
    _IMPORT_RE = re.compile(r"^import\s+(.+)", re.MULTILINE)

    def apply(self, code: str, *, source_lang: str = "python", target_lang: str = "typescript", context: Any = None) -> Tuple[str, bool]:
        if source_lang != "python" or target_lang not in ("javascript", "typescript"):
            return code, False

        out = code

        # Remove type hints (Python-specific syntax)
        out = re.sub(r":\s*\w+(\[.*?\])?(?=\s*[=,)\]])", "", out)
        out = re.sub(r"\s*->\s*\w+(\[.*?\])?\s*:", " {", out)

        # def → function
        def _fn_repl(m: re.Match) -> str:
            indent, name, params = m.group(1), m.group(2), m.group(3)
            params = self._SELF_RE.sub("", params).strip().strip(",")
            # clean up trailing comma
            params = re.sub(r",\s*,", ",", params)
            params = params.strip(", ")
            return f"{indent}function {name}({params}) {{"
        out = self._FUNC_RE.sub(_fn_repl, out)

        # class
        def _cls_repl(m: re.Match) -> str:
            indent, name = m.group(1), m.group(2)
            return f"{indent}class {name} {{"
        out = self._CLASS_RE.sub(_cls_repl, out)

        # literals
        out = self._NONE_RE.sub("null", out)
        out = self._TRUE_RE.sub("true", out)
        out = self._FALSE_RE.sub("false", out)

        # logical operators
        out = self._AND_RE.sub("&&", out)
        out = self._OR_RE.sub("||", out)
        out = self._NOT_RE.sub("!", out)

        # print → console.log
        out = self._PRINT_RE.sub(r"console.log(\1)", out)

        # len(x) → x.length
        out = self._LEN_RE.sub(r"\1.length", out)

        # list comprehension → Array.from / .map
        def _list_comp(m: re.Match) -> str:
            expr, var, iterable = m.group(1), m.group(2), m.group(3)
            return f"{iterable}.map({var} => {expr})"
        out = self._LIST_COMP_RE.sub(_list_comp, out)

        # f-strings → template literals
        def _fstring(m: re.Match) -> str:
            inner = m.group(1)
            # convert {expr} to ${expr}
            inner = re.sub(r"\{([^}]+)\}", r"${\1}", inner)
            return f"`{inner[1:-1]}`"
        out = self._FSTRING_RE.sub(_fstring, out)

        # range(n) → Array.from({length: n}, (_, i) => i)
        def _range(m: re.Match) -> str:
            args = [a.strip() for a in m.group(1).split(",")]
            if len(args) == 1:
                return f"Array.from({{length: {args[0]}}}, (_, i) => i)"
            elif len(args) == 2:
                return f"Array.from({{length: {args[1]} - {args[0]}}}, (_, i) => i + {args[0]})"
            else:
                return f"Array.from({{length: ({args[1]} - {args[0]}) / {args[2]}}}, (_, i) => {args[0]} + i * {args[2]})"
        out = self._RANGE_RE.sub(_range, out)

        # lambda → arrow function
        out = self._LAMBDA_RE.sub(r"(\1) => \2", out)

        # # comments → // comments
        out = self._COMMENT_RE.sub(r"// \1", out)

        # except → catch
        def _except_repl(m: re.Match) -> str:
            exc = m.group(1) or "Error"
            return f"catch (error) {{ // caught {exc}"
        out = self._EXCEPT_RE.sub(_except_repl, out)

        # raise → throw
        out = self._RAISE_RE.sub(r"throw new \1(\2)", out)

        # Remove import lines (handled separately)
        out = self._IMPORT_RE.sub(lambda m: f"// migrated: import {m.group(1)}", out)
        out = self._IMPORT_FROM_RE.sub(lambda m: f"// migrated: import {m.group(1)}", out)

        # Fix indentation-based blocks → braces (simple heuristic)
        out = self._fix_indentation(out)

        return out, out != code

    def _fix_indentation(self, code: str) -> str:
        """Best-effort conversion of Python indentation to braces."""
        lines = code.split("\n")
        result: List[str] = []
        indent_stack: List[int] = [0]

        for line in lines:
            stripped = line.lstrip()
            if not stripped:
                result.append("")
                continue

            indent = len(line) - len(stripped)

            # dedent → close braces
            while indent < indent_stack[-1]:
                indent_stack.pop()
                result.append(" " * indent_stack[-1] + "}")

            if stripped.endswith("{") or stripped.endswith("}") or stripped.startswith("//"):
                result.append(line)
            elif indent > indent_stack[-1] and not stripped.startswith("}"):
                indent_stack.append(indent)

            result.append(line)

        # close remaining
        while len(indent_stack) > 1:
            indent_stack.pop()
            result.append(" " * indent_stack[-1] + "}")

        return "\n".join(result)


# ---------------------------------------------------------------------------
# 2. Add TypeScript type annotations
# ---------------------------------------------------------------------------

class AddTypeAnnotations(Pattern):
    """Add basic TypeScript type annotations to JS code."""
    name = "add_type_annotations"
    description = "Infer and add TypeScript type annotations"

    _FUNC_RE = re.compile(r"function\s+(\w+)\(([^)]*)\)\s*\{")
    _RETURN_RE = re.compile(r"return\s+(.+?);")
    _CONST_RE = re.compile(r"const\s+(\w+)\s*=\s*(.+?);")

    def apply(self, code: str, *, source_lang: str = "python", target_lang: str = "typescript", context: Any = None) -> Tuple[str, bool]:
        if target_lang != "typescript":
            return code, False

        out = code

        # Add : any to untyped params
        def _fn_repl(m: re.Match) -> str:
            name, params = m.group(1), m.group(2).strip()
            if not params:
                return f"function {name}(): any {{"
            typed_params = []
            for p in params.split(","):
                p = p.strip()
                if ":" not in p:
                    typed_params.append(f"{p}: any")
                else:
                    typed_params.append(p)
            return f"function {name}({', '.join(typed_params)}): any {{"
        out = self._FUNC_RE.sub(_fn_repl, out)

        return out, out != code


# ---------------------------------------------------------------------------
# 3. Flask → Express
# ---------------------------------------------------------------------------

class FlaskToExpress(Pattern):
    """Convert Flask patterns to Express.js equivalents."""
    name = "flask_to_express"
    description = "Flask → Express.js migration patterns"

    _ROUTE_RE = re.compile(r'@app\.route\(["\']([^"\']+)["\'].*?\)\s*\ndef\s+(\w+)')
    _REQUEST_RE = re.compile(r"\brequest\.(args|form|json)\b")
    _JSONIFY_RE = re.compile(r"jsonify\s*\(([^)]*)\)")
    _APP_RUN_RE = re.compile(r"app\.run\s*\([^)]*\)")

    def apply(self, code: str, *, source_lang: str = "python", target_lang: str = "typescript", context: Any = None) -> Tuple[str, bool]:
        out = code

        # @app.route → app.get/post
        def _route_repl(m: re.Match) -> str:
            path, handler = m.group(1), m.group(2)
            return f'app.get("{path}", (req, res) => {{\n  // handler: {handler}'
        out = self._ROUTE_RE.sub(_route_repl, out)

        # request.args → req.query
        out = re.sub(r"request\.args", "req.query", out)
        out = re.sub(r"request\.form", "req.body", out)
        out = re.sub(r"request\.json", "req.body", out)

        # jsonify → res.json
        out = self._JSONIFY_RE.sub(r"res.json(\1)", out)

        # app.run → app.listen
        out = self._APP_RUN_RE.sub("app.listen(3000, () => console.log('Server running'))", out)

        return out, out != code


# ---------------------------------------------------------------------------
# 4. FastAPI → Express
# ---------------------------------------------------------------------------

class FastAPIToExpress(Pattern):
    """Convert FastAPI patterns to Express.js equivalents."""
    name = "fastapi_to_express"
    description = "FastAPI → Express.js migration patterns"

    _ROUTE_RE = re.compile(r'@app\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']\s*\)')
    _PYDANTIC_RE = re.compile(r"class\s+(\w+)\s*\(BaseModel\)\s*:")

    def apply(self, code: str, *, source_lang: str = "python", target_lang: str = "typescript", context: Any = None) -> Tuple[str, bool]:
        out = code

        # @app.get("/path") → app.get("/path", async (req, res) => {
        def _route_repl(m: re.Match) -> str:
            method, path = m.group(1), m.group(2)
            return f'app.{method}("{path}", async (req, res) => {{'
        out = self._ROUTE_RE.sub(_route_repl, out)

        # Pydantic models → TypeScript interfaces
        def _pydantic_repl(m: re.Match) -> str:
            name = m.group(1)
            return f"interface {name} {{"
        out = self._PYDANTIC_RE.sub(_pydantic_repl, out)

        return out, out != code


# ---------------------------------------------------------------------------
# 5. Django → Express
# ---------------------------------------------------------------------------

class DjangoToExpress(Pattern):
    """Convert Django patterns to Express.js equivalents."""
    name = "django_to_express"
    description = "Django → Express.js migration patterns"

    _URL_RE = re.compile(r'path\s*\(\s*["\']([^"\']+)["\']\s*,\s*(\w+)')
    _VIEW_RE = re.compile(r"def\s+(\w+)\s*\(\s*request")
    _JSON_RE = re.compile(r"JsonResponse\s*\(([^)]*)\)")

    def apply(self, code: str, *, source_lang: str = "python", target_lang: str = "typescript", context: Any = None) -> Tuple[str, bool]:
        out = code

        # Django path() → Express route
        def _url_repl(m: re.Match) -> str:
            path, view = m.group(1), m.group(2)
            return f'app.get("{path}", (req, res) => {{\n  // view: {view}'
        out = self._URL_RE.sub(_url_repl, out)

        # def view(request) → function
        out = self._VIEW_RE.sub(lambda m: f"function {m.group(1)}(req, res)", out)

        # JsonResponse → res.json
        out = self._JSON_RE.sub(r"res.json(\1)", out)

        return out, out != code


# ---------------------------------------------------------------------------
# 6-16. Additional patterns
# ---------------------------------------------------------------------------

class RemoveTypeHints(Pattern):
    """Strip Python type annotations."""
    name = "remove_type_hints"
    description = "Remove Python type hints"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = re.sub(r":\s*\w+(\[.*?\])?(?=\s*[=,)\]])", "", code)
        out = re.sub(r"->\s*\w+(\[.*?\])?\s*:", ":", out)
        return out, out != code


class RenameSnakeToCamel(Pattern):
    """Convert snake_case identifiers to camelCase."""
    name = "snake_to_camel"
    description = "Rename snake_case to camelCase"

    _RE = re.compile(r"\b([a-z]+(?:_[a-z]+)+)\b")

    def _convert(self, m: re.Match) -> str:
        parts = m.group(1).split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = self._RE.sub(self._convert, code)
        return out, out != code


class DictToObject(Pattern):
    """Convert Python dict patterns to JS object literals."""
    name = "dict_to_object"
    description = "Python dicts → JS objects"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = code.replace(": None", ": null").replace(": True", ": true").replace(": False", ": false")
        return out, out != code


class StringFormatToTemplate(Pattern):
    """Convert .format() calls to template literals."""
    name = "string_format_to_template"
    description = "str.format() → template literals"

    _RE = re.compile(r"""(['"].*?['"])\.format\(([^)]*)\)""")

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        def _repl(m: re.Match) -> str:
            tmpl = m.group(1)[1:-1]  # strip quotes
            args = [a.strip() for a in m.group(2).split(",")]
            for i, arg in enumerate(args):
                tmpl = tmpl.replace("{}", f"${{{arg}}}", 1)
            return f"`{tmpl}`"
        out = self._RE.sub(_repl, code)
        return out, out != code


class AsyncAwaitTransform(Pattern):
    """Convert Python async/await to JS async/await."""
    name = "async_await"
    description = "Python async/await → JS async/await"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = code
        out = re.sub(r"\basync def\b", "async function", out)
        out = re.sub(r"\bawait\s+", "await ", out)
        return out, out != code


class TryExceptToTryCatch(Pattern):
    """Convert try/except to try/catch."""
    name = "try_except_to_try_catch"
    description = "try/except → try/catch"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = code
        out = re.sub(r"\bexcept\b", "catch", out)
        out = re.sub(r"\bfinally\s*:", "finally {", out)
        return out, out != code


class ClassMethodToPrototype(Pattern):
    """Convert Python class methods to JS class syntax."""
    name = "class_method_to_prototype"
    description = "Python class → JS class"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = code
        out = re.sub(r"__init__", "constructor", out)
        out = re.sub(r"\bself\b", "this", out)
        return out, out != code


class ForInToForEach(Pattern):
    """Convert Python for-in loops to JS .forEach() or for...of."""
    name = "for_in_to_foreach"
    description = "for x in y → for (const x of y)"

    _RE = re.compile(r"for\s+(\w+)\s+in\s+(.+):")

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = self._RE.sub(r"for (const \1 of \2) {", code)
        return out, out != code


class DecoratorToMiddleware(Pattern):
    """Convert Python decorators to Express middleware patterns."""
    name = "decorator_to_middleware"
    description = "@decorator → middleware pattern"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = re.sub(r"@(\w+)\s*\n", r"// middleware: \1\n", code)
        return out, out != code


class ListToSpread(Pattern):
    """Convert Python list operations to JS spread/slice."""
    name = "list_to_spread"
    description = "Python list ops → JS spread/slice"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = code
        out = re.sub(r"\b\.append\(", ".push(", out)
        out = re.sub(r"\b\.extend\(", ".push(...", out)
        out = re.sub(r"\b\.pop\(\)", ".pop()", out)
        out = re.sub(r"\b\.insert\((\d+),\s*([^)]+)\)", r".splice(\1, 0, \2)", out)
        return out, out != code


class SetToSet(Pattern):
    """Convert Python set operations to JS Set."""
    name = "set_to_js_set"
    description = "Python set → JS Set"

    def apply(self, code: str, **kwargs: Any) -> Tuple[str, bool]:
        out = code
        out = re.sub(r"\bset\(\)", "new Set()", out)
        out = re.sub(r"\b\.add\(", ".add(", out)
        out = re.sub(r"\b\.discard\(", ".delete(", out)
        return out, out != code


# ---------------------------------------------------------------------------
# Pattern registry
# ---------------------------------------------------------------------------

_BUILTIN_PATTERNS: Dict[str, Pattern] = {
    p.name: p() for p in [
        PythonToJSBase,
        AddTypeAnnotations,
        FlaskToExpress,
        FastAPIToExpress,
        DjangoToExpress,
        RemoveTypeHints,
        RenameSnakeToCamel,
        DictToObject,
        StringFormatToTemplate,
        AsyncAwaitTransform,
        TryExceptToTryCatch,
        ClassMethodToPrototype,
        ForInToForEach,
        DecoratorToMiddleware,
        ListToSpread,
        SetToSet,
    ]
}


class PatternRegistry:
    """Central registry of migration patterns."""

    def __init__(self) -> None:
        self._patterns: Dict[str, Pattern] = dict(_BUILTIN_PATTERNS)

    def register(self, pattern: Pattern) -> None:
        """Register a custom pattern."""
        self._patterns[pattern.name] = pattern

    def get(self, name: str) -> Optional[Pattern]:
        """Look up a pattern by name."""
        return self._patterns.get(name)

    def list_patterns(self) -> List[str]:
        """Return sorted list of all registered pattern names."""
        return sorted(self._patterns.keys())

    def summary(self) -> str:
        """Human-readable listing."""
        lines = ["Registered Patterns:", "=" * 50]
        for name in self.list_patterns():
            p = self._patterns[name]
            lines.append(f"  {p.name:30s}  {p.description}")
        return "\n".join(lines)
