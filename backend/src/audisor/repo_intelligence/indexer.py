"""File indexing and incremental refresh."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .ast_extractor import ParseResult, parse_python_file, compute_module_prefix
from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError, TruncationInfo
from .exclusions import is_binary_file, should_index_file
from .index_db import IndexDatabase, open_index
from .index_writes import _decode_content, _insert_imports, _insert_symbols, _write_file_rows
from .language import detect_language


class IndexingError(RepositoryIntelligenceError):
    """Raised when indexing fails."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class IndexingStats:
    """Statistics from an indexing operation."""

    files_examined: int = 0
    files_indexed: int = 0
    files_reparsed: int = 0
    files_skipped: int = 0
    files_deleted: int = 0
    files_renamed: int = 0
    symbols_extracted: int = 0
    imports_extracted: int = 0
    binary_files_skipped: int = 0
    encoding_errors: int = 0
    syntax_errors: int = 0
    elapsed_seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "files_examined": self.files_examined,
            "files_indexed": self.files_indexed,
            "files_reparsed": self.files_reparsed,
            "files_skipped": self.files_skipped,
            "files_deleted": self.files_deleted,
            "files_renamed": self.files_renamed,
            "symbols_extracted": self.symbols_extracted,
            "imports_extracted": self.imports_extracted,
            "binary_files_skipped": self.binary_files_skipped,
            "encoding_errors": self.encoding_errors,
            "syntax_errors": self.syntax_errors,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


def compute_file_hash(content: bytes) -> str:
    """Compute SHA-256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


def iter_files_to_index(
    repository_root: Path,
    config: Config = DEFAULT_CONFIG,
) -> Iterator[tuple[Path, str, bytes]]:
    """Yield (path, relative_path, content_bytes) tuples for indexable files."""
    resolved_root = repository_root.expanduser().resolve()

    for path in sorted(resolved_root.rglob("*")):
        if not path.is_file():
            continue

        try:
            relative = path.relative_to(resolved_root)
        except ValueError:
            continue

        if not should_index_file(relative):
            continue

        # Check file size
        try:
            size = path.stat().st_size
        except OSError:
            continue

        if size > config.max_file_size_bytes:
            continue

        # Skip binary files
        if is_binary_file(path):
            continue

        # Read content
        try:
            content = path.read_bytes()
        except (OSError, IOError):
            continue

        yield path, relative.as_posix(), content


def index_file(
    db: IndexDatabase,
    relative_path: str,
    content: bytes,
    config: Config = DEFAULT_CONFIG,
) -> tuple[bool, ParseResult | None]:
    """Index a single file; returns (success, parse_result)."""
    text = _decode_content(content)
    if text is None:
        return False, None

    content_hash = compute_file_hash(content)
    language = detect_language(Path(relative_path))

    # Parse Python files
    parse_result: ParseResult | None = None
    parse_status = "ok"

    if language == "python":
        module_prefix = compute_module_prefix(relative_path)
        parse_result = parse_python_file(text, relative_path, module_prefix)
        parse_status = parse_result.parse_status

    conn = db._get_connection()
    _write_file_rows(conn, relative_path, text, content_hash, language, len(content), parse_status)

    if parse_result is not None:
        _insert_symbols(conn, relative_path, parse_result.symbols)
        _insert_imports(conn, relative_path, parse_result.imports)

    return True, parse_result


def _apply_index_result(
    stats: IndexingStats,
    success: bool,
    parse_result: ParseResult | None,
) -> None:
    """Accumulate per-file indexing outcome into stats."""
    if success:
        stats.files_indexed += 1
        stats.files_reparsed += 1
        if parse_result is not None:
            stats.symbols_extracted += len(parse_result.symbols)
            stats.imports_extracted += len(parse_result.imports)
            if parse_result.parse_status == "syntax_error":
                stats.syntax_errors += 1
    else:
        stats.encoding_errors += 1


def full_index(
    repository_root: Path,
    config: Config = DEFAULT_CONFIG,
    progress_callback: callable | None = None,
) -> IndexingStats:
    """Perform a full index of the repository; returns IndexingStats."""
    start_time = time.time()
    stats = IndexingStats()

    with open_index(repository_root, config, create=True) as db:
        # Acquire lock
        if not db.acquire_lock("full_index"):
            raise IndexingError("index_locked", "Another indexing operation is in progress")

        try:
            # Clear existing data
            conn = db._get_connection()
            conn.execute("DELETE FROM files")
            conn.execute("DELETE FROM file_text")
            conn.execute("DELETE FROM symbols")
            conn.execute("DELETE FROM imports")

            # Set metadata
            db.set_metadata("schema_version", "1")
            db.set_metadata("repository_root", str(repository_root.resolve()))
            db.set_metadata("created_at", str(start_time))
            db.set_metadata("updated_at", str(start_time))

            # Index files
            for path, relative_path, content in iter_files_to_index(repository_root, config):
                stats.files_examined += 1

                if progress_callback:
                    progress_callback(relative_path, stats.files_examined)

                success, parse_result = index_file(db, relative_path, content, config)
                _apply_index_result(stats, success, parse_result)

            db.set_metadata("updated_at", str(time.time()))

        finally:
            db.release_lock("full_index")

    stats.elapsed_seconds = time.time() - start_time
    return stats


def _discover_refresh_paths(
    conn,
    repository_root: Path,
    paths: list[str] | None,
    config: Config,
    stats: IndexingStats,
) -> tuple[set[str], list[str]]:
    """Discover indexable files; returns (discovered_paths, paths_to_refresh)."""
    discovered_paths: set[str] = set()
    paths_to_refresh: list[str] = []

    for path, relative_path, content in iter_files_to_index(repository_root, config):
        stats.files_examined += 1
        discovered_paths.add(relative_path)
        current_hash = compute_file_hash(content)

        if paths is not None:
            # If specific paths requested, only refresh those
            if relative_path in paths:
                paths_to_refresh.append(relative_path)
        else:
            # Auto-detect: check if file exists in index or has changed
            row = conn.execute(
                "SELECT sha256 FROM files WHERE relative_path = ?",
                (relative_path,),
            ).fetchone()

            if row is None or row[0] != current_hash:
                paths_to_refresh.append(relative_path)

    return discovered_paths, paths_to_refresh


def _refresh_paths(
    db: IndexDatabase,
    repository_root: Path,
    paths_to_refresh: list[str],
    config: Config,
    stats: IndexingStats,
) -> None:
    """Re-index each refresh path, accumulating outcome stats."""
    resolved_root = repository_root.resolve()
    for relative_path in paths_to_refresh:
        file_path = resolved_root / relative_path
        if not file_path.is_file():
            stats.files_skipped += 1
            continue

        try:
            content = file_path.read_bytes()
        except (OSError, IOError):
            stats.files_skipped += 1
            continue

        success, parse_result = index_file(db, relative_path, content, config)
        _apply_index_result(stats, success, parse_result)


def incremental_refresh(
    repository_root: Path,
    paths: list[str] | None = None,
    config: Config = DEFAULT_CONFIG,
) -> IndexingStats:
    """Refresh changed files incrementally, removing deleted-file records.

    When paths is None, changes and deletions are auto-detected.
    """
    start_time = time.time()
    stats = IndexingStats()

    with open_index(repository_root, config, create=True) as db:
        # Acquire lock
        if not db.acquire_lock("incremental_refresh"):
            raise IndexingError("index_locked", "Another indexing operation is in progress")

        try:
            conn = db._get_connection()

            discovered_paths, paths_to_refresh = _discover_refresh_paths(
                conn, repository_root, paths, config, stats
            )

            # Detect deleted files: indexed paths not in discovered set
            if paths is None:
                # Only detect deletions when doing full auto-refresh
                indexed_rows = conn.execute("SELECT relative_path FROM files").fetchall()
                indexed_paths = {row[0] for row in indexed_rows}
                deleted_paths = indexed_paths - discovered_paths

                if deleted_paths:
                    # Remove deleted files atomically
                    _remove_deleted_files(conn, deleted_paths, stats)

            _refresh_paths(db, repository_root, paths_to_refresh, config, stats)

            # Detect renames: files with same hash but different paths
            # This is a best-effort heuristic based on content hash
            if paths is None and stats.files_deleted > 0:
                _detect_renames(conn, discovered_paths, stats)

            db.set_metadata("updated_at", str(time.time()))

        finally:
            db.release_lock("incremental_refresh")

    stats.elapsed_seconds = time.time() - start_time
    return stats


def _remove_deleted_files(conn, deleted_paths: set[str], stats: IndexingStats) -> None:
    """Remove deleted files and their associated records atomically."""
    for relative_path in deleted_paths:
        # Remove from all tables in a single transaction
        conn.execute("DELETE FROM files WHERE relative_path = ?", (relative_path,))
        conn.execute("DELETE FROM file_text WHERE path = ?", (relative_path,))
        conn.execute("DELETE FROM symbols WHERE relative_path = ?", (relative_path,))
        conn.execute("DELETE FROM imports WHERE relative_path = ?", (relative_path,))
        stats.files_deleted += 1


def _detect_renames(conn, discovered_paths: set[str], stats: IndexingStats) -> None:
    """Detect renames by matching content hashes (best-effort heuristic)."""
    # This is a simplified implementation - full rename detection would
    # require tracking hash history. For now, we just count deletions.
    # A more sophisticated approach would compare hashes of deleted vs new files.
    pass


def get_index_status(repository_root: Path, config: Config = DEFAULT_CONFIG) -> dict:
    """Get the current status of the index as a dictionary."""
    db_path = config.index_path(repository_root)

    if not db_path.exists():
        return {
            "exists": False,
            "status": "not_found",
            "message": "Index database not found",
        }

    try:
        with open_index(repository_root, config, create=False) as db:
            metadata = db.get_metadata()
            if metadata is None:
                return {
                    "exists": True,
                    "status": "uninitialized",
                    "message": "Index database exists but is not initialized",
                }

            locked, holder = db.is_locked()

            return {
                "exists": True,
                "status": "ready",
                "schema_version": metadata.schema_version,
                "repository_root": metadata.repository_root,
                "head_commit": metadata.head_commit,
                "created_at": metadata.created_at,
                "updated_at": metadata.updated_at,
                "file_count": metadata.file_count,
                "symbol_count": metadata.symbol_count,
                "locked": locked,
                "locked_by": holder,
            }
    except Exception as exc:
        return {
            "exists": True,
            "status": "error",
            "message": str(exc),
        }
