"""Gap analysis engine.

Read-only evidence-based gap analysis using repository intelligence.
"""

from __future__ import annotations

import hashlib
import time
import uuid
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
    TriggerDigest,
    TriggerType,
    EvidenceLocation,
)
from .git_ops import get_repository_info, git_status
from .indexer import get_index_status, incremental_refresh
from .search import search_text


class GapAnalysisError(RepositoryIntelligenceError):
    """Raised when gap analysis fails."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


# Analysis-status values reported by find_gap.
ANALYSIS_COMPLETE = "complete"
EVIDENCE_INCOMPLETE = "evidence_incomplete"


def generate_gap_id() -> str:
    """Generate a unique gap ID."""
    return f"gap-{uuid.uuid4().hex[:12]}"


def generate_gap_run_id() -> str:
    """Generate a unique gap run ID."""
    return f"gaprun-{uuid.uuid4().hex[:12]}"


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    if not path.exists():
        return "missing"
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest()[:16]


def _hash_changed_paths(repository_root: Path, changed_paths: list[str]) -> dict[str, str]:
    """Hash each changed path for trigger idempotency."""
    return {
        rel_path: compute_file_hash(repository_root / rel_path)
        for rel_path in changed_paths
    }


def _compute_trigger_digest(
    task_id: str | None,
    plan_id: str | None,
    trigger_type: TriggerType,
    repository_head: str | None,
    path_hashes: dict[str, str],
    success_definition: str | None,
) -> str:
    """Compute the idempotency digest for a gap trigger."""
    trigger_digest = TriggerDigest(
        task_digest=task_id,
        plan_digest=plan_id,
        trigger_type=trigger_type,
        repository_head=repository_head,
        changed_path_hashes=path_hashes,
        success_definition_digest=(
            hashlib.sha256(success_definition.encode()).hexdigest()[:16]
            if success_definition else None
        ),
    )
    return trigger_digest.compute_digest()


def _build_gap_result(
    trigger_type: TriggerType,
    trigger_level: GapLevel,
    digest: str,
    ids: dict[str, str | None],
    repository_state: dict[str, Any],
    changed_paths: list[str],
    path_hashes: dict[str, str],
    findings: list[GapFinding],
    analysis_status: str,
) -> dict[str, Any]:
    """Assemble the find_gap result payload."""
    # A placeholder analysis never claims no material gap (decision 9).
    no_material_gap = analysis_status == ANALYSIS_COMPLETE and (
        len(findings) == 0 or all(
            f.severity in (GapSeverity.LOW, GapSeverity.INFO) for f in findings
        )
    )
    return {
        "gap_run_id": generate_gap_run_id(),
        "trigger_type": trigger_type.value,
        "trigger_level": trigger_level.value,
        "trigger_digest": digest,
        "task_id": ids.get("task_id"),
        "plan_id": ids.get("plan_id"),
        "operation_id": ids.get("operation_id"),
        "repository_state": repository_state,
        "changed_paths": changed_paths,
        "path_hashes": path_hashes,
        "findings": [f.as_dict() for f in findings],
        "analysis_status": analysis_status,
        "no_material_gap": no_material_gap,
        "finding_count": len(findings),
    }


def find_gap(
    repository_root: Path,
    trigger_type: TriggerType,
    trigger_level: GapLevel,
    task_id: str | None = None,
    plan_id: str | None = None,
    operation_id: str | None = None,
    changed_paths: list[str] | None = None,
    success_definition: str | None = None,
    config: Config = DEFAULT_CONFIG,
) -> dict:
    """Perform read-only gap analysis.

    Examines the repository state and identifies gaps between expected
    and observed state.

    Returns:
        Dictionary with gap analysis results
    """
    try:
        repo_info = get_repository_info(repository_root)
        index_status = get_index_status(repository_root)
        path_hashes = _hash_changed_paths(repository_root, changed_paths or [])
        digest = _compute_trigger_digest(
            task_id, plan_id, trigger_type, repo_info.get("head"),
            path_hashes, success_definition,
        )
        findings, analysis_status = _analyze_gaps(
            repository_root, trigger_level, changed_paths or [],
            success_definition, config,
        )
        result = _build_gap_result(
            trigger_type=trigger_type,
            trigger_level=trigger_level,
            digest=digest,
            ids={"task_id": task_id, "plan_id": plan_id, "operation_id": operation_id},
            repository_state={
                "head": repo_info.get("head"),
                "branch": repo_info.get("branch"),
                "index_status": index_status,
            },
            changed_paths=changed_paths or [],
            path_hashes=path_hashes,
            findings=findings,
            analysis_status=analysis_status,
        )
        return success("find_gap", result).as_dict()

    except RepositoryIntelligenceError as exc:
        return error("find_gap", exc.code, exc.detail).as_dict()
    except Exception as exc:
        return error("find_gap", "gap_analysis_failed", str(exc)).as_dict()


def _analyze_gaps(
    repository_root: Path,
    trigger_level: GapLevel,
    changed_paths: list[str],
    success_definition: str | None,
    config: Config,
) -> tuple[list[GapFinding], str]:
    """Analyze gaps based on trigger level.

    Returns the findings plus the analysis status: ANALYSIS_COMPLETE when
    real evidence analysis ran, EVIDENCE_INCOMPLETE when a placeholder
    path was involved (decision 9: placeholders never prove absence of
    material gaps).
    """
    findings: list[GapFinding] = []
    analysis_status = ANALYSIS_COMPLETE

    # For preview and incremental levels, check changed paths
    if trigger_level in (GapLevel.PREVIEW, GapLevel.INCREMENTAL):
        findings.extend(_check_changed_paths(repository_root, changed_paths, config))

    # For completion level, check against success definition
    if trigger_level == GapLevel.COMPLETION:
        completion_findings, complete = _check_success_definition(
            repository_root, success_definition, config
        )
        findings.extend(completion_findings)
        if not complete:
            analysis_status = EVIDENCE_INCOMPLETE

    # For diagnostic level, check for common failure patterns
    if trigger_level == GapLevel.DIAGNOSTIC:
        diagnostic_findings, complete = _check_failure_patterns(repository_root, config)
        findings.extend(diagnostic_findings)
        if not complete:
            analysis_status = EVIDENCE_INCOMPLETE

    return findings, analysis_status


def _check_changed_paths(
    repository_root: Path,
    changed_paths: list[str],
    config: Config,
) -> list[GapFinding]:
    """Check changed paths for gaps.
    
    Args:
        repository_root: Repository root directory
        changed_paths: List of changed paths
        config: Configuration to use
        
    Returns:
        List of gap findings
    """
    findings: list[GapFinding] = []
    
    for rel_path in changed_paths:
        full_path = repository_root / rel_path
        if not full_path.exists():
            findings.append(GapFinding(
                gap_id=generate_gap_id(),
                category=GapCategory.IMPLEMENTATION,
                severity=GapSeverity.HIGH,
                expected_claim=f"File {rel_path} should exist",
                observed_state="File is missing",
                evidence_locations=[EvidenceLocation(path=rel_path)],
                affected_paths=[rel_path],
                required_correction=f"Create or restore {rel_path}",
                required_validation=f"Verify {rel_path} exists and is correct",
                confidence=1.0,
            ))
    
    return findings


def _check_success_definition(
    repository_root: Path,
    success_definition: str | None,
    config: Config,
) -> tuple[list[GapFinding], bool]:
    """Check repository state against success definition.

    Placeholder: real success-definition evidence analysis is not
    implemented, so this reports evidence-incomplete (findings, False)
    and must never be treated as proof of absence of gaps.
    """
    return [], False


def _check_failure_patterns(
    repository_root: Path,
    config: Config,
) -> tuple[list[GapFinding], bool]:
    """Check for common failure patterns.

    Placeholder: real failure-pattern evidence analysis is not
    implemented, so this reports evidence-incomplete (findings, False)
    and must never be treated as proof of absence of gaps.
    """
    return [], False
