"""Text search functionality - FTS5 and ripgrep backends."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError, TruncationInfo
from .file_reading import read_file_outline, read_file_range  # noqa: F401  (compat re-export)
from .index_db import open_index
from .path_security import validate_relative_path


SearchBackend = Literal["auto", "index", "ripgrep"]


class SearchError(RepositoryIntelligenceError):
    """Raised when search fails."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class TextMatch:
    """A text match result."""

    path: str
    line: int
    column: int
    content: str
    context_before: list[str] | None = None
    context_after: list[str] | None = None

    def as_dict(self) -> dict:
        result = {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "content": self.content,
        }
        if self.context_before:
            result["context_before"] = self.context_before
        if self.context_after:
            result["context_after"] = self.context_after
        return result


@dataclass
class SearchResult:
    """Result of a text search."""

    matches: list[TextMatch]
    total_count: int
    truncated: bool
    backend_used: str
    query: str

    def as_dict(self) -> dict:
        return {
            "matches": [m.as_dict() for m in self.matches],
            "total_count": self.total_count,
            "truncated": self.truncated,
            "backend_used": self.backend_used,
            "query": self.query,
        }


def escape_fts5_query(query: str) -> str:
    """Escape a raw query string so it is safe for FTS5."""
    # FTS5 special characters that need escaping
    special_chars = r'() * + - " AND OR NOT NEAR'

    # For simple term search, just escape double quotes
    # and wrap in quotes for phrase search
    escaped = query.replace('"', '""')
    return f'"{escaped}"'


def _fts5_sql(
    fts_query: str,
    path_scope: str | None,
    language: str | None,
    max_results: int,
) -> tuple[str, list]:
    """Build the FTS5 SQL statement and its parameters."""
    sql = """
        SELECT
            ft.path,
            ft.content,
            snippet(file_text, 1, '>>>', '<<<', '...', 32) as snippet
        FROM file_text ft
        JOIN files f ON ft.path = f.relative_path
        WHERE file_text MATCH ?
    """
    params: list = [fts_query]

    if path_scope:
        sql += " AND ft.path LIKE ?"
        params.append(f"{path_scope}%")

    if language:
        sql += " AND f.language = ?"
        params.append(language)

    sql += " LIMIT ?"
    params.append(max_results)
    return sql, params


def _match_from_fts_row(row, query: str) -> TextMatch:
    """Build a TextMatch from an FTS5 result row."""
    path = row[0]
    content = row[1]
    snippet = row[2]

    # Find line number
    lines = content.splitlines()
    line_num = 1
    column = 0
    line = ""
    for i, line in enumerate(lines):
        if query.lower() in line.lower():
            line_num = i + 1
            column = line.lower().find(query.lower()) + 1
            break

    return TextMatch(
        path=path,
        line=line_num,
        column=column,
        content=snippet or line.strip() if lines else "",
    )


def search_fts5(
    repository_root: Path,
    query: str,
    path_scope: str | None = None,
    language: str | None = None,
    max_results: int = 100,
    config: Config = DEFAULT_CONFIG,
) -> SearchResult:
    """Search using the FTS5 index."""
    matches: list[TextMatch] = []

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()

        fts_query = escape_fts5_query(query)
        sql, params = _fts5_sql(fts_query, path_scope, language, max_results)

        try:
            rows = conn.execute(sql, params).fetchall()
            for row in rows:
                matches.append(_match_from_fts_row(row, query))
        except Exception as exc:
            raise SearchError("search_failed", f"FTS5 search error: {exc}")

    truncated = len(matches) >= max_results
    return SearchResult(
        matches=matches,
        total_count=len(matches),
        truncated=truncated,
        backend_used="index",
        query=query,
    )


def _ripgrep_command(
    rg_path: str,
    query: str,
    repository_root: Path,
    path_scope: str | None,
    language: str | None,
    max_results: int,
    is_regex: bool,
) -> list[str]:
    """Build the ripgrep command line."""
    cmd = [rg_path, "--json", "--max-count", str(max_results)]

    if not is_regex:
        cmd.append("--fixed-strings")

    if path_scope:
        cmd.extend(["--glob", f"{path_scope}**"])

    if language:
        # Map language names to ripgrep types
        lang_map = {
            "python": "py",
            "javascript": "js",
            "typescript": "ts",
        }
        rg_lang = lang_map.get(language, language)
        cmd.extend(["--type", rg_lang])

    cmd.append(query)
    cmd.append(str(repository_root))
    return cmd


def _parse_ripgrep_output(stdout: str, repository_root: Path) -> list[TextMatch]:
    """Parse ripgrep --json output lines into matches."""
    matches: list[TextMatch] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            if data.get("type") == "match":
                match_data = data.get("data", {})
                path = match_data.get("path", {}).get("text", "")
                line_num = match_data.get("line_number", 0)
                content = match_data.get("lines", {}).get("text", "").rstrip()
                submatches = match_data.get("submatches", [])

                column = 1
                if submatches:
                    column = submatches[0].get("start", 0) + 1

                # Make path relative
                try:
                    rel_path = str(Path(path).relative_to(repository_root))
                except ValueError:
                    rel_path = path

                matches.append(TextMatch(
                    path=rel_path.replace("\\", "/"),
                    line=line_num,
                    column=column,
                    content=content,
                ))
        except (json.JSONDecodeError, KeyError):
            continue
    return matches


def search_ripgrep(
    repository_root: Path,
    query: str,
    path_scope: str | None = None,
    language: str | None = None,
    max_results: int = 100,
    is_regex: bool = False,
    config: Config = DEFAULT_CONFIG,
) -> SearchResult:
    """Search using ripgrep."""
    # Check if ripgrep is available
    rg_path = shutil.which("rg")
    if rg_path is None:
        raise SearchError("ripgrep_not_found", "ripgrep (rg) is not installed or not in PATH")

    cmd = _ripgrep_command(
        rg_path, query, repository_root, path_scope, language, max_results, is_regex
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(repository_root),
        )
        matches = _parse_ripgrep_output(result.stdout, repository_root)
    except subprocess.TimeoutExpired:
        raise SearchError("search_timeout", "Search timed out")
    except Exception as exc:
        raise SearchError("search_failed", f"ripgrep error: {exc}")

    truncated = len(matches) >= max_results
    return SearchResult(
        matches=matches[:max_results],
        total_count=len(matches),
        truncated=truncated,
        backend_used="ripgrep",
        query=query,
    )


def search_text(
    repository_root: Path,
    query: str,
    backend: SearchBackend = "auto",
    path_scope: str | None = None,
    language: str | None = None,
    max_results: int = 100,
    is_regex: bool = False,
    config: Config = DEFAULT_CONFIG,
) -> SearchResult:
    """Search for text in repository files via the selected backend."""
    # Validate path scope if provided
    if path_scope:
        try:
            validate_relative_path(repository_root, path_scope)
        except Exception:
            pass  # Allow non-existent paths for scope

    # Determine backend
    if backend == "auto":
        # Use ripgrep for regex, index for plain text
        if is_regex:
            backend = "ripgrep"
        else:
            # Check if index exists
            db_path = config.index_path(repository_root)
            if db_path.exists():
                backend = "index"
            else:
                backend = "ripgrep"

    if backend == "index":
        return search_fts5(
            repository_root=repository_root,
            query=query,
            path_scope=path_scope,
            language=language,
            max_results=max_results,
            config=config,
        )
    else:
        return search_ripgrep(
            repository_root=repository_root,
            query=query,
            path_scope=path_scope,
            language=language,
            max_results=max_results,
            is_regex=is_regex,
            config=config,
        )
