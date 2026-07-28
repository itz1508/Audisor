"""Python AST parsing and symbol/import extraction."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any


@dataclass
class SymbolInfo:
    """Information about a Python symbol."""

    name: str
    qualified_name: str
    kind: str  # "class", "function", "method", "property", "variable"
    parent: str | None
    start_line: int
    end_line: int
    decorators: list[str]
    is_async: bool


@dataclass
class ImportInfo:
    """Information about a Python import."""

    imported_module: str
    imported_name: str | None
    alias: str | None
    relative_level: int
    line: int


@dataclass
class ParseResult:
    """Result of parsing a Python file."""

    relative_path: str
    symbols: list[SymbolInfo]
    imports: list[ImportInfo]
    line_count: int
    parse_status: str  # "ok", "syntax_error", "partial"
    error_message: str | None = None


def _qualified_name(name: str, parent: str | None, module_prefix: str) -> str:
    """Build the qualified name for a symbol."""
    if parent:
        return f"{parent}.{name}"
    if module_prefix:
        return f"{module_prefix}.{name}"
    return name


def _get_decorators(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    """Extract decorator names from a definition node."""
    decorators = []
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            decorators.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            decorators.append(ast.unparse(dec))
        elif isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Name):
                decorators.append(dec.func.id)
            elif isinstance(dec.func, ast.Attribute):
                decorators.append(ast.unparse(dec.func))
            else:
                decorators.append(ast.unparse(dec))
        else:
            decorators.append(ast.unparse(dec))
    return decorators


def _function_kind(parent: str | None, decorators: list[str]) -> str:
    """Determine whether a def is a function, method, or property."""
    if not parent:
        return "function"
    if "property" in decorators or "classmethod" in decorators or "staticmethod" in decorators:
        return "property"
    return "method"


def _variable_symbols(
    node: ast.Assign | ast.AnnAssign,
    parent_qualified: str | None,
    module_prefix: str,
) -> list[SymbolInfo]:
    """Build symbols for module-level variable assignments."""
    targets = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                targets.append(target.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        targets.append(node.target.id)

    symbols: list[SymbolInfo] = []
    for name in targets:
        if name.startswith("_"):
            continue  # Skip private variables
        symbols.append(SymbolInfo(
            name=name,
            qualified_name=_qualified_name(name, parent_qualified, module_prefix),
            kind="variable",
            parent=None,
            start_line=node.lineno,
            end_line=node.lineno,
            decorators=[],
            is_async=False,
        ))
    return symbols


def _visit_body(
    body: list[ast.stmt],
    parent: str | None,
    parent_qualified: str | None,
    module_prefix: str,
    symbols: list[SymbolInfo],
) -> None:
    """Visit statements and collect class/function/variable symbols."""
    for node in body:
        if isinstance(node, ast.ClassDef):
            qualified = _qualified_name(node.name, parent_qualified, module_prefix)
            symbols.append(SymbolInfo(
                name=node.name,
                qualified_name=qualified,
                kind="class",
                parent=parent,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                decorators=_get_decorators(node),
                is_async=False,
            ))
            _visit_body(node.body, node.name, qualified, module_prefix, symbols)

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualified = _qualified_name(node.name, parent_qualified, module_prefix)
            decorators = _get_decorators(node)
            symbols.append(SymbolInfo(
                name=node.name,
                qualified_name=qualified,
                kind=_function_kind(parent, decorators),
                parent=parent,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                decorators=decorators,
                is_async=isinstance(node, ast.AsyncFunctionDef),
            ))
            _visit_body(node.body, node.name, qualified, module_prefix, symbols)

        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            # Handle module-level variable assignments
            if parent is None:
                symbols.extend(_variable_symbols(node, parent_qualified, module_prefix))


def extract_symbols_from_ast(
    tree: ast.Module,
    relative_path: str,
    module_prefix: str = "",
) -> list[SymbolInfo]:
    """Extract symbols from an AST."""
    symbols: list[SymbolInfo] = []
    _visit_body(tree.body, None, module_prefix or None, module_prefix, symbols)
    return symbols


def extract_imports_from_ast(
    tree: ast.Module,
    relative_path: str,
) -> list[ImportInfo]:
    """Extract imports from an AST.

    Args:
        tree: Parsed AST
        relative_path: File path relative to repository root

    Returns:
        List of ImportInfo
    """
    imports: list[ImportInfo] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(ImportInfo(
                    imported_module=alias.name,
                    imported_name=None,
                    alias=alias.asname,
                    relative_level=0,
                    line=node.lineno,
                ))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            for alias in node.names:
                imports.append(ImportInfo(
                    imported_module=module,
                    imported_name=alias.name,
                    alias=alias.asname,
                    relative_level=level,
                    line=node.lineno,
                ))

    return imports


def parse_python_file(
    content: str,
    relative_path: str,
    module_prefix: str = "",
) -> ParseResult:
    """Parse a Python file and extract symbols and imports.

    Args:
        content: File content
        relative_path: File path relative to repository root
        module_prefix: Module prefix for qualified names

    Returns:
        ParseResult with extracted information
    """
    line_count = len(content.splitlines())

    try:
        tree = ast.parse(content, filename=relative_path)
    except SyntaxError as exc:
        return ParseResult(
            relative_path=relative_path,
            symbols=[],
            imports=[],
            line_count=line_count,
            parse_status="syntax_error",
            error_message=f"Line {exc.lineno}: {exc.msg}",
        )

    symbols = extract_symbols_from_ast(tree, relative_path, module_prefix)
    imports = extract_imports_from_ast(tree, relative_path)

    return ParseResult(
        relative_path=relative_path,
        symbols=symbols,
        imports=imports,
        line_count=line_count,
        parse_status="ok",
    )


def compute_module_prefix(relative_path: str) -> str:
    """Compute module prefix from file path.

    Args:
        relative_path: File path relative to repository root

    Returns:
        Module prefix string
    """
    path_parts = relative_path.replace("\\", "/").split("/")

    # Remove .py extension
    if path_parts[-1].endswith(".py"):
        path_parts[-1] = path_parts[-1][:-3]

    # Remove __init__
    if path_parts[-1] == "__init__":
        path_parts = path_parts[:-1]

    # Look for src directory
    if "src" in path_parts:
        src_idx = path_parts.index("src")
        path_parts = path_parts[src_idx + 1:]

    return ".".join(path_parts) if path_parts else ""
