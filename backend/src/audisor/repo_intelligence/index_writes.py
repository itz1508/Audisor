"""Per-file row-writing helpers for the indexer."""

from __future__ import annotations

import json
import time

from .language import read_text_file


def _decode_content(content: bytes) -> str | None:
    """Decode file content to text; returns None on encoding failure."""
    if hasattr(read_text_file, "__wrapped__"):
        text, _ = read_text_file.__wrapped__(content)
        if text is not None:
            return text
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _write_file_rows(
    conn,
    relative_path: str,
    text: str,
    content_hash: str,
    language: str,
    size: int,
    parse_status: str,
) -> None:
    """Write the file record and FTS row; clear stale symbols and imports."""
    conn.execute(
        """
        INSERT OR REPLACE INTO files
        (relative_path, sha256, language, size, line_count, indexed_at, parse_status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (relative_path, content_hash, language, size, len(text.splitlines()), time.time(), parse_status),
    )
    conn.execute("DELETE FROM file_text WHERE path = ?", (relative_path,))
    conn.execute(
        "INSERT INTO file_text (path, content) VALUES (?, ?)",
        (relative_path, text),
    )
    conn.execute("DELETE FROM symbols WHERE relative_path = ?", (relative_path,))
    conn.execute("DELETE FROM imports WHERE relative_path = ?", (relative_path,))


def _insert_symbols(conn, relative_path: str, symbols) -> None:
    """Insert extracted symbol rows for a file."""
    for symbol in symbols:
        conn.execute(
            """
            INSERT INTO symbols
            (relative_path, name, qualified_name, kind, parent, start_line, end_line, decorators, is_async)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relative_path,
                symbol.name,
                symbol.qualified_name,
                symbol.kind,
                symbol.parent,
                symbol.start_line,
                symbol.end_line,
                json.dumps(symbol.decorators) if symbol.decorators else None,
                1 if symbol.is_async else 0,
            ),
        )


def _insert_imports(conn, relative_path: str, imports) -> None:
    """Insert extracted import rows for a file."""
    for imp in imports:
        conn.execute(
            """
            INSERT INTO imports
            (relative_path, imported_module, imported_name, alias, relative_level, line)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                relative_path,
                imp.imported_module,
                imp.imported_name,
                imp.alias,
                imp.relative_level,
                imp.line,
            ),
        )
