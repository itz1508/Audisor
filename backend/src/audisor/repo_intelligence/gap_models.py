"""Gap analysis data models.

Defines the structure of gap findings, records, and trigger digests.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GapSeverity(str, Enum):
    """Severity levels for gap findings."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class GapStatus(str, Enum):
    """Status of a gap finding."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"
    DEFERRED = "deferred"


class GapCategory(str, Enum):
    """Categories of gap findings."""
    REQUIREMENT = "requirement"
    DESIGN = "design"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    SECURITY = "security"
    PERFORMANCE = "performance"
    COMPATIBILITY = "compatibility"
    DOCUMENTATION = "documentation"


class TriggerType(str, Enum):
    """Types of automatic gap triggers."""
    TASK_CREATED = "task_created"
    TASK_EDITED = "task_edited"
    PLAN_CREATED = "plan_created"
    PLAN_EDITED = "plan_edited"
    FILE_APPLIED = "file_applied"
    CHANGESET_APPLIED = "changeset_applied"
    BUILD_SUCCESS = "build_success"
    IMPLEMENTATION_COMPLETE = "implementation_complete"
    VALIDATION_SUCCESS = "validation_success"
    EXECUTION_FAILURE = "execution_failure"


class GapLevel(str, Enum):
    """Gap analysis levels."""
    PREVIEW = "preview_gap"
    INCREMENTAL = "incremental_gap"
    COMPLETION = "completion_gap"
    DIAGNOSTIC = "diagnostic_gap"


@dataclass
class EvidenceLocation:
    """Location of evidence for a gap finding."""
    path: str
    line: int | None = None
    column: int | None = None
    content: str | None = None
    context: str | None = None

    def as_dict(self) -> dict:
        result = {"path": self.path}
        if self.line is not None:
            result["line"] = self.line
        if self.column is not None:
            result["column"] = self.column
        if self.content is not None:
            result["content"] = self.content
        if self.context is not None:
            result["context"] = self.context
        return result


@dataclass
class GapFinding:
    """A single gap finding."""
    gap_id: str
    category: GapCategory
    severity: GapSeverity
    expected_claim: str
    observed_state: str
    evidence_locations: list[EvidenceLocation]
    affected_paths: list[str]
    required_correction: str
    required_validation: str
    confidence: float  # 0.0 to 1.0
    status: GapStatus = GapStatus.OPEN

    def as_dict(self) -> dict:
        return {
            "gap_id": self.gap_id,
            "category": self.category.value,
            "severity": self.severity.value,
            "expected_claim": self.expected_claim,
            "observed_state": self.observed_state,
            "evidence_locations": [e.as_dict() for e in self.evidence_locations],
            "affected_paths": self.affected_paths,
            "required_correction": self.required_correction,
            "required_validation": self.required_validation,
            "confidence": self.confidence,
            "status": self.status.value,
        }


@dataclass
class TriggerDigest:
    """Digest for trigger idempotency."""
    task_digest: str | None = None
    plan_digest: str | None = None
    trigger_type: TriggerType = TriggerType.FILE_APPLIED
    repository_head: str | None = None
    dirty_state_digest: str | None = None
    changed_path_hashes: dict[str, str] = field(default_factory=dict)
    success_definition_digest: str | None = None

    def compute_digest(self) -> str:
        """Compute a deterministic digest for this trigger."""
        payload = {
            "task_digest": self.task_digest,
            "plan_digest": self.plan_digest,
            "trigger_type": self.trigger_type.value,
            "repository_head": self.repository_head,
            "dirty_state_digest": self.dirty_state_digest,
            "changed_path_hashes": dict(sorted(self.changed_path_hashes.items())),
            "success_definition_digest": self.success_definition_digest,
        }
        json_str = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(json_str.encode("utf-8")).hexdigest()[:16]


@dataclass
class GapRecord:
    """A persisted gap analysis record."""
    gap_run_id: str
    task_id: str | None
    plan_id: str | None
    operation_id: str | None
    trigger_type: TriggerType
    trigger_digest: str
    trigger_level: GapLevel
    repository_state: dict[str, Any]
    changed_paths: list[str]
    path_hashes: dict[str, str]
    findings: list[GapFinding]
    no_material_gap: bool
    previous_run_id: str | None
    final_result: str
    created_at: float

    def as_dict(self) -> dict:
        return {
            "gap_run_id": self.gap_run_id,
            "task_id": self.task_id,
            "plan_id": self.plan_id,
            "operation_id": self.operation_id,
            "trigger_type": self.trigger_type.value,
            "trigger_digest": self.trigger_digest,
            "trigger_level": self.trigger_level.value,
            "repository_state": self.repository_state,
            "changed_paths": self.changed_paths,
            "path_hashes": self.path_hashes,
            "findings": [f.as_dict() for f in self.findings],
            "no_material_gap": self.no_material_gap,
            "previous_run_id": self.previous_run_id,
            "final_result": self.final_result,
            "created_at": self.created_at,
        }


def findings_from_dicts(findings: list[dict] | None) -> list[GapFinding]:
    """Build GapFinding objects from serialized finding dictionaries."""
    finding_objects: list[GapFinding] = []
    for f in (findings or []):
        evidence_locs = [
            EvidenceLocation(
                path=e.get("path", ""),
                line=e.get("line"),
                column=e.get("column"),
                content=e.get("content"),
                context=e.get("context"),
            )
            for e in f.get("evidence_locations", [])
        ]
        finding_objects.append(GapFinding(
            gap_id=f["gap_id"],
            category=GapCategory(f["category"]),
            severity=GapSeverity(f["severity"]),
            expected_claim=f["expected_claim"],
            observed_state=f["observed_state"],
            evidence_locations=evidence_locs,
            affected_paths=f["affected_paths"],
            required_correction=f["required_correction"],
            required_validation=f["required_validation"],
            confidence=f["confidence"],
            status=GapStatus(f.get("status", "open")),
        ))
    return finding_objects
