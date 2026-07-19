from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import ArtifactError, redact_text, verify_artifact, verify_current_snapshot
from .gap_contract import validate_gap_evaluation


def _value_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _safe_evaluation(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for item in evaluation["findings"]:
        safe: dict[str, Any] = {"id": item["id"], "status": item["status"]}
        if item["status"] == "valid":
            safe.update({
                "closure": redact_text(item["closure"]),
                "scope": {"include": list(item["scope"]["include"]), "exclude": list(item["scope"]["exclude"])},
                "success_criteria": [redact_text(value) for value in item["success_criteria"]],
                "validator": redact_text(item["validator"]),
            })
        findings.append(safe)
    return {"findings": findings}


def validate_inspection(inspection: Mapping[str, Any], evaluation: Mapping[str, Any]) -> dict[str, Any]:
    verify_artifact(inspection, "audisor.inspection", "manifest_sha256")
    root_value = inspection.get("repository_root")
    snapshot = inspection.get("source_snapshot")
    report = inspection.get("scan_report")
    if not isinstance(root_value, str) or not isinstance(snapshot, list) or not isinstance(report, Mapping):
        raise ArtifactError("inspection_fields_invalid")
    root = Path(root_value)
    if not root.is_dir():
        raise ArtifactError("repository_not_found")
    verify_current_snapshot(root, snapshot)
    validate_gap_evaluation(report, evaluation)
    artifact: dict[str, Any] = {
        "artifact_type": "audisor.validation",
        "schema_version": "1.0.0",
        "inspection_manifest_sha256": inspection["manifest_sha256"],
        "evaluation_sha256": _value_hash(evaluation),
        "evaluation": _safe_evaluation(evaluation),
        "repair_criteria": "Codex may use only valid findings; runtime validators remain not_run until separately executed.",
    }
    artifact["validation_sha256"] = _value_hash({key: value for key, value in artifact.items() if key != "validation_sha256"})
    return artifact


def verify_validation(inspection: Mapping[str, Any], validation: Mapping[str, Any]) -> None:
    verify_artifact(validation, "audisor.validation", "validation_sha256")
    if validation.get("inspection_manifest_sha256") != inspection.get("manifest_sha256"):
        raise ArtifactError("inspection_validation_mismatch")
