from __future__ import annotations

from importlib import resources
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator

from .artifacts import ArtifactError, redact_text, verify_artifact


_SCHEMA_NAME = "llm-statement.schema.json"


def _schema_path() -> Path:
    packaged = resources.files("audisor").joinpath("schemas", "v1", _SCHEMA_NAME)
    return Path(str(packaged))


def _schema() -> dict[str, Any]:
    try:
        value = json.loads(_schema_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError("llm_statement_schema_unavailable") from exc
    if not isinstance(value, dict):
        raise ArtifactError("llm_statement_schema_invalid")
    return value


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _redact(item) for key, item in value.items()}
    return value


def normalize_inspection(inspection: Mapping[str, Any], llm_statement: Mapping[str, Any]) -> dict[str, Any]:
    """Return semantic repair context without copying Inspection snapshot evidence."""
    verify_artifact(inspection, "audisor.inspection", "manifest_sha256")
    errors = sorted(Draft202012Validator(_schema()).iter_errors(llm_statement), key=lambda error: list(error.path))
    if errors:
        raise ArtifactError(f"invalid_llm_statement:{errors[0].message}")

    inspection_ref = llm_statement.get("inspection_ref")
    if not isinstance(inspection_ref, Mapping):
        raise ArtifactError("llm_statement_inspection_ref_invalid")
    if inspection_ref.get("inspection_id") != inspection.get("inspection_id"):
        raise ArtifactError("llm_statement_inspection_id_mismatch")
    if inspection_ref.get("manifest_sha256") != inspection.get("manifest_sha256"):
        raise ArtifactError("llm_statement_inspection_hash_mismatch")

    report = inspection.get("scan_report")
    finding_ids = llm_statement.get("finding_ids")
    if not isinstance(report, Mapping) or not isinstance(finding_ids, list):
        raise ArtifactError("llm_statement_finding_refs_invalid")
    known_ids = {
        item.get("id")
        for item in report.get("findings", [])
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    if not set(finding_ids).issubset(known_ids):
        raise ArtifactError("llm_statement_unknown_finding_id")

    return {
        "artifact_type": "audisor.normalization_package",
        "schema_version": "1.0.0",
        "inspection_ref": {
            "inspection_id": inspection["inspection_id"],
            "manifest_sha256": inspection["manifest_sha256"],
        },
        "dossier": inspection["dossier"],
        "handoff": inspection["handoff"],
        "llm_statement": _redact(llm_statement),
    }
