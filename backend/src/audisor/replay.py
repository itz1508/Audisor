from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any, Mapping

from .artifacts import ArtifactError, canonical_hash, safe_snapshot, snapshot_index, verify_artifact
from .scanner import scan_report
from .validation import verify_validation


_IDENTITY_EVIDENCE = {
    "dependency_declaration_mismatch": ("module",),
    "missing_local_import": ("module",),
    "missing_schema_reference": ("reference",),
    "invalid_script_entrypoint": ("script", "target"),
    "missing_validation_registration": ("script", "target"),
}


def _change_kind(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> str | None:
    if before is None:
        return "added"
    if after is None:
        return "removed"
    if before.get("sha256") != after.get("sha256"):
        return "modified"
    return None


def _safe_diff(path: str, before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> str:
    before_lines = str(before.get("display_content") or "").splitlines(keepends=True) if before else []
    after_lines = str(after.get("display_content") or "").splitlines(keepends=True) if after else []
    return "".join(difflib.unified_diff(before_lines, after_lines, fromfile=f"original/{path}", tofile=f"current/{path}"))


def _finding_identity(item: Mapping[str, Any]) -> tuple[object, ...]:
    finding_type = item.get("type")
    file = item.get("file")
    evidence = item.get("evidence")
    keys = _IDENTITY_EVIDENCE.get(finding_type, ())
    if not keys or not isinstance(evidence, Mapping):
        return finding_type, file
    return finding_type, file, *(evidence.get(key) for key in keys)


def replay_inspection(inspection: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    verify_artifact(inspection, "audisor.inspection", "manifest_sha256")
    verify_validation(inspection, validation)
    root_value = inspection.get("repository_root")
    original_snapshot = inspection.get("source_snapshot")
    original_report = inspection.get("scan_report")
    evaluation = validation.get("evaluation")
    if not isinstance(root_value, str) or not isinstance(original_snapshot, list) or not isinstance(original_report, Mapping) or not isinstance(evaluation, Mapping):
        raise ArtifactError("replay_fields_invalid")
    root = Path(root_value)
    if not root.is_dir():
        raise ArtifactError("repository_not_found")
    current_snapshot = safe_snapshot(root)
    before = snapshot_index(original_snapshot)
    after = snapshot_index(current_snapshot)
    changes = {path: _change_kind(before.get(path), after.get(path)) for path in sorted(set(before) | set(after))}
    changes = {path: kind for path, kind in changes.items() if kind}
    valid_scopes = {path for item in evaluation.get("findings", []) if item.get("status") == "valid" for path in item.get("scope", {}).get("include", [])}
    diff_view = [{"path": path, "status": kind, "diff": _safe_diff(path, before.get(path), after.get(path))} for path, kind in changes.items() if path in valid_scopes]
    unrelated_changes = [{"path": path, "status": kind} for path, kind in changes.items() if path not in valid_scopes]
    requested_baseline = original_report.get("baseline", {}).get("requested") if isinstance(original_report.get("baseline"), Mapping) else None
    current_report = scan_report(root, baseline=requested_baseline)
    original_by_id = {item["id"]: item for item in original_report.get("findings", []) if isinstance(item, Mapping) and isinstance(item.get("id"), str)}
    current_candidates = {_finding_identity(item) for item in current_report.findings}
    findings: list[dict[str, Any]] = []
    for item in evaluation.get("findings", []):
        original = original_by_id.get(item.get("id"), {})
        status = item.get("status")
        result: dict[str, Any] = {"id": item.get("id"), "original_status": status}
        if status != "valid":
            result["replay_status"] = status
        elif original.get("type") == "repository_drift":
            result["replay_status"] = "uncertainty"
            result["reason"] = "Git drift requires a new baseline."
        elif _finding_identity(original) in current_candidates:
            result["replay_status"] = "unresolved"
        else:
            scope = set(item.get("scope", {}).get("include", []))
            deleted_scope = any(changes.get(path) == "removed" for path in scope)
            changed_scope = any(path in changes and changes[path] != "removed" for path in scope)
            result["replay_status"] = "uncertainty" if deleted_scope or not changed_scope else "resolved"
            if result["replay_status"] == "uncertainty":
                result["reason"] = "No non-deleted required scope change proves the closure."
        if status == "valid":
            result["validator_state"] = "not_run"
            result["validation_note"] = "Unverified_Execution_Claim: runtime validator was not executed by replay."
        findings.append(result)
    replay_states = {item["replay_status"] for item in findings if item["original_status"] == "valid"}
    overall = "unresolved" if "unresolved" in replay_states else "uncertainty" if "uncertainty" in replay_states else "resolved"
    artifact: dict[str, Any] = {
        "artifact_type": "audisor.replay_result",
        "schema_version": "1.0.0",
        "inspection_manifest_sha256": inspection["manifest_sha256"],
        "validation_sha256": validation["validation_sha256"],
        "original_issue": inspection["original_issue"],
        "overall_replay_status": overall,
        "findings": findings,
        "current_scan_summary": current_report.summary,
        "diff_view": diff_view,
        "unrelated_change_summary": unrelated_changes,
    }
    artifact["result_sha256"] = canonical_hash(artifact, "result_sha256")
    return artifact
