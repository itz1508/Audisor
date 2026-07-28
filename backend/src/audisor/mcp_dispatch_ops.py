"""Dispatch handlers: git, commands, diagnostics, mutation, and gap analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .mcp_schemas import blocked_payload as _error
from .repo_intelligence import success, error
from .repo_intelligence.commands import run_command, run_validation, CommandError
from .repo_intelligence.contracts import RepositoryIntelligenceError
from .repo_intelligence.diagnostics import (
    parse_test_failures,
    parse_python_traceback,
    summarise_command_failure,
)
from .repo_intelligence.gap_analysis import find_gap
from .repo_intelligence.gap_models import TriggerType, GapLevel
from .repo_intelligence.gap_tools import create_gap, gap_record_tool
from .repo_intelligence.gap_triggers import trigger_gap_run
from .repo_intelligence.git_ops import git_status, git_diff, git_history, git_show_file, GitError
from .repo_intelligence.indexer import incremental_refresh
from .repo_intelligence.operations import get_operation, OperationStatus
from .repo_intelligence.patch import prepare_patch, apply_patch, PatchError


def dispatch_git(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle git inspection tools."""
    if name == "git_status":
        try:
            entries = git_status(root)
            return success("git_status", {"entries": [e.as_dict() for e in entries]}).as_dict()
        except GitError as exc:
            return error("git_status", exc.code, exc.detail).as_dict()
    if name == "git_diff":
        try:
            result = git_diff(
                root,
                path=arguments.get("path"),
                staged=arguments.get("staged", False),
            )
            return success("git_diff", result).as_dict()
        except GitError as exc:
            return error("git_diff", exc.code, exc.detail).as_dict()
    if name == "git_history":
        try:
            commits = git_history(
                root,
                path=arguments.get("path"),
                max_commits=arguments.get("max_commits"),
            )
            return success("git_history", {"commits": [c.as_dict() for c in commits]}).as_dict()
        except GitError as exc:
            return error("git_history", exc.code, exc.detail).as_dict()
    if name == "git_show_file":
        try:
            result = git_show_file(root, arguments["revision"], arguments["path"])
            return success("git_show_file", result).as_dict()
        except GitError as exc:
            return error("git_show_file", exc.code, exc.detail).as_dict()
    return None


def dispatch_commands(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle command execution and operation tools."""
    if name == "run_command":
        try:
            result = run_command(
                root,
                command=arguments["command"],
                timeout_seconds=arguments.get("timeout_seconds"),
                working_directory=arguments.get("working_directory"),
            )
            return success("run_command", result.as_dict()).as_dict()
        except CommandError as exc:
            return error("run_command", exc.code, exc.detail).as_dict()
    if name == "run_validation":
        try:
            result = run_validation(
                root,
                profile=arguments["profile"],
                path=arguments.get("path"),
                timeout_seconds=arguments.get("timeout_seconds"),
            )
            return success("run_validation", result.as_dict()).as_dict()
        except CommandError as exc:
            return error("run_validation", exc.code, exc.detail).as_dict()
    if name == "refresh_paths":
        try:
            stats = incremental_refresh(root, paths=arguments["paths"])
            return success("refresh_paths", stats.as_dict()).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("refresh_paths", exc.code, exc.detail).as_dict()
    return None


def dispatch_operations(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle operation status and result tools."""
    if name == "operation_status":
        try:
            op = get_operation(root, arguments["operation_id"])
            if op is None:
                return error("operation_status", "not_found", f"Operation not found: {arguments['operation_id']}").as_dict()
            return success("operation_status", op.as_dict()).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("operation_status", exc.code, exc.detail).as_dict()
    if name == "operation_result":
        try:
            op = get_operation(root, arguments["operation_id"])
            if op is None:
                return error("operation_result", "not_found", f"Operation not found: {arguments['operation_id']}").as_dict()
            if op.status != OperationStatus.COMPLETED:
                return error(
                    "operation_result",
                    "not_completed",
                    f"Operation is not completed (status: {op.status.value})",
                ).as_dict()
            return success("operation_result", op.as_dict()).as_dict()
        except RepositoryIntelligenceError as exc:
            return error("operation_result", exc.code, exc.detail).as_dict()
    return None


def dispatch_diagnostics(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle output-parsing diagnostic tools."""
    if name == "parse_test_failures":
        failures = parse_test_failures(arguments["output"])
        return success("parse_test_failures", {"failures": [f.as_dict() for f in failures]}).as_dict()
    if name == "parse_python_traceback":
        tb = parse_python_traceback(arguments["output"])
        if tb is None:
            return success("parse_python_traceback", {"traceback": None, "message": "No traceback found"}).as_dict()
        return success("parse_python_traceback", tb.as_dict()).as_dict()
    if name == "summarise_command_failure":
        summary = summarise_command_failure(
            exit_code=arguments["exit_code"],
            timed_out=arguments["timed_out"],
            stdout=arguments["stdout"],
            stderr=arguments["stderr"],
        )
        return success("summarise_command_failure", summary.as_dict()).as_dict()
    return None


def dispatch_mutation(name: str, root: Path | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle patch preparation and application tools."""
    if name == "prepare_patch":
        try:
            preview = prepare_patch(
                root,
                relative_path=arguments["path"],
                new_content=arguments["new_content"],
                expected_sha256=arguments.get("expected_sha256"),
                start_line=arguments.get("start_line"),
                end_line=arguments.get("end_line"),
            )
            return success("prepare_patch", preview.as_dict()).as_dict()
        except PatchError as exc:
            return error("prepare_patch", exc.code, exc.detail).as_dict()
    if name == "apply_patch":
        try:
            result = apply_patch(
                root,
                relative_path=arguments["path"],
                new_content=arguments["new_content"],
                expected_sha256=arguments["expected_sha256"],
                patch_id=arguments.get("patch_id"),
            )
            payload = result.as_dict()
            payload.update(_post_apply_gap(root, arguments["path"]))
            return success("apply_patch", payload).as_dict()
        except PatchError as exc:
            return error("apply_patch", exc.code, exc.detail).as_dict()
    return None


def _post_apply_gap(root: Path, relative_path: str) -> dict[str, Any]:
    """Run the apply-triggered refresh and incremental gap run.

    The mutation already succeeded; refresh or gap failures are reported
    in the payload instead of voiding the apply result.
    """
    outcome: dict[str, Any] = {}
    try:
        stats = incremental_refresh(root, paths=[relative_path])
        outcome["refresh"] = stats.as_dict()
    except RepositoryIntelligenceError as exc:
        outcome["refresh"] = {"error": {"code": exc.code, "detail": exc.detail}}

    gap_trigger = trigger_gap_run(
        repository_root=root,
        trigger_type=TriggerType.FILE_APPLIED,
        changed_paths=[relative_path],
    )
    if gap_trigger.get("status") == "success":
        trigger_result = dict(gap_trigger.get("result", {}))
        trigger_result.pop("gap_analysis", None)  # persisted record is authoritative
        outcome["gap"] = trigger_result
    else:
        outcome["gap"] = {"error": gap_trigger.get("error", {})}
    return outcome


def dispatch_gap(name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    """Handle gap analysis tools."""
    if name == "create_gap":
        root = Path(arguments["repository_root"])
        if not root.is_dir():
            return _error("repository_not_found", arguments["repository_root"])
        return create_gap(
            repository_root=root,
            task_id=arguments.get("task_id"),
            plan_id=arguments.get("plan_id"),
            operation_id=arguments.get("operation_id"),
            trigger_type=arguments.get("trigger_type", "task_created"),
        )
    if name == "find_gap":
        return _dispatch_find_gap(arguments)
    if name == "gap_record":
        root = Path(arguments["repository_root"])
        if not root.is_dir():
            return _error("repository_not_found", arguments["repository_root"])
        return gap_record_tool(
            repository_root=root,
            gap_run_id=arguments["gap_run_id"],
            task_id=arguments.get("task_id"),
            plan_id=arguments.get("plan_id"),
            operation_id=arguments.get("operation_id"),
            trigger_type=arguments["trigger_type"],
            trigger_digest=arguments["trigger_digest"],
            trigger_level=arguments["trigger_level"],
            repository_state=arguments.get("repository_state"),
            changed_paths=arguments.get("changed_paths"),
            path_hashes=arguments.get("path_hashes"),
            findings=arguments.get("findings"),
            no_material_gap=arguments.get("no_material_gap", True),
            previous_run_id=arguments.get("previous_run_id"),
            final_result=arguments.get("final_result", "completed"),
        )
    return None


def _dispatch_find_gap(arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate find_gap arguments and run the analysis."""
    root = Path(arguments["repository_root"])
    if not root.is_dir():
        return _error("repository_not_found", arguments["repository_root"])
    try:
        trigger_type = TriggerType(arguments["trigger_type"])
    except ValueError:
        return _error("invalid_trigger_type", f"Unknown trigger type: {arguments['trigger_type']}")
    try:
        trigger_level = GapLevel(arguments["trigger_level"])
    except ValueError:
        return _error("invalid_trigger_level", f"Unknown trigger level: {arguments['trigger_level']}")
    return find_gap(
        repository_root=root,
        trigger_type=trigger_type,
        trigger_level=trigger_level,
        task_id=arguments.get("task_id"),
        plan_id=arguments.get("plan_id"),
        operation_id=arguments.get("operation_id"),
        changed_paths=arguments.get("changed_paths"),
        success_definition=arguments.get("success_definition"),
    )
