"""Import relationships and dependency neighbourhood analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Config, DEFAULT_CONFIG
from .index_db import open_index


@dataclass
class ImportRelation:
    """An import relationship."""

    source_path: str
    imported_module: str
    imported_name: str | None
    alias: str | None
    relative_level: int
    line: int

    def as_dict(self) -> dict:
        return {
            "source_path": self.source_path,
            "imported_module": self.imported_module,
            "imported_name": self.imported_name,
            "alias": self.alias,
            "relative_level": self.relative_level,
            "line": self.line,
        }


def find_imports(
    repository_root: Path,
    path: str | None = None,
    module: str | None = None,
    max_results: int = 100,
    config: Config = DEFAULT_CONFIG,
) -> list[ImportRelation]:
    """Find import relationships, optionally filtered by path or module."""
    imports: list[ImportRelation] = []

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()

        sql = """
            SELECT relative_path, imported_module, imported_name, alias, relative_level, line
            FROM imports
            WHERE 1=1
        """
        params: list = []

        if path:
            sql += " AND relative_path = ?"
            params.append(path)

        if module:
            sql += " AND (imported_module = ? OR imported_module LIKE ?)"
            params.extend([module, f"{module}.%"])

        sql += " ORDER BY relative_path, line LIMIT ?"
        params.append(max_results)

        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            imports.append(ImportRelation(
                source_path=row[0],
                imported_module=row[1],
                imported_name=row[2],
                alias=row[3],
                relative_level=row[4],
                line=row[5],
            ))

    return imports


def _imports_of(repository_root: Path, config: Config, mod: str) -> list[str]:
    """Get modules imported by the given module."""
    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT imported_module
            FROM imports
            WHERE relative_path LIKE ? AND relative_level = 0
            """,
            (f"%{mod.replace('.', '/')}%",),
        ).fetchall()
        return [row[0] for row in rows if row[0]]


def _dependents_of(repository_root: Path, config: Config, mod: str) -> list[str]:
    """Get modules that import the given module."""
    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()
        rows = conn.execute(
            """
            SELECT DISTINCT relative_path
            FROM imports
            WHERE imported_module = ? OR imported_module LIKE ?
            """,
            (mod, f"{mod}.%"),
        ).fetchall()
        return [row[0] for row in rows if row[0]]


def _traverse_deps(
    repository_root: Path,
    config: Config,
    mod: str,
    current_depth: int,
    depth: int,
    max_results: int,
    visited: set[str],
    dependencies: dict[str, list[str]],
    dependents: dict[str, list[str]],
) -> None:
    """Recursively collect dependencies and dependents up to the given depth."""
    if mod in visited or current_depth > depth:
        return
    visited.add(mod)

    # Get imports
    imports = _imports_of(repository_root, config, mod)
    dependencies[mod] = imports

    # Get dependents
    deps = _dependents_of(repository_root, config, mod)
    dependents[mod] = deps

    # Recurse
    for imp in imports:
        if len(visited) < max_results:
            _traverse_deps(
                repository_root, config, imp, current_depth + 1,
                depth, max_results, visited, dependencies, dependents,
            )


def dependency_neighbourhood(
    repository_root: Path,
    module: str,
    depth: int = 1,
    max_results: int = 100,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Find the dependency neighbourhood of a module."""
    visited: set[str] = set()
    dependencies: dict[str, list[str]] = {}
    dependents: dict[str, list[str]] = {}

    _traverse_deps(
        repository_root, config, module, 0,
        depth, max_results, visited, dependencies, dependents,
    )

    return {
        "module": module,
        "depth": depth,
        "dependencies": dependencies,
        "dependents": dependents,
        "truncated": len(visited) >= max_results,
    }
