"""Automatic gap trigger system.

Schedules gap runs based on repository events.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError, success, error
from .gap_analysis import ANALYSIS_COMPLETE, find_gap
from .gap_models import (
    GapLevel,
    GapRecord,
    TriggerDigest,
    TriggerType,
    findings_from_dicts,
)
from .gap_records import find_gap_by_digest, gap_record


class TriggerError(RepositoryIntelligenceError):
    """Raised when trigger operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class TriggerConfig:
    """Configuration for automatic gap triggers."""
    auto_enabled: bool = True
    confirm_before_gap: bool = False
    skip_trivial: bool = True

    def as_dict(self) -> dict:
        return {
            "auto_enabled": self.auto_enabled,
            "confirm_before_gap": self.confirm_before_gap,
            "skip_trivial": self.skip_trivial,
        }


def compute_trigger_digest(
    task_id: str | None,
    plan_id: str | None,
    trigger_type: TriggerType,
    repository_head: str | None,
    changed_paths: list[str],
    repository_root: Path,
) -> str:
    """Compute a deterministic trigger digest for idempotency.
    
    Args:
        task_id: Optional task ID
        plan_id: Optional plan ID
        trigger_type: Type of trigger
        repository_head: Repository HEAD commit
        changed_paths: List of changed paths
        repository_root: Repository root directory
        
    Returns:
        Deterministic trigger digest
    """
    # Compute path hashes
    path_hashes = {}
    for rel_path in changed_paths:
        full_path = repository_root / rel_path
        if full_path.exists():
            content = full_path.read_bytes()
            path_hashes[rel_path] = hashlib.sha256(content).hexdigest()[:16]
        else:
            path_hashes[rel_path] = "missing"
    
    # Compute dirty state digest
    dirty_state = {
        "changed_paths": sorted(changed_paths),
        "path_hashes": dict(sorted(path_hashes.items())),
    }
    dirty_digest = hashlib.sha256(
        json.dumps(dirty_state, sort_keys=True).encode()
    ).hexdigest()[:16]
    
    # Build trigger digest
    trigger_digest = TriggerDigest(
        task_digest=task_id,
        plan_digest=plan_id,
        trigger_type=trigger_type,
        repository_head=repository_head,
        dirty_state_digest=dirty_digest,
        changed_path_hashes=path_hashes,
    )
    
    return trigger_digest.compute_digest()


def should_trigger_gap(
    trigger_type: TriggerType,
    config: TriggerConfig,
) -> bool:
    """Determine if the backend should auto-fire a gap run.

    The backend owns only repository-local apply events (decision 5).
    All other TriggerTypes stay valid request parameters for runtime or
    harness callers, but never auto-fire from backend code.
    """
    if not config.auto_enabled:
        return False

    return trigger_type in (TriggerType.FILE_APPLIED, TriggerType.CHANGESET_APPLIED)


_TRIGGER_LEVELS: dict[TriggerType, GapLevel] = {
    TriggerType.TASK_CREATED: GapLevel.PREVIEW,
    TriggerType.PLAN_CREATED: GapLevel.PREVIEW,
    TriggerType.FILE_APPLIED: GapLevel.INCREMENTAL,
    TriggerType.CHANGESET_APPLIED: GapLevel.INCREMENTAL,
    TriggerType.BUILD_SUCCESS: GapLevel.COMPLETION,
    TriggerType.IMPLEMENTATION_COMPLETE: GapLevel.COMPLETION,
    TriggerType.EXECUTION_FAILURE: GapLevel.DIAGNOSTIC,
}


def _persist_gap_result(
    repository_root: Path,
    trigger_type: TriggerType,
    level: GapLevel,
    trigger_digest: str,
    ids: dict[str, str | None],
    changed_paths: list[str] | None,
    gap_data: dict[str, Any],
    analysis_status: str,
    config: Config,
) -> None:
    """Persist a gap run's record with every live finding (decision 10)."""
    final_result = (
        "completed" if analysis_status == ANALYSIS_COMPLETE else analysis_status
    )
    gap_record(
        repository_root=repository_root,
        gap_run_id=gap_data.get("gap_run_id"),
        task_id=ids.get("task_id"),
        plan_id=ids.get("plan_id"),
        operation_id=ids.get("operation_id"),
        trigger_type=trigger_type,
        trigger_digest=trigger_digest,
        trigger_level=level,
        repository_state=gap_data.get("repository_state", {}),
        changed_paths=changed_paths or [],
        path_hashes=gap_data.get("path_hashes", {}),
        findings=findings_from_dicts(gap_data.get("findings", [])),
        no_material_gap=gap_data.get("no_material_gap", False),
        previous_run_id=None,
        final_result=final_result,
        config=config,
    )


def _run_and_persist_gap(
    repository_root: Path,
    trigger_type: TriggerType,
    level: GapLevel,
    trigger_digest: str,
    task_id: str | None,
    plan_id: str | None,
    operation_id: str | None,
    changed_paths: list[str] | None,
    success_definition: str | None,
    config: Config,
) -> dict:
    """Run the gap analysis, persist the record, and build the trigger result."""
    gap_result = find_gap(
        repository_root=repository_root,
        trigger_type=trigger_type,
        trigger_level=level,
        task_id=task_id,
        plan_id=plan_id,
        operation_id=operation_id,
        changed_paths=changed_paths,
        success_definition=success_definition,
        config=config,
    )
    if gap_result.get("status") != "success":
        return gap_result

    gap_data = gap_result.get("result", {})
    analysis_status = gap_data.get("analysis_status", ANALYSIS_COMPLETE)
    _persist_gap_result(
        repository_root, trigger_type, level, trigger_digest,
        {"task_id": task_id, "plan_id": plan_id, "operation_id": operation_id},
        changed_paths, gap_data, analysis_status, config,
    )

    return success("trigger_gap_run", {
        "triggered": True,
        "gap_run_id": gap_data.get("gap_run_id"),
        "trigger_type": trigger_type.value,
        "trigger_level": level.value,
        "trigger_digest": trigger_digest,
        "finding_count": len(gap_data.get("findings", [])),
        "analysis_status": analysis_status,
        "no_material_gap": gap_data.get("no_material_gap", False),
        "gap_analysis": gap_result,
    }).as_dict()


def trigger_gap_run(
    repository_root: Path,
    trigger_type: TriggerType,
    task_id: str | None = None,
    plan_id: str | None = None,
    operation_id: str | None = None,
    changed_paths: list[str] | None = None,
    success_definition: str | None = None,
    trigger_config: TriggerConfig | None = None,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Trigger a gap run based on an event.

    Checks idempotency, performs the gap analysis, and persists the record.

    Returns:
        Dictionary with trigger result
    """
    try:
        if trigger_config is None:
            trigger_config = TriggerConfig()

        if not should_trigger_gap(trigger_type, trigger_config):
            return success("trigger_gap_run", {
                "triggered": False,
                "reason": "auto_disabled_or_not_applicable",
            }).as_dict()

        level = _TRIGGER_LEVELS.get(trigger_type, GapLevel.INCREMENTAL)

        from .git_ops import get_repository_info
        repo_info = get_repository_info(repository_root)

        trigger_digest = compute_trigger_digest(
            task_id=task_id,
            plan_id=plan_id,
            trigger_type=trigger_type,
            repository_head=repo_info.get("head"),
            changed_paths=changed_paths or [],
            repository_root=repository_root,
        )

        existing = find_gap_by_digest(repository_root, trigger_digest, config)
        if existing.get("status") == "success" and existing.get("result", {}).get("found"):
            return success("trigger_gap_run", {
                "triggered": False,
                "reason": "duplicate_trigger",
                "existing_gap_run_id": existing["result"]["gap_run_id"],
            }).as_dict()

        return _run_and_persist_gap(
            repository_root, trigger_type, level, trigger_digest,
            task_id, plan_id, operation_id, changed_paths,
            success_definition, config,
        )

    except RepositoryIntelligenceError as exc:
        return error("trigger_gap_run", exc.code, exc.detail).as_dict()
    except Exception as exc:
        return error("trigger_gap_run", "trigger_failed", str(exc)).as_dict()
