"""Symbol queries, reference finding, and dependency analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError
from .dependencies import ImportRelation, dependency_neighbourhood, find_imports  # noqa: F401  (compat re-export)
from .index_db import open_index


SymbolKind = Literal["class", "function", "method", "property", "variable"]
ReferenceConfidence = Literal["definition", "import", "ast_reference", "lexical_reference"]


class SymbolError(RepositoryIntelligenceError):
    """Raised when symbol operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class Symbol:
    """A symbol in the codebase."""

    name: str
    qualified_name: str
    kind: str
    path: str
    parent: str | None
    start_line: int
    end_line: int
    decorators: list[str]
    is_async: bool

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "path": self.path,
            "parent": self.parent,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "decorators": self.decorators,
            "is_async": self.is_async,
        }


@dataclass
class Reference:
    """A reference to a symbol."""

    path: str
    line: int
    column: int
    content: str
    confidence: ReferenceConfidence

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "content": self.content,
            "confidence": self.confidence,
        }


def _symbol_from_row(row) -> Symbol:
    """Build a Symbol from an indexed symbols row."""
    decorators = []
    if row[7]:
        try:
            decorators = json.loads(row[7])
        except (json.JSONDecodeError, TypeError):
            pass

    return Symbol(
        name=row[0],
        qualified_name=row[1],
        kind=row[2],
        path=row[3],
        parent=row[4],
        start_line=row[5],
        end_line=row[6],
        decorators=decorators,
        is_async=bool(row[8]),
    )


def list_symbols(
    repository_root: Path,
    kind: SymbolKind | None = None,
    path_prefix: str | None = None,
    max_results: int = 100,
    config: Config = DEFAULT_CONFIG,
) -> list[Symbol]:
    """List symbols in the repository, optionally filtered by kind or path."""
    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()

        sql = """
            SELECT name, qualified_name, kind, relative_path, parent,
                   start_line, end_line, decorators, is_async
            FROM symbols
            WHERE 1=1
        """
        params: list = []

        if kind:
            sql += " AND kind = ?"
            params.append(kind)

        if path_prefix:
            sql += " AND relative_path LIKE ?"
            params.append(f"{path_prefix}%")

        sql += " ORDER BY relative_path, start_line LIMIT ?"
        params.append(max_results)

        rows = conn.execute(sql, params).fetchall()
        return [_symbol_from_row(row) for row in rows]


def _find_symbol_sql(
    name: str,
    exact: bool,
    kind: SymbolKind | None,
    max_results: int,
) -> tuple[str, list]:
    """Build the ranked find_symbol SQL statement and its parameters."""
    if exact:
        sql = """
            SELECT name, qualified_name, kind, relative_path, parent,
                   start_line, end_line, decorators, is_async
            FROM symbols
            WHERE name = ?
        """
        params: list = [name]
    else:
        sql = """
            SELECT name, qualified_name, kind, relative_path, parent,
                   start_line, end_line, decorators, is_async
            FROM symbols
            WHERE name LIKE ? OR qualified_name LIKE ?
        """
        params = [f"%{name}%", f"%{name}%"]

    if kind:
        sql += " AND kind = ?"
        params.append(kind)

    sql += " ORDER BY "
    if exact:
        sql += "CASE WHEN name = ? THEN 0 ELSE 1 END, "
        params.append(name)
    else:
        sql += "CASE WHEN name = ? THEN 0 WHEN name LIKE ? THEN 1 ELSE 2 END, "
        params.extend([name, f"{name}%"])
    sql += "relative_path, start_line LIMIT ?"
    params.append(max_results)
    return sql, params


def find_symbol(
    repository_root: Path,
    name: str,
    exact: bool = False,
    kind: SymbolKind | None = None,
    max_results: int = 100,
    config: Config = DEFAULT_CONFIG,
) -> list[Symbol]:
    """Find symbols by name, ranked by relevance."""
    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()
        sql, params = _find_symbol_sql(name, exact, kind, max_results)
        rows = conn.execute(sql, params).fetchall()
        return [_symbol_from_row(row) for row in rows]


def _import_references(conn, symbol_name: str, max_results: int) -> list[Reference]:
    """Collect import-based references to a symbol."""
    import_rows = conn.execute(
        """
        SELECT relative_path, line
        FROM imports
        WHERE imported_name = ? OR (imported_module LIKE ? AND imported_name IS NULL)
        LIMIT ?
        """,
        (symbol_name, f"%{symbol_name}%", max_results),
    ).fetchall()

    return [
        Reference(
            path=row[0],
            line=row[1],
            column=0,
            content=f"Import of {symbol_name}",
            confidence="import",
        )
        for row in import_rows
    ]


def _lexical_references(conn, symbol_name: str, max_results: int, def_row) -> list[Reference]:
    """Collect lexical references via FTS; empty on FTS failure."""
    references: list[Reference] = []
    try:
        from .search import escape_fts5_query
        fts_query = escape_fts5_query(symbol_name)
        fts_rows = conn.execute(
            """
            SELECT path, snippet(file_text, 1, '>>>', '<<<', '...', 32)
            FROM file_text
            WHERE file_text MATCH ?
            LIMIT ?
            """,
            (fts_query, max_results),
        ).fetchall()

        for row in fts_rows:
            # Skip if already added as definition
            if def_row and row[0] == def_row[0]:
                continue
            references.append(Reference(
                path=row[0],
                line=0,
                column=0,
                content=row[1] or f"Reference to {symbol_name}",
                confidence="lexical_reference",
            ))
    except Exception:
        pass  # FTS search failed, skip lexical references
    return references


def find_references(
    repository_root: Path,
    symbol_name: str,
    max_results: int = 100,
    config: Config = DEFAULT_CONFIG,
) -> list[Reference]:
    """Find references to a symbol with confidence classification."""
    references: list[Reference] = []

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()

        # Find definition
        def_row = conn.execute(
            """
            SELECT relative_path, start_line
            FROM symbols
            WHERE name = ? OR qualified_name = ?
            LIMIT 1
            """,
            (symbol_name, symbol_name),
        ).fetchone()

        if def_row:
            references.append(Reference(
                path=def_row[0],
                line=def_row[1],
                column=0,
                content=f"Definition of {symbol_name}",
                confidence="definition",
            ))

        references.extend(_import_references(conn, symbol_name, max_results))
        references.extend(_lexical_references(conn, symbol_name, max_results, def_row))

    return references[:max_results]
