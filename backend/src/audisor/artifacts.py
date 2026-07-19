from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .scanner import evidence_paths


_SECRET_VALUE = re.compile(r"(?i)(?P<prefix>(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"])[^'\"]+(['\"])")


class ArtifactError(ValueError):
    pass


def canonical_hash(value: Mapping[str, Any], hash_field: str) -> str:
    payload = dict(value)
    payload.pop(hash_field, None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redact_text(value: str) -> str:
    return _SECRET_VALUE.sub(lambda match: f"{match.group('prefix')}[REDACTED]{match.group(2)}", value)


def safe_snapshot(root: Path) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    for path in evidence_paths(root):
        relative = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError):
            snapshot.append({"path": relative, "sha256": None, "display_content": None})
            continue
        display_content = redact_text(text) if path.suffix.lower() in {".py", ".json", ".toml", ".yaml", ".yml"} else None
        snapshot.append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "display_content": display_content})
    return snapshot


def snapshot_index(snapshot: list[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(item["path"]): item for item in snapshot if isinstance(item, Mapping) and isinstance(item.get("path"), str)}


def verify_artifact(value: Mapping[str, Any], artifact_type: str, hash_field: str) -> None:
    if value.get("artifact_type") != artifact_type or value.get("schema_version") != "1.0.0":
        raise ArtifactError(f"invalid {artifact_type} artifact")
    actual = value.get(hash_field)
    if not isinstance(actual, str) or actual != canonical_hash(value, hash_field):
        raise ArtifactError(f"invalid {hash_field}")


def verify_current_snapshot(root: Path, original: list[Mapping[str, Any]]) -> None:
    original_index = snapshot_index(original)
    current_index = snapshot_index(safe_snapshot(root))
    if set(original_index) != set(current_index):
        raise ArtifactError("evidence_file_set_changed")
    for path, item in original_index.items():
        if item.get("sha256") != current_index[path].get("sha256"):
            raise ArtifactError(f"evidence_changed:{path}")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"invalid_json:{path}") from exc
    if not isinstance(value, dict):
        raise ArtifactError(f"object_required:{path}")
    return value
