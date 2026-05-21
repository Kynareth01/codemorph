"""Tests for migration patterns."""

import pytest

from codemorph.patterns import (
    AddTypeAnnotations,
    AsyncAwaitTransform,
    ClassMethodToPrototype,
    DecoratorToMiddleware,
    DictToObject,
    DjangoToExpress,
    FastAPIToExpress,
    FlaskToExpress,
    ForInToForEach,
    ListToSpread,
    PatternRegistry,
    PythonToJSBase,
    RemoveTypeHints,
    RenameSnakeToCamel,
    SetToSet,
    StringFormatToTemplate,
    TryExceptToTryCatch,
)


class TestPythonToJSBase:
    def setup_method(self):
        self.pattern = PythonToJSBase()

    def test_function_conversion(self):
        code = "def hello_world(name):\n    print(name)\n"
        result, applied = self.pattern.apply(code)
        assert applied is True
        assert "function" in result
        assert "console.log" in result

    def test_none_to_null(self):
        code = "x = None\n"
        result, applied = self.pattern.apply(code)
        assert "null" in result
        assert "None" not in result

    def test_true_false(self):
        code = "a = True\nb = False\n"
        result, applied = self.pattern.apply(code)
        assert "true" in result
        assert "false" in result

    def test_logical_operators(self):
        code = "x = a and b\ny = c or d\n"
        result, applied = self.pattern.apply(code)
        assert "&&" in result
        assert "||" in result

    def test_list_comprehension(self):
        code = "result = [x * 2 for x in items]\n"
        result, applied = self.pattern.apply(code)
        assert ".map(" in result

    def test_range_conversion(self):
        code = "for i in range(10):\n    print(i)\n"
        result, applied = self.pattern.apply(code)
        assert "Array.from" in result

    def test_lambda_conversion(self):
        code = "f = lambda x: x + 1\n"
        result, applied = self.pattern.apply(code)
        assert "=>" in result

    def test_comment_conversion(self):
        code = "# this is a comment\n"
        result, applied = self.pattern.apply(code)
        assert "//" in result

    def test_non_python_unchanged(self):
        code = "function hello() { return 1; }"
        result, applied = self.pattern.apply(code, source_lang="javascript")
        assert result == code
        assert applied is False

    def test_class_conversion(self):
        code = "class MyClass:\n    pass\n"
        result, applied = self.pattern.apply(code)
        assert "class MyClass" in result

    def test_fstring_conversion(self):
        code = 'msg = f"Hello {name}"\n'
        result, applied = self.pattern.apply(code)
        assert "${" in result or "`" in result

    def test_except_conversion(self):
        code = "try:\n    x()\nexcept ValueError:\n    pass\n"
        result, applied = self.pattern.apply(code)
        assert "catch" in result


class TestFlaskToExpress:
    def setup_method(self):
        self.pattern = FlaskToExpress()

    def test_route_conversion(self):
        code = '@app.route("/api/users")\ndef get_users():\n    pass\n'
        result, applied = self.pattern.apply(code)
        assert 'app.get("/api/users"' in result

    def test_request_args(self):
        code = "name = request.args.get('name')\n"
        result, applied = self.pattern.apply(code)
        assert "req.query" in result

    def test_jsonify(self):
        code = "return jsonify({'status': 'ok'})\n"
        result, applied = self.pattern.apply(code)
        assert "res.json" in result


class TestFastAPIToExpress:
    def setup_method(self):
        self.pattern = FastAPIToExpress()

    def test_route_conversion(self):
        code = '@app.get("/items/{item_id}")\nasync def read_item(item_id: int):\n    pass\n'
        result, applied = self.pattern.apply(code)
        assert 'app.get("/items/{item_id}"' in result
        assert "async" in result

    def test_pydantic_model(self):
        code = "class Item(BaseModel):\n    name: str\n    price: float\n"
        result, applied = self.pattern.apply(code)
        assert "interface Item" in result


class TestDjangoToExpress:
    def setup_method(self):
        self.pattern = DjangoToExpress()

    def test_path_conversion(self):
        code = 'path("api/users", get_users)\n'
        result, applied = self.pattern.apply(code)
        assert 'app.get("api/users"' in result

    def test_json_response(self):
        code = 'return JsonResponse({"status": "ok"})\n'
        result, applied = self.pattern.apply(code)
        assert "res.json" in result


class TestRenameSnakeToCamel:
    def setup_method(self):
        self.pattern = RenameSnakeToCamel()

    def test_basic_rename(self):
        code = "my_variable = 10\n"
        result, applied = self.pattern.apply(code)
        assert "myVariable" in result

    def test_multiple_words(self):
        code = "get_user_name = True\n"
        result, applied = self.pattern.apply(code)
        assert "getUserName" in result


class TestStringFormatToTemplate:
    def setup_method(self):
        self.pattern = StringFormatToTemplate()

    def test_basic_format(self):
        code = '"Hello {}".format(name)\n'
        result, applied = self.pattern.apply(code)
        assert "`" in result
        assert "${name}" in result


class TestPatternRegistry:
    def test_builtin_patterns_count(self):
        registry = PatternRegistry()
        assert len(registry.list_patterns()) == 16

    def test_get_pattern(self):
        registry = PatternRegistry()
        assert registry.get("python_to_js_base") is not None
        assert registry.get("nonexistent") is None

    def test_custom_pattern(self):
        from codemorph.patterns import Pattern
        from typing import Tuple

        class MyPattern(Pattern):
            name = "custom_test"
            description = "Test pattern"

            def apply(self, code: str, **kwargs) -> Tuple[str, bool]:
                return code.upper(), True

        registry = PatternRegistry()
        registry.register(MyPattern())
        assert registry.get("custom_test") is not None

    def test_summary(self):
        registry = PatternRegistry()
        summary = registry.summary()
        assert "python_to_js_base" in summary
        assert "16" not in summary or "patterns" in summary.lower()
