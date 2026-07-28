"""Safe mutation - prepare and apply patches with hash verification."""

from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError
from .path_security import validate_relative_path, validate_repository_root


class PatchError(RepositoryIntelligenceError):
    """Raised when patch operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


# Global registry for prepared patches
_prepared_patches: dict[str, PatchPreview] = {}


@dataclass
class PatchPreview:
    """Preview of a patch before application."""

    path: str
    original_sha256: str
    new_sha256: str
    original_content: str
    new_content: str
    start_line: int | None
    end_line: int | None
    diff: str
    patch_id: str = field(default_factory=lambda: f"patch-{uuid.uuid4().hex[:12]}")

    def as_dict(self) -> dict:
        result = {
            "path": self.path,
            "original_sha256": self.original_sha256,
            "new_sha256": self.new_sha256,
            "diff": self.diff,
            "patch_id": self.patch_id,
        }
        if self.start_line is not None:
            result["start_line"] = self.start_line
        if self.end_line is not None:
            result["end_line"] = self.end_line
        return result


@dataclass
class PatchResult:
    """Result of applying a patch."""

    path: str
    sha256: str
    success: bool
    message: str

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "success": self.success,
            "message": self.message,
        }


def compute_sha256(content: str | bytes) -> str:
    """Compute SHA-256 hash of content.

    Args:
        content: Content to hash (string or bytes)

    Returns:
        Hex digest string
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _generate_diff(original: str, new: str, path: str) -> str:
    """Generate a unified diff between two strings.

    Args:
        original: Original content
        new: New content
        path: File path for diff header

    Returns:
        Unified diff string
    """
    import difflib

    original_lines = original.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    )
    return "".join(diff)


def _check_symlink_safety(repository_root: Path, relative_path: str) -> None:
    """Check that a file path is not a symlink or does not escape the repository.

    Args:
        repository_root: Repository root directory
        relative_path: Relative path to check

    Raises:
        PatchError: If the path is a symlink or escapes the repository
    """
    resolved_root = repository_root.resolve()

    # Build the unresolved path
    unresolved_path = resolved_root / relative_path

    # Check if the file itself is a symlink (check unresolved path)
    if unresolved_path.is_symlink():
        raise PatchError(
            "symlink_rejected",
            f"Symlinks are not permitted for mutation: {relative_path}",
        )

    # Check if any parent component is a symlink
    current = unresolved_path.parent
    while current != resolved_root and current.parent != current:
        if current.is_symlink():
            raise PatchError(
                "symlink_rejected",
                f"Path component is a symlink: {current}",
            )
        current = current.parent

    # Verify the resolved path is still under the repository root
    resolved_path = unresolved_path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise PatchError(
            "path_escape",
            f"Resolved path escapes repository root: {resolved_path}",
        )


def _load_target(repository_root: Path, relative_path: str) -> tuple[Path, str]:
    """Validate the target path and read its current UTF-8 content."""
    # Validate path
    try:
        file_path = validate_relative_path(repository_root, relative_path)
    except Exception as exc:
        raise PatchError("path_security_violation", str(exc))

    if not file_path.is_file():
        raise PatchError("file_not_found", f"File not found: {relative_path}")

    # Check symlink safety (before validate_relative_path resolves symlinks)
    _check_symlink_safety(repository_root, relative_path)

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise PatchError("encoding_error", f"File is not valid UTF-8: {relative_path}")
    except (OSError, IOError) as exc:
        raise PatchError("read_error", f"Failed to read file: {exc}")

    return file_path, content


def _replace_line_range(
    original: str,
    new_content: str,
    start_line: int,
    end_line: int,
) -> tuple[str, int, int]:
    """Replace an inclusive 1-based line range; returns (content, start, end) after clamping."""
    lines = original.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Validate line range
    if start_line < 1:
        start_line = 1
    if end_line > len(lines):
        end_line = len(lines)
    if start_line > end_line:
        raise PatchError("invalid_range", f"Invalid line range: {start_line}-{end_line}")

    final_content = "".join(lines[:start_line - 1] + new_lines + lines[end_line:])
    return final_content, start_line, end_line


def prepare_patch(
    repository_root: Path,
    relative_path: str,
    new_content: str,
    expected_sha256: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
    config: Config = DEFAULT_CONFIG,
) -> PatchPreview:
    """Prepare a patch without applying it.

    Validates the path and computes the diff, but does not modify the file.

    Returns:
        PatchPreview with diff information

    Raises:
        PatchError: If validation fails
    """
    repository_root = validate_repository_root(repository_root)
    file_path, original_content = _load_target(repository_root, relative_path)
    original_sha256 = compute_sha256(original_content)

    # Verify expected hash if provided
    if expected_sha256 is not None and expected_sha256 != original_sha256:
        raise PatchError(
            "hash_mismatch",
            f"Current file hash {original_sha256} does not match expected {expected_sha256}",
        )

    # Compute new content
    if start_line is not None and end_line is not None:
        final_content, start_line, end_line = _replace_line_range(
            original_content, new_content, start_line, end_line,
        )
    else:
        # Full replacement
        final_content = new_content

    preview = PatchPreview(
        path=relative_path,
        original_sha256=original_sha256,
        new_sha256=compute_sha256(final_content),
        original_content=original_content,
        new_content=final_content,
        start_line=start_line,
        end_line=end_line,
        diff=_generate_diff(original_content, final_content, relative_path),
    )

    # Register the prepared patch
    _prepared_patches[preview.patch_id] = preview

    return preview


def _verify_prepared(patch_id: str, relative_path: str, new_content: str) -> None:
    """Verify an apply request matches its prepared patch."""
    if patch_id not in _prepared_patches:
        raise PatchError("unknown_patch_id", f"Patch ID not found: {patch_id}")
    prepared = _prepared_patches[patch_id]
    # Verify the prepared patch matches the apply request
    if prepared.path != relative_path:
        raise PatchError(
            "patch_path_mismatch",
            f"Patch ID {patch_id} is for path {prepared.path}, not {relative_path}",
        )
    if prepared.new_sha256 != compute_sha256(new_content):
        raise PatchError(
            "patch_content_mismatch",
            f"Patch ID {patch_id} content does not match provided new_content",
        )


def _write_atomic(file_path: Path, new_content: str) -> None:
    """Write content atomically using temp file + rename."""
    try:
        # Create temp file in same directory for atomic rename
        dir_path = file_path.parent
        fd, temp_path = tempfile.mkstemp(dir=dir_path, prefix=".patch_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Atomic rename (on same filesystem)
            os.replace(temp_path, file_path)
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    except (OSError, IOError) as exc:
        raise PatchError("write_error", f"Failed to write file: {exc}")


def apply_patch(
    repository_root: Path,
    relative_path: str,
    new_content: str,
    expected_sha256: str,
    patch_id: str | None = None,
    config: Config = DEFAULT_CONFIG,
) -> PatchResult:
    """Apply a patch to a file.

    This re-verifies the current hash before writing.

    Returns:
        PatchResult with application status

    Raises:
        PatchError: If validation or application fails
    """
    repository_root = validate_repository_root(repository_root)

    # Validate patch_id if provided
    if patch_id is not None:
        _verify_prepared(patch_id, relative_path, new_content)

    file_path, current_content = _load_target(repository_root, relative_path)

    # Re-verify current hash
    current_sha256 = compute_sha256(current_content)
    if current_sha256 != expected_sha256:
        raise PatchError(
            "stale_patch",
            f"File has been modified. Current hash: {current_sha256}, expected: {expected_sha256}",
        )

    _write_atomic(file_path, new_content)

    # Clean up prepared patch registry
    if patch_id is not None and patch_id in _prepared_patches:
        del _prepared_patches[patch_id]

    return PatchResult(
        path=relative_path,
        sha256=compute_sha256(new_content),
        success=True,
        message="Patch applied successfully",
    )

