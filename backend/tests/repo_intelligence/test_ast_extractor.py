"""Tests for ast_extractor module."""

from __future__ import annotations

import pytest

from audisor.repo_intelligence.ast_extractor import (
    parse_python_file,
    extract_symbols_from_ast,
    extract_imports_from_ast,
    compute_module_prefix,
    ParseResult,
    SymbolInfo,
    ImportInfo,
)


class TestParsePythonFile:
    """Tests for parse_python_file."""

    def test_parse_simple_class(self):
        content = '''
class MyClass:
    def method(self):
        pass
'''
        result = parse_python_file(content, "module.py")
        assert result.parse_status == "ok"
        assert len(result.symbols) >= 1
        assert any(s.name == "MyClass" for s in result.symbols)

    def test_parse_function(self):
        content = '''
def my_function():
    pass
'''
        result = parse_python_file(content, "module.py")
        assert result.parse_status == "ok"
        assert any(s.name == "my_function" for s in result.symbols)

    def test_parse_async_function(self):
        content = '''
async def async_func():
    pass
'''
        result = parse_python_file(content, "module.py")
        assert result.parse_status == "ok"
        func = next(s for s in result.symbols if s.name == "async_func")
        assert func.is_async is True

    def test_parse_imports(self):
        content = '''
import os
from pathlib import Path
from . import sibling
'''
        result = parse_python_file(content, "module.py")
        assert result.parse_status == "ok"
        assert len(result.imports) >= 3
        assert any(i.imported_module == "os" for i in result.imports)
        assert any(i.imported_module == "pathlib" and i.imported_name == "Path" for i in result.imports)

    def test_parse_syntax_error(self):
        content = '''
def broken(
    # missing closing paren
'''
        result = parse_python_file(content, "module.py")
        assert result.parse_status == "syntax_error"
        assert result.error_message is not None

    def test_parse_decorators(self):
        content = '''
@property
def my_prop(self):
    pass

@staticmethod
def static_method():
    pass
'''
        result = parse_python_file(content, "module.py")
        assert result.parse_status == "ok"
        prop = next((s for s in result.symbols if s.name == "my_prop"), None)
        assert prop is not None
        assert "property" in prop.decorators

    def test_line_count(self):
        content = "line1\nline2\nline3\n"
        result = parse_python_file(content, "module.py")
        assert result.line_count >= 3  # At least 3 lines


class TestComputeModulePrefix:
    """Tests for compute_module_prefix."""

    def test_simple_module(self):
        assert compute_module_prefix("module.py") == "module"

    def test_nested_module(self):
        assert compute_module_prefix("pkg/subpkg/module.py") == "pkg.subpkg.module"

    def test_init_module(self):
        assert compute_module_prefix("pkg/__init__.py") == "pkg"

    def test_src_layout(self):
        assert compute_module_prefix("src/pkg/module.py") == "pkg.module"

    def test_src_layout_init(self):
        assert compute_module_prefix("src/pkg/__init__.py") == "pkg"


class TestExtractSymbolsFromAst:
    """Tests for extract_symbols_from_ast."""

    def test_extract_class(self):
        import ast
        content = "class MyClass: pass"
        tree = ast.parse(content)
        symbols = extract_symbols_from_ast(tree, "module.py")
        assert len(symbols) == 1
        assert symbols[0].name == "MyClass"
        assert symbols[0].kind == "class"

    def test_extract_function(self):
        import ast
        content = "def my_func(): pass"
        tree = ast.parse(content)
        symbols = extract_symbols_from_ast(tree, "module.py")
        assert len(symbols) == 1
        assert symbols[0].name == "my_func"
        assert symbols[0].kind == "function"

    def test_extract_method(self):
        import ast
        content = '''
class MyClass:
    def method(self): pass
'''
        tree = ast.parse(content)
        symbols = extract_symbols_from_ast(tree, "module.py")
        method = next((s for s in symbols if s.name == "method"), None)
        assert method is not None
        assert method.kind == "method"
        assert method.parent == "MyClass"


class TestExtractImportsFromAst:
    """Tests for extract_imports_from_ast."""

    def test_extract_import(self):
        import ast
        content = "import os"
        tree = ast.parse(content)
        imports = extract_imports_from_ast(tree, "module.py")
        assert len(imports) == 1
        assert imports[0].imported_module == "os"

    def test_extract_from_import(self):
        import ast
        content = "from pathlib import Path"
        tree = ast.parse(content)
        imports = extract_imports_from_ast(tree, "module.py")
        assert len(imports) == 1
        assert imports[0].imported_module == "pathlib"
        assert imports[0].imported_name == "Path"

    def test_extract_relative_import(self):
        import ast
        content = "from . import sibling"
        tree = ast.parse(content)
        imports = extract_imports_from_ast(tree, "module.py")
        assert len(imports) == 1
        assert imports[0].relative_level == 1
