"""File range and outline reading backed by the index."""

from __future__ import annotations

from pathlib import Path

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError
from .index_db import open_index
from .path_security import validate_relative_path


class FileReadError(RepositoryIntelligenceError):
    """Raised when file reading fails."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


def _read_lines(repository_root: Path, relative_path: str) -> list[str]:
    """Validate the path and read the file as UTF-8 lines."""
    file_path = validate_relative_path(repository_root, relative_path)

    if not file_path.is_file():
        raise FileReadError("file_not_found", f"File not found: {relative_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.readlines()
    except UnicodeDecodeError:
        raise FileReadError("encoding_error", f"File is not valid UTF-8: {relative_path}")
    except (OSError, IOError) as exc:
        raise FileReadError("read_error", f"Failed to read file: {exc}")


def read_file_range(
    repository_root: Path,
    relative_path: str,
    start_line: int = 1,
    end_line: int | None = None,
    max_bytes: int | None = None,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Read a specific range of lines from a file."""
    lines = _read_lines(repository_root, relative_path)
    total_lines = len(lines)

    # Validate line range
    if start_line < 1:
        start_line = 1
    if end_line is None or end_line > total_lines:
        end_line = total_lines
    if start_line > total_lines:
        return {
            "path": relative_path,
            "content": "",
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "truncated": False,
        }

    # Extract range
    content = "".join(lines[start_line - 1:end_line])

    # Check byte limit
    truncated = False
    if max_bytes and len(content.encode("utf-8")) > max_bytes:
        truncated = True
        # Truncate to byte limit
        content_bytes = content.encode("utf-8")[:max_bytes]
        content = content_bytes.decode("utf-8", errors="ignore")

    return {
        "path": relative_path,
        "content": content,
        "start_line": start_line,
        "end_line": end_line if not truncated else start_line + content.count("\n"),
        "total_lines": total_lines,
        "truncated": truncated,
    }


def _outline_symbols(conn, relative_path: str) -> list[dict]:
    """Load indexed symbols for a file, ordered by start line."""
    rows = conn.execute(
        """
        SELECT name, qualified_name, kind, parent, start_line, end_line, decorators, is_async
        FROM symbols
        WHERE relative_path = ?
        ORDER BY start_line
        """,
        (relative_path,),
    ).fetchall()

    return [
        {
            "name": row[0],
            "qualified_name": row[1],
            "kind": row[2],
            "parent": row[3],
            "start_line": row[4],
            "end_line": row[5],
            "decorators": row[6],
            "is_async": bool(row[7]),
        }
        for row in rows
    ]


def _outline_imports(conn, relative_path: str) -> list[dict]:
    """Load indexed imports for a file, ordered by line."""
    rows = conn.execute(
        """
        SELECT imported_module, imported_name, alias, relative_level, line
        FROM imports
        WHERE relative_path = ?
        ORDER BY line
        """,
        (relative_path,),
    ).fetchall()

    return [
        {
            "imported_module": row[0],
            "imported_name": row[1],
            "alias": row[2],
            "relative_level": row[3],
            "line": row[4],
        }
        for row in rows
    ]


def read_file_outline(
    repository_root: Path,
    relative_path: str,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Read the structural outline of a file (imports, classes, functions)."""
    # Validate path
    file_path = validate_relative_path(repository_root, relative_path)

    if not file_path.is_file():
        raise FileReadError("file_not_found", f"File not found: {relative_path}")

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()

        symbols = _outline_symbols(conn, relative_path)
        imports = _outline_imports(conn, relative_path)

        # Get file info
        file_row = conn.execute(
            "SELECT language, line_count, parse_status FROM files WHERE relative_path = ?",
            (relative_path,),
        ).fetchone()

        return {
            "path": relative_path,
            "language": file_row[0] if file_row else "unknown",
            "total_lines": file_row[1] if file_row else 0,
            "parse_status": file_row[2] if file_row else "unknown",
            "symbols": symbols,
            "imports": imports,
        }
