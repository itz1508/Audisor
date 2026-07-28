"""Gap record persistence.

Stores and retrieves gap analysis records in the repository index.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError, success, error
from .gap_models import (
    GapCategory,
    GapFinding,
    GapLevel,
    GapRecord,
    GapSeverity,
    GapStatus,
    TriggerType,
    EvidenceLocation,
)
from .index_db import open_index


class GapRecordError(RepositoryIntelligenceError):
    """Raised when gap record operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


def _ensure_gap_tables(conn) -> None:
    """Ensure gap analysis tables exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gap_records (
            gap_run_id TEXT PRIMARY KEY,
            task_id TEXT,
            plan_id TEXT,
            operation_id TEXT,
            trigger_type TEXT NOT NULL,
            trigger_digest TEXT NOT NULL,
            trigger_level TEXT NOT NULL,
            repository_state TEXT NOT NULL,
            changed_paths TEXT NOT NULL,
            path_hashes TEXT NOT NULL,
            findings TEXT NOT NULL,
            no_material_gap INTEGER NOT NULL,
            previous_run_id TEXT,
            final_result TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS gap_findings (
            gap_id TEXT PRIMARY KEY,
            gap_run_id TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            expected_claim TEXT NOT NULL,
            observed_state TEXT NOT NULL,
            evidence_locations TEXT NOT NULL,
            affected_paths TEXT NOT NULL,
            required_correction TEXT NOT NULL,
            required_validation TEXT NOT NULL,
            confidence REAL NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY (gap_run_id) REFERENCES gap_records(gap_run_id)
        )
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gap_records_digest
        ON gap_records(trigger_digest)
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_gap_records_task
        ON gap_records(task_id)
    """)


def _insert_record_row(conn, record: dict[str, Any]) -> None:
    """Insert the gap_records row from a prepared field mapping."""
    conn.execute(
        """
        INSERT INTO gap_records (
            gap_run_id, task_id, plan_id, operation_id,
            trigger_type, trigger_digest, trigger_level,
            repository_state, changed_paths, path_hashes,
            findings, no_material_gap, previous_run_id,
            final_result, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record["gap_run_id"],
            record["task_id"],
            record["plan_id"],
            record["operation_id"],
            record["trigger_type"].value,
            record["trigger_digest"],
            record["trigger_level"].value,
            json.dumps(record["repository_state"]),
            json.dumps(record["changed_paths"]),
            json.dumps(record["path_hashes"]),
            json.dumps([f.as_dict() for f in record["findings"]]),
            1 if record["no_material_gap"] else 0,
            record["previous_run_id"],
            record["final_result"],
            time.time(),
        ),
    )


def _insert_finding_rows(conn, gap_run_id: str, findings: list[GapFinding]) -> None:
    """Insert one gap_findings row per finding."""
    for finding in findings:
        conn.execute(
            """
            INSERT INTO gap_findings (
                gap_id, gap_run_id, category, severity,
                expected_claim, observed_state, evidence_locations,
                affected_paths, required_correction, required_validation,
                confidence, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.gap_id,
                gap_run_id,
                finding.category.value,
                finding.severity.value,
                finding.expected_claim,
                finding.observed_state,
                json.dumps([e.as_dict() for e in finding.evidence_locations]),
                json.dumps(finding.affected_paths),
                finding.required_correction,
                finding.required_validation,
                finding.confidence,
                finding.status.value,
            ),
        )


def gap_record(
    repository_root: Path,
    gap_run_id: str,
    task_id: str | None,
    plan_id: str | None,
    operation_id: str | None,
    trigger_type: TriggerType,
    trigger_digest: str,
    trigger_level: GapLevel,
    repository_state: dict[str, Any],
    changed_paths: list[str],
    path_hashes: dict[str, str],
    findings: list[GapFinding],
    no_material_gap: bool,
    previous_run_id: str | None,
    final_result: str,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Persist a gap analysis record.

    Returns:
        Dictionary with gap record result
    """
    try:
        record = {
            "gap_run_id": gap_run_id,
            "task_id": task_id,
            "plan_id": plan_id,
            "operation_id": operation_id,
            "trigger_type": trigger_type,
            "trigger_digest": trigger_digest,
            "trigger_level": trigger_level,
            "repository_state": repository_state,
            "changed_paths": changed_paths,
            "path_hashes": path_hashes,
            "findings": findings,
            "no_material_gap": no_material_gap,
            "previous_run_id": previous_run_id,
            "final_result": final_result,
        }
        with open_index(repository_root, config, create=True) as db:
            conn = db._get_connection()
            _ensure_gap_tables(conn)
            _insert_record_row(conn, record)
            _insert_finding_rows(conn, gap_run_id, findings)

        result = {
            "gap_run_id": gap_run_id,
            "stored": True,
            "finding_count": len(findings),
            "no_material_gap": no_material_gap,
        }
        return success("gap_record", result).as_dict()

    except Exception as exc:
        return error("gap_record", "gap_record_failed", str(exc)).as_dict()


def get_gap_record(
    repository_root: Path,
    gap_run_id: str,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Retrieve a gap record by ID.
    
    Args:
        repository_root: Repository root directory
        gap_run_id: Gap run ID
        config: Configuration to use
        
    Returns:
        Dictionary with gap record or error
    """
    try:
        with open_index(repository_root, config, create=False) as db:
            conn = db._get_connection()
            
            row = conn.execute(
                "SELECT * FROM gap_records WHERE gap_run_id = ?",
                (gap_run_id,),
            ).fetchone()
            
            if not row:
                return error("get_gap_record", "gap_not_found", f"Gap record {gap_run_id} not found").as_dict()
            
            # Parse JSON fields
            record = {
                "gap_run_id": row["gap_run_id"],
                "task_id": row["task_id"],
                "plan_id": row["plan_id"],
                "operation_id": row["operation_id"],
                "trigger_type": row["trigger_type"],
                "trigger_digest": row["trigger_digest"],
                "trigger_level": row["trigger_level"],
                "repository_state": json.loads(row["repository_state"]),
                "changed_paths": json.loads(row["changed_paths"]),
                "path_hashes": json.loads(row["path_hashes"]),
                "findings": json.loads(row["findings"]),
                "no_material_gap": bool(row["no_material_gap"]),
                "previous_run_id": row["previous_run_id"],
                "final_result": row["final_result"],
                "created_at": row["created_at"],
            }
            
            return success("get_gap_record", record).as_dict()
            
    except Exception as exc:
        return error("get_gap_record", "gap_record_failed", str(exc)).as_dict()


def find_gap_by_digest(
    repository_root: Path,
    trigger_digest: str,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Find a gap record by trigger digest (for idempotency).
    
    Args:
        repository_root: Repository root directory
        trigger_digest: Trigger digest to search for
        config: Configuration to use
        
    Returns:
        Dictionary with gap record or None
    """
    try:
        with open_index(repository_root, config, create=False) as db:
            conn = db._get_connection()
            
            row = conn.execute(
                "SELECT gap_run_id FROM gap_records WHERE trigger_digest = ?",
                (trigger_digest,),
            ).fetchone()
            
            if not row:
                return success("find_gap_by_digest", {"found": False}).as_dict()
            
            return success("find_gap_by_digest", {
                "found": True,
                "gap_run_id": row["gap_run_id"],
            }).as_dict()
            
    except Exception as exc:
        return error("find_gap_by_digest", "gap_record_failed", str(exc)).as_dict()
