"""Gap analysis MCP tools.

Provides tools for gap analysis initialization and recording.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError, success, error
from .gap_analysis import generate_gap_run_id
from .gap_models import (
    GapLevel,
    TriggerType,
    findings_from_dicts,
)
from .gap_records import gap_record as gap_record_impl

_TRIGGER_LEVELS: dict[TriggerType, GapLevel] = {
    TriggerType.TASK_CREATED: GapLevel.PREVIEW,
    TriggerType.PLAN_CREATED: GapLevel.PREVIEW,
    TriggerType.FILE_APPLIED: GapLevel.INCREMENTAL,
    TriggerType.CHANGESET_APPLIED: GapLevel.INCREMENTAL,
    TriggerType.BUILD_SUCCESS: GapLevel.COMPLETION,
    TriggerType.IMPLEMENTATION_COMPLETE: GapLevel.COMPLETION,
    TriggerType.EXECUTION_FAILURE: GapLevel.DIAGNOSTIC,
}


def create_gap(
    repository_root: Path,
    task_id: str | None = None,
    plan_id: str | None = None,
    operation_id: str | None = None,
    trigger_type: str = "task_created",
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Initialize a gap analysis run for a task, plan, or operation.

    Returns:
        Dictionary with gap run initialization result
    """
    try:
        try:
            trigger_enum = TriggerType(trigger_type)
        except ValueError:
            return error("create_gap", "invalid_trigger_type", f"Unknown trigger type: {trigger_type}").as_dict()

        level = _TRIGGER_LEVELS.get(trigger_enum, GapLevel.INCREMENTAL)
        result = {
            "gap_run_id": generate_gap_run_id(),
            "trigger_type": trigger_enum.value,
            "trigger_level": level.value,
            "task_id": task_id,
            "plan_id": plan_id,
            "operation_id": operation_id,
            "status": "initialized",
        }
        return success("create_gap", result).as_dict()

    except RepositoryIntelligenceError as exc:
        return error("create_gap", exc.code, exc.detail).as_dict()
    except Exception as exc:
        return error("create_gap", "gap_creation_failed", str(exc)).as_dict()


def gap_record_tool(
    repository_root: Path,
    gap_run_id: str,
    task_id: str | None = None,
    plan_id: str | None = None,
    operation_id: str | None = None,
    trigger_type: str = "file_applied",
    trigger_digest: str = "",
    trigger_level: str = "incremental_gap",
    repository_state: dict[str, Any] | None = None,
    changed_paths: list[str] | None = None,
    path_hashes: dict[str, str] | None = None,
    findings: list[dict] | None = None,
    no_material_gap: bool = True,
    previous_run_id: str | None = None,
    final_result: str = "completed",
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Persist a gap analysis record.

    Returns:
        Dictionary with gap record result
    """
    try:
        try:
            trigger_enum = TriggerType(trigger_type)
        except ValueError:
            return error("gap_record", "invalid_trigger_type", f"Unknown trigger type: {trigger_type}").as_dict()
        try:
            level_enum = GapLevel(trigger_level)
        except ValueError:
            return error("gap_record", "invalid_trigger_level", f"Unknown trigger level: {trigger_level}").as_dict()

        return gap_record_impl(
            repository_root=repository_root,
            gap_run_id=gap_run_id,
            task_id=task_id,
            plan_id=plan_id,
            operation_id=operation_id,
            trigger_type=trigger_enum,
            trigger_digest=trigger_digest,
            trigger_level=level_enum,
            repository_state=repository_state or {},
            changed_paths=changed_paths or [],
            path_hashes=path_hashes or {},
            findings=findings_from_dicts(findings),
            no_material_gap=no_material_gap,
            previous_run_id=previous_run_id,
            final_result=final_result,
            config=config,
        )

    except RepositoryIntelligenceError as exc:
        return error("gap_record", exc.code, exc.detail).as_dict()
    except Exception as exc:
        return error("gap_record", "gap_record_failed", str(exc)).as_dict()
