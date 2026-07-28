"""Operation registry for tracking long-running operations."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError
from .index_db import open_index


class OperationStatus(str, Enum):
    """Operation status values."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class OperationError(RepositoryIntelligenceError):
    """Raised when operation operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class Operation:
    """An operation record."""

    operation_id: str
    operation_type: str
    status: OperationStatus
    created_at: float
    started_at: float | None
    completed_at: float | None
    result: dict[str, Any] | None
    error: dict[str, str] | None

    def as_dict(self) -> dict:
        result_dict: dict[str, Any] = {
            "operation_id": self.operation_id,
            "operation_type": self.operation_type,
            "status": self.status.value,
            "created_at": self.created_at,
        }
        if self.started_at is not None:
            result_dict["started_at"] = self.started_at
        if self.completed_at is not None:
            result_dict["completed_at"] = self.completed_at
        if self.result is not None:
            result_dict["result"] = self.result
        if self.error is not None:
            result_dict["error"] = self.error
        return result_dict


def generate_operation_id() -> str:
    """Generate a unique operation ID."""
    return f"op-{uuid.uuid4().hex[:12]}"


def create_operation(
    repository_root: Path,
    operation_type: str,
    config: Config = DEFAULT_CONFIG,
) -> Operation:
    """Create a new operation.

    Args:
        repository_root: Repository root directory
        operation_type: Type of operation
        config: Configuration to use

    Returns:
        Operation object
    """
    operation_id = generate_operation_id()
    now = time.time()

    operation = Operation(
        operation_id=operation_id,
        operation_type=operation_type,
        status=OperationStatus.QUEUED,
        created_at=now,
        started_at=None,
        completed_at=None,
        result=None,
        error=None,
    )

    with open_index(repository_root, config, create=True) as db:
        conn = db._get_connection()
        conn.execute(
            """
            INSERT INTO operations (operation_id, operation_type, status, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (operation_id, operation_type, OperationStatus.QUEUED.value, now),
        )

    return operation


def start_operation(
    repository_root: Path,
    operation_id: str,
    config: Config = DEFAULT_CONFIG,
) -> bool:
    """Mark an operation as started.

    Args:
        repository_root: Repository root directory
        operation_id: Operation ID
        config: Configuration to use

    Returns:
        True if operation was started, False if not found
    """
    now = time.time()

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()
        result = conn.execute(
            """
            UPDATE operations
            SET status = ?, started_at = ?
            WHERE operation_id = ? AND status = ?
            """,
            (OperationStatus.RUNNING.value, now, operation_id, OperationStatus.QUEUED.value),
        )
        return result.rowcount > 0


def complete_operation(
    repository_root: Path,
    operation_id: str,
    result: dict[str, Any] | None = None,
    config: Config = DEFAULT_CONFIG,
) -> bool:
    """Mark an operation as completed.

    Args:
        repository_root: Repository root directory
        operation_id: Operation ID
        result: Operation result
        config: Configuration to use

    Returns:
        True if operation was completed, False if not found
    """
    now = time.time()

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()
        result_json = json.dumps(result) if result else None
        update_result = conn.execute(
            """
            UPDATE operations
            SET status = ?, completed_at = ?, result_json = ?
            WHERE operation_id = ?
            """,
            (OperationStatus.COMPLETED.value, now, result_json, operation_id),
        )
        return update_result.rowcount > 0


def fail_operation(
    repository_root: Path,
    operation_id: str,
    error_code: str,
    error_detail: str,
    config: Config = DEFAULT_CONFIG,
) -> bool:
    """Mark an operation as failed.

    Args:
        repository_root: Repository root directory
        operation_id: Operation ID
        error_code: Error code
        error_detail: Error detail
        config: Configuration to use

    Returns:
        True if operation was marked failed, False if not found
    """
    now = time.time()

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()
        error_json = json.dumps({"code": error_code, "detail": error_detail})
        result = conn.execute(
            """
            UPDATE operations
            SET status = ?, completed_at = ?, error_json = ?
            WHERE operation_id = ?
            """,
            (OperationStatus.FAILED.value, now, error_json, operation_id),
        )
        return result.rowcount > 0


def _operation_from_row(row) -> Operation:
    """Build an Operation from a database row."""
    result = None
    if row[6]:
        try:
            result = json.loads(row[6])
        except json.JSONDecodeError:
            pass

    error = None
    if row[7]:
        try:
            error = json.loads(row[7])
        except json.JSONDecodeError:
            pass

    return Operation(
        operation_id=row[0],
        operation_type=row[1],
        status=OperationStatus(row[2]),
        created_at=row[3],
        started_at=row[4],
        completed_at=row[5],
        result=result,
        error=error,
    )


def get_operation(
    repository_root: Path,
    operation_id: str,
    config: Config = DEFAULT_CONFIG,
) -> Operation | None:
    """Get an operation by ID.

    Args:
        repository_root: Repository root directory
        operation_id: Operation ID
        config: Configuration to use

    Returns:
        Operation object or None if not found
    """
    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()
        row = conn.execute(
            """
            SELECT operation_id, operation_type, status, created_at,
                   started_at, completed_at, result_json, error_json
            FROM operations
            WHERE operation_id = ?
            """,
            (operation_id,),
        ).fetchone()

        if row is None:
            return None

        return _operation_from_row(row)


def list_operations(
    repository_root: Path,
    status: OperationStatus | None = None,
    operation_type: str | None = None,
    limit: int = 100,
    config: Config = DEFAULT_CONFIG,
) -> list[Operation]:
    """List operations.

    Args:
        repository_root: Repository root directory
        status: Optional status filter
        operation_type: Optional type filter
        limit: Maximum results
        config: Configuration to use

    Returns:
        List of Operation objects
    """
    operations: list[Operation] = []

    with open_index(repository_root, config, create=False) as db:
        conn = db._get_connection()

        sql = """
            SELECT operation_id, operation_type, status, created_at,
                   started_at, completed_at, result_json, error_json
            FROM operations
            WHERE 1=1
        """
        params: list = []

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        if operation_type:
            sql += " AND operation_type = ?"
            params.append(operation_type)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        for row in rows:
            operations.append(_operation_from_row(row))

    return operations
