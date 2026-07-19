from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import ArtifactError, canonical_hash, redact_text, safe_snapshot
from .contracts import InspectionRequest
from .scanner import scan_report


def inspect_repository(request: InspectionRequest) -> dict[str, Any]:
    root = Path(request.repository_root).expanduser().resolve()
    if not root.is_dir():
        raise ArtifactError("repository_not_found")
    report = scan_report(root, baseline=request.baseline).as_dict()
    snapshot = safe_snapshot(root)
    findings = report["findings"]
    artifact: dict[str, Any] = {
        "artifact_type": "audisor.inspection",
        "schema_version": "1.0.0",
        "inspection_id": request.inspection_id,
        "repository_root": str(root),
        "original_issue": redact_text(request.issue),
        "scan_report": report,
        "source_snapshot": snapshot,
        "dossier": {
            "raw_issue": redact_text(request.issue),
            "finding_ids": [item["id"] for item in findings],
            "scan_summary": report["summary"],
            "evidence_files": [item["path"] for item in snapshot],
        },
        "handoff": {
            "scope_files": sorted({item["file"] for item in findings}),
            "validation_hints": sorted({item["type"] for item in findings}),
            "next_action": "Codex performs Gap Evaluation, then validates the immutable Inspection Artifact before any repair.",
        },
    }
    artifact["manifest_sha256"] = canonical_hash(artifact, "manifest_sha256")
    return artifact
