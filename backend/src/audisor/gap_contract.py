from __future__ import annotations

from typing import Any, Mapping

from .finding_registry import finding_definition
from .scanner import ScanReport


_STATUSES = {"valid", "not_valid", "uncertainty"}


class GapEvaluationError(ValueError):
    pass


def validate_gap_evaluation(scan_report: ScanReport | Mapping[str, Any], evaluation: Mapping[str, Any]) -> None:
    report = scan_report.as_dict() if isinstance(scan_report, ScanReport) else scan_report
    candidates = report.get("findings")
    findings = evaluation.get("findings")
    if not isinstance(candidates, list) or not isinstance(findings, list):
        raise GapEvaluationError("scan_report.findings and evaluation.findings must be lists")
    for candidate in candidates:
        if not isinstance(candidate, Mapping) or not isinstance(candidate.get("type"), str):
            raise GapEvaluationError("each ScanReport finding requires a registered type")
        try:
            finding_definition(candidate["type"])
        except ValueError as exc:
            raise GapEvaluationError("ScanReport contains an unknown finding type") from exc
    expected_ids = [item.get("id") for item in candidates if isinstance(item, Mapping)]
    returned_ids = [item.get("id") for item in findings if isinstance(item, Mapping)]
    if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) != set(expected_ids):
        raise GapEvaluationError("evaluation must classify every ScanReport finding exactly once")
    for finding in findings:
        if not isinstance(finding, Mapping) or finding.get("status") not in _STATUSES:
            raise GapEvaluationError("each evaluation finding requires valid, not_valid, or uncertainty status")
        if finding["status"] != "valid":
            continue
        scope = finding.get("scope")
        if not isinstance(finding.get("closure"), str) or not finding["closure"].strip():
            raise GapEvaluationError("valid findings require closure")
        if not isinstance(scope, Mapping) or not isinstance(scope.get("include"), list) or not isinstance(scope.get("exclude"), list):
            raise GapEvaluationError("valid findings require included and excluded scope")
        if not isinstance(finding.get("success_criteria"), list) or not finding["success_criteria"]:
            raise GapEvaluationError("valid findings require success criteria")
        if not isinstance(finding.get("validator"), str) or not finding["validator"].strip():
            raise GapEvaluationError("valid findings require a focused validator")
