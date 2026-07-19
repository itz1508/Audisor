from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping
import base64
import io

from PIL import Image, UnidentifiedImageError

from .scanner import evidence_paths, image_paths


_SECRET_VALUE = re.compile(r"(?i)(?P<prefix>(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"])[^'\"]+(['\"])")
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_IMAGE_PIXELS = 16_000_000
_MAX_IMAGE_PREVIEW_BYTES = 256 * 1024
_MAX_IMAGE_PREVIEWS = 64


class ArtifactError(ValueError):
    pass


def canonical_hash(value: Mapping[str, Any], hash_field: str) -> str:
    payload = dict(value)
    payload.pop(hash_field, None)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def redact_text(value: str) -> str:
    return _SECRET_VALUE.sub(lambda match: f"{match.group('prefix')}[REDACTED]{match.group(2)}", value)


def _image_preview(raw: bytes) -> dict[str, Any]:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if getattr(image, "is_animated", False):
                return {"status": "uncertainty", "reason": "animated_image_not_supported"}
            if image.width * image.height > _MAX_IMAGE_PIXELS:
                return {"status": "uncertainty", "reason": "image_pixel_limit", "width": image.width, "height": image.height}
            normalized = image.convert("RGBA")
            for bound in (512, 256, 128):
                preview = normalized.copy()
                preview.thumbnail((bound, bound), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                preview.save(buffer, format="PNG", optimize=True)
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                if len(encoded) <= _MAX_IMAGE_PREVIEW_BYTES:
                    return {
                        "status": "valid",
                        "width": image.width,
                        "height": image.height,
                        "preview_width": preview.width,
                        "preview_height": preview.height,
                        "preview_png_base64": encoded,
                    }
            return {"status": "uncertainty", "reason": "image_preview_limit", "width": image.width, "height": image.height}
    except (UnidentifiedImageError, OSError, ValueError):
        return {"status": "uncertainty", "reason": "image_unreadable"}


def _snapshot_paths(root: Path) -> list[Path]:
    return sorted({*evidence_paths(root), *image_paths(root)})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_snapshot(root: Path) -> list[dict[str, Any]]:
    snapshot: list[dict[str, Any]] = []
    image_previews = 0
    for path in _snapshot_paths(root):
        relative = path.relative_to(root).as_posix()
        is_image = path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        if is_image:
            try:
                if path.stat().st_size > _MAX_IMAGE_BYTES:
                    snapshot.append({"path": relative, "sha256": _sha256_file(path), "display_content": None, "image": {"status": "uncertainty", "reason": "image_byte_limit"}})
                    continue
            except OSError:
                snapshot.append({"path": relative, "sha256": None, "display_content": None})
                continue
        try:
            raw = path.read_bytes()
        except OSError:
            snapshot.append({"path": relative, "sha256": None, "display_content": None})
            continue
        item: dict[str, Any] = {"path": relative, "sha256": hashlib.sha256(raw).hexdigest(), "display_content": None}
        if path.suffix.lower() in {".py", ".json", ".toml", ".yaml", ".yml"}:
            try:
                item["display_content"] = redact_text(raw.decode("utf-8"))
            except UnicodeDecodeError:
                item["sha256"] = None
        elif image_previews >= _MAX_IMAGE_PREVIEWS:
            item["image"] = {"status": "uncertainty", "reason": "image_preview_count_limit"}
        else:
            item["image"] = _image_preview(raw)
            if item["image"].get("status") == "valid":
                image_previews += 1
        snapshot.append(item)
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
