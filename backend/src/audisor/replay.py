from __future__ import annotations

import base64
import difflib
import io
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageChops

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


def _image_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in ("width", "height", "preview_width", "preview_height") if key in value}


def _decode_preview(value: Mapping[str, Any]) -> Image.Image | None:
    preview = value.get("preview_png_base64")
    if not isinstance(preview, str):
        return None
    try:
        return Image.open(io.BytesIO(base64.b64decode(preview))).convert("RGBA")
    except (ValueError, OSError):
        return None


def _bounded_png(image: Image.Image) -> str | None:
    for bound in (512, 256, 128):
        candidate = image.copy()
        candidate.thumbnail((bound * 3, bound), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        candidate.save(buffer, format="PNG", optimize=True)
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        if len(encoded) <= 256 * 1024:
            return encoded
    return None


def _image_diff(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> dict[str, Any]:
    if before is None or after is None:
        return {"status": "uncertainty", "reason": "image_added_or_deleted"}
    before_image = before.get("image")
    after_image = after.get("image")
    if not isinstance(before_image, Mapping) or not isinstance(after_image, Mapping):
        return {"status": "uncertainty", "reason": "image_evidence_missing"}
    if before_image.get("status") != "valid" or after_image.get("status") != "valid":
        return {
            "status": "uncertainty",
            "reason": "image_preview_unavailable",
            "before": _image_metadata(before_image),
            "after": _image_metadata(after_image),
        }
    before_preview = _decode_preview(before_image)
    after_preview = _decode_preview(after_image)
    if before_preview is None or after_preview is None:
        return {"status": "uncertainty", "reason": "image_preview_invalid"}
    width = max(before_preview.width, after_preview.width)
    height = max(before_preview.height, after_preview.height)
    before_canvas = Image.new("RGBA", (width, height))
    after_canvas = Image.new("RGBA", (width, height))
    before_canvas.paste(before_preview, (0, 0))
    after_canvas.paste(after_preview, (0, 0))
    difference = ImageChops.difference(before_canvas, after_canvas)
    changed_pixels = sum(1 for pixel in difference.getdata() if pixel != (0, 0, 0, 0))
    total_pixels = width * height
    mask = difference.convert("L").point(lambda value: 255 if value else 0)
    highlight = Image.new("RGBA", (width, height), (255, 0, 0, 0))
    highlight.putalpha(mask)
    visual = Image.new("RGBA", (width * 3, height))
    visual.paste(before_canvas, (0, 0))
    visual.paste(after_canvas, (width, 0))
    visual.paste(after_canvas, (width * 2, 0))
    visual.alpha_composite(highlight, (width * 2, 0))
    payload = _bounded_png(visual)
    if payload is None:
        return {"status": "uncertainty", "reason": "image_diff_payload_limit"}
    return {
        "status": "valid",
        "comparison_basis": "normalized_preview",
        "panels": ["before", "after", "difference"],
        "before": _image_metadata(before_image),
        "after": _image_metadata(after_image),
        "comparison_width": width,
        "comparison_height": height,
        "changed_pixel_count": changed_pixels,
        "total_pixel_count": total_pixels,
        "changed_pixel_ratio": changed_pixels / total_pixels if total_pixels else 0,
        "diff_png_base64": payload,
    }


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
    diff_view = []
    for path, kind in changes.items():
        if path not in valid_scopes:
            continue
        before_item = before.get(path)
        after_item = after.get(path)
        if (isinstance(before_item, Mapping) and "image" in before_item) or (isinstance(after_item, Mapping) and "image" in after_item):
            diff_view.append({"path": path, "status": kind, "image_diff": _image_diff(before_item, after_item)})
        else:
            diff_view.append({"path": path, "status": kind, "diff": _safe_diff(path, before_item, after_item)})
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
