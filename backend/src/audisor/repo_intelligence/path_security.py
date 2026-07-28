"""Path security utilities for repository containment."""

from __future__ import annotations

from pathlib import Path

from .contracts import PathSecurityError


def validate_repository_root(repository_root: Path) -> Path:
    """Validate and resolve repository root path.

    Args:
        repository_root: Path to validate

    Returns:
        Resolved absolute path

    Raises:
        PathSecurityError: If path is invalid or not a directory
    """
    try:
        resolved = repository_root.expanduser().resolve()
    except (OSError, ValueError) as exc:
        raise PathSecurityError(f"Invalid repository root path: {exc}")

    if not resolved.is_dir():
        raise PathSecurityError(f"Repository root is not a directory: {resolved}")

    return resolved


def validate_relative_path(repository_root: Path, relative_path: str) -> Path:
    """Validate a relative path is contained within repository root.

    Args:
        repository_root: The repository root directory
        relative_path: Relative path to validate

    Returns:
        Resolved absolute path

    Raises:
        PathSecurityError: If path escapes repository root
    """
    # Reject absolute paths
    if Path(relative_path).is_absolute():
        raise PathSecurityError(f"Absolute paths not allowed: {relative_path}")

    # Reject path traversal attempts
    if ".." in Path(relative_path).parts:
        raise PathSecurityError(f"Path traversal not allowed: {relative_path}")

    # Resolve the path
    resolved_root = repository_root.expanduser().resolve()
    candidate = (resolved_root / relative_path).resolve()

    # Verify containment
    try:
        candidate.relative_to(resolved_root)
    except ValueError:
        raise PathSecurityError(f"Path escapes repository root: {relative_path}")

    return candidate


def validate_path_containment(repository_root: Path, target_path: Path) -> Path:
    """Validate that a target path is contained within repository root.

    Args:
        repository_root: The repository root directory
        target_path: Target path to validate

    Returns:
        Resolved absolute path

    Raises:
        PathSecurityError: If path escapes repository root
    """
    resolved_root = repository_root.expanduser().resolve()
    resolved_target = target_path.expanduser().resolve()

    try:
        resolved_target.relative_to(resolved_root)
    except ValueError:
        raise PathSecurityError(f"Path escapes repository root: {target_path}")

    return resolved_target


def to_repository_relative(path: Path, repository_root: Path) -> str:
    """Convert a path to repository-relative POSIX path.

    Args:
        path: Path to convert
        repository_root: Repository root

    Returns:
        POSIX-style relative path string
    """
    resolved_path = path.resolve()
    resolved_root = repository_root.resolve()
    relative = resolved_path.relative_to(resolved_root)
    return relative.as_posix()
