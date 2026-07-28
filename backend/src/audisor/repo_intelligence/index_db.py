"""SQLite index schema, migrations, and connection management."""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError


SCHEMA_VERSION = 1


class IndexConnectionError(RepositoryIntelligenceError):
    """Raised when index connection fails."""

    def __init__(self, detail: str) -> None:
        super().__init__("index_connection_error", detail)


class IndexSchemaError(RepositoryIntelligenceError):
    """Raised when index schema is incompatible."""

    def __init__(self, detail: str) -> None:
        super().__init__("index_schema_error", detail)


class IndexLockedError(RepositoryIntelligenceError):
    """Raised when index is locked by another writer."""

    def __init__(self, detail: str) -> None:
        super().__init__("index_locked", detail)


# SQL Schema statements
_CREATE_METADATA = """
CREATE TABLE IF NOT EXISTS index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CREATE_FILES = """
CREATE TABLE IF NOT EXISTS files (
    relative_path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    language TEXT NOT NULL,
    size INTEGER NOT NULL,
    line_count INTEGER,
    indexed_at REAL NOT NULL,
    parse_status TEXT NOT NULL DEFAULT 'ok'
);
"""

_CREATE_FILE_TEXT_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS file_text USING fts5(
    path,
    content,
    tokenize='unicode61'
);
"""

_CREATE_SYMBOLS = """
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path TEXT NOT NULL,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    parent TEXT,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    decorators TEXT,
    is_async INTEGER DEFAULT 0,
    FOREIGN KEY (relative_path) REFERENCES files(relative_path) ON DELETE CASCADE
);
"""

_CREATE_SYMBOLS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_path ON symbols(relative_path);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
"""

_CREATE_IMPORTS = """
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relative_path TEXT NOT NULL,
    imported_module TEXT NOT NULL,
    imported_name TEXT,
    alias TEXT,
    relative_level INTEGER DEFAULT 0,
    line INTEGER NOT NULL,
    FOREIGN KEY (relative_path) REFERENCES files(relative_path) ON DELETE CASCADE
);
"""

_CREATE_IMPORTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_imports_path ON imports(relative_path);
CREATE INDEX IF NOT EXISTS idx_imports_module ON imports(imported_module);
"""

_CREATE_OPERATIONS = """
CREATE TABLE IF NOT EXISTS operations (
    operation_id TEXT PRIMARY KEY,
    operation_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    result_json TEXT,
    error_json TEXT
);
"""

_CREATE_LOCK = """
CREATE TABLE IF NOT EXISTS index_lock (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    holder TEXT NOT NULL,
    acquired_at REAL NOT NULL
);
"""


@dataclass
class IndexMetadata:
    """Metadata about the index."""

    schema_version: int
    repository_root: str
    head_commit: str | None
    created_at: float
    updated_at: float
    file_count: int
    symbol_count: int


class IndexDatabase:
    """SQLite index database manager."""

    def __init__(self, db_path: Path, config: Config = DEFAULT_CONFIG) -> None:
        self.db_path = db_path
        self.config = config
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                conn = sqlite3.connect(
                    str(self.db_path),
                    timeout=5.0,
                    isolation_level=None,  # Autocommit mode
                )
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA foreign_keys=ON")
                self._local.connection = conn
            except sqlite3.Error as exc:
                raise IndexConnectionError(f"Failed to connect to index: {exc}")
        return self._local.connection

    def close(self) -> None:
        """Close the thread-local connection."""
        if hasattr(self._local, "connection") and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager for a transaction."""
        conn = self._get_connection()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def initialize(self) -> None:
        """Initialize the database schema."""
        conn = self._get_connection()
        conn.executescript(
            _CREATE_METADATA
            + _CREATE_FILES
            + _CREATE_FILE_TEXT_FTS
            + _CREATE_SYMBOLS
            + _CREATE_SYMBOLS_INDEX
            + _CREATE_IMPORTS
            + _CREATE_IMPORTS_INDEX
            + _CREATE_OPERATIONS
            + _CREATE_LOCK
        )
        # Set schema version if not present
        conn.execute(
            "INSERT OR IGNORE INTO index_metadata (key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )

    def check_schema_version(self) -> int:
        """Check the schema version; raises IndexSchemaError if incompatible."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM index_metadata WHERE key = ?",
                ("schema_version",),
            ).fetchone()
            if row is None:
                return 0
            version = int(row[0])
            if version != SCHEMA_VERSION:
                raise IndexSchemaError(
                    f"Schema version {version} is not supported. "
                    f"Expected version {SCHEMA_VERSION}. "
                    "Please rebuild the index."
                )
            return version
        except (sqlite3.Error, ValueError) as exc:
            raise IndexSchemaError(f"Failed to read schema version: {exc}")

    def get_metadata(self) -> IndexMetadata | None:
        """Get index metadata, or None if not initialized."""
        conn = self._get_connection()
        try:
            rows = conn.execute("SELECT key, value FROM index_metadata").fetchall()
            if not rows:
                return None

            data = {row[0]: row[1] for row in rows}
            schema_version = int(data.get("schema_version", 0))

            # Count files and symbols
            file_count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            symbol_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]

            return IndexMetadata(
                schema_version=schema_version,
                repository_root=data.get("repository_root", ""),
                head_commit=data.get("head_commit"),
                created_at=float(data.get("created_at", 0)),
                updated_at=float(data.get("updated_at", 0)),
                file_count=file_count,
                symbol_count=symbol_count,
            )
        except sqlite3.Error:
            return None

    def set_metadata(self, key: str, value: str) -> None:
        """Set a metadata value."""
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
            (key, value),
        )

    def acquire_lock(self, holder: str, timeout_seconds: float = 5.0) -> bool:
        """Acquire the index write lock; returns True if acquired."""
        conn = self._get_connection()
        deadline = time.time() + timeout_seconds

        while time.time() < deadline:
            if _try_acquire_lock(conn, holder):
                return True

        return False

    def release_lock(self, holder: str) -> bool:
        """Release the index write lock; returns False if not held by this holder."""
        return _release_lock(self._get_connection(), holder)

    def is_locked(self) -> tuple[bool, str | None]:
        """Check if the index is locked; returns (is_locked, holder)."""
        conn = self._get_connection()
        try:
            row = conn.execute(
                "SELECT holder FROM index_lock WHERE id = 1"
            ).fetchone()
            if row is None:
                return False, None
            return True, row[0]
        except sqlite3.Error:
            return False, None


def _try_acquire_lock(conn: sqlite3.Connection, holder: str) -> bool:
    """One lock acquisition attempt; clears stale locks. True when acquired."""
    try:
        conn.execute("BEGIN")
        # Check if lock exists
        row = conn.execute("SELECT holder FROM index_lock WHERE id = 1").fetchone()
        if row is None:
            # No lock, acquire it
            conn.execute(
                "INSERT INTO index_lock (id, holder, acquired_at) VALUES (1, ?, ?)",
                (holder, time.time()),
            )
            conn.execute("COMMIT")
            return True

        # Lock exists, check if stale (older than 10 minutes)
        conn.execute("ROLLBACK")
        acquired_row = conn.execute(
            "SELECT acquired_at FROM index_lock WHERE id = 1"
        ).fetchone()
        if acquired_row and (time.time() - acquired_row[0]) > 600:
            # Stale lock, force release and retry
            conn.execute("DELETE FROM index_lock WHERE id = 1")
            return False
        time.sleep(0.1)
        return False
    except sqlite3.Error:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        time.sleep(0.1)
        return False


def _release_lock(conn: sqlite3.Connection, holder: str) -> bool:
    """Release the lock if held by this holder."""
    try:
        conn.execute("BEGIN")
        row = conn.execute(
            "SELECT holder FROM index_lock WHERE id = 1"
        ).fetchone()
        if row is None or row[0] != holder:
            conn.execute("ROLLBACK")
            return False
        conn.execute("DELETE FROM index_lock WHERE id = 1")
        conn.execute("COMMIT")
        return True
    except sqlite3.Error:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        return False


@contextmanager
def open_index(
    repository_root: Path,
    config: Config = DEFAULT_CONFIG,
    create: bool = True,
) -> Iterator[IndexDatabase]:
    """Open an index database.

    Args:
        repository_root: Repository root directory
        config: Configuration to use
        create: Whether to create the database if it doesn't exist

    Yields:
        IndexDatabase instance
    """
    db_path = config.index_path(repository_root)

    if not db_path.exists() and not create:
        raise IndexConnectionError(f"Index database not found: {db_path}")

    db = IndexDatabase(db_path, config)
    try:
        if create:
            db.initialize()
        yield db
    finally:
        db.close()
