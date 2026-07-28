"""Runtime-facing completion analysis interface.

Python-level API (deliberately not an MCP tool) that the runtime
operation state owner calls before recording completion. The backend
produces gap evidence only; final completion authority belongs to the
runtime operation state owner (decisions 4 and 7).
"""

from __future__ import annotations

from pathlib import Path

from .config import Config, DEFAULT_CONFIG
from .contracts import success, error
from .gap_analysis import ANALYSIS_COMPLETE, find_gap
from .gap_models import GapLevel, TriggerType, findings_from_dicts
from .gap_records import gap_record


def _persist_completion_record(
    repository_root: Path,
    ids: dict[str, str | None],
    changed_paths: list[str] | None,
    result: dict,
    analysis_status: str,
    config: Config,
) -> dict:
    """Persist the completion gap run and return the gap_record result."""
    final_result = (
        "completed" if analysis_status == ANALYSIS_COMPLETE else analysis_status
    )
    return gap_record(
        repository_root=repository_root,
        gap_run_id=result.get("gap_run_id"),
        task_id=ids.get("task_id"),
        plan_id=ids.get("plan_id"),
        operation_id=ids.get("operation_id"),
        trigger_type=TriggerType.IMPLEMENTATION_COMPLETE,
        trigger_digest=result.get("trigger_digest", ""),
        trigger_level=GapLevel.COMPLETION,
        repository_state=result.get("repository_state", {}),
        changed_paths=changed_paths or [],
        path_hashes=result.get("path_hashes", {}),
        findings=findings_from_dicts(result.get("findings", [])),
        no_material_gap=result.get("no_material_gap", False),
        previous_run_id=None,
        final_result=final_result,
        config=config,
    )


def analyze_completion(
    repository_root: Path,
    task_id: str | None = None,
    plan_id: str | None = None,
    operation_id: str | None = None,
    changed_paths: list[str] | None = None,
    success_definition: str | None = None,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Run a completion-level gap analysis and persist the record.

    Returns the persisted gap evidence for the caller to consume before
    recording completion. This function never decides completion itself:
    while completion analysis remains a placeholder, analysis_status is
    "evidence_incomplete" and no_material_gap is always False.
    """
    gap_result = find_gap(
        repository_root=repository_root,
        trigger_type=TriggerType.IMPLEMENTATION_COMPLETE,
        trigger_level=GapLevel.COMPLETION,
        task_id=task_id,
        plan_id=plan_id,
        operation_id=operation_id,
        changed_paths=changed_paths,
        success_definition=success_definition,
        config=config,
    )
    if gap_result.get("status") != "success":
        return gap_result

    result = gap_result.get("result", {})
    analysis_status = result.get("analysis_status", ANALYSIS_COMPLETE)
    record_result = _persist_completion_record(
        repository_root,
        {"task_id": task_id, "plan_id": plan_id, "operation_id": operation_id},
        changed_paths, result, analysis_status, config,
    )
    if record_result.get("status") != "success":
        return error(
            "analyze_completion",
            "gap_record_failed",
            str(record_result.get("error", {})),
        ).as_dict()

    return success("analyze_completion", {
        "gap_run_id": result.get("gap_run_id"),
        "trigger_digest": result.get("trigger_digest"),
        "analysis_status": analysis_status,
        "no_material_gap": result.get("no_material_gap", False),
        "finding_count": result.get("finding_count", 0),
        "findings": result.get("findings", []),
        "persisted": True,
    }).as_dict()
