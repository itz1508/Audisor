"""Repository traversal utilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .config import Config, DEFAULT_CONFIG
from .exclusions import is_excluded_path, is_binary_file, should_index_file
from .language import detect_language


@dataclass(frozen=True)
class FileInfo:
    """Information about a discovered file."""

    path: Path
    relative_path: str
    language: str
    size: int
    is_binary: bool
    encoding_error: str | None = None


def traverse_repository(
    repository_root: Path,
    config: Config = DEFAULT_CONFIG,
    include_binary: bool = False,
) -> Iterator[FileInfo]:
    """Traverse repository and yield file information.

    Args:
        repository_root: Root directory of repository
        config: Configuration to use
        include_binary: Whether to include binary files

    Yields:
        FileInfo for each discovered file
    """
    resolved_root = repository_root.expanduser().resolve()

    for path in sorted(resolved_root.rglob("*")):
        if not path.is_file():
            continue

        # Get relative path
        try:
            relative = path.relative_to(resolved_root)
        except ValueError:
            continue

        # Check exclusions
        if not should_index_file(relative):
            continue

        # Check file size
        try:
            size = path.stat().st_size
        except OSError:
            continue

        if size > config.max_file_size_bytes:
            continue

        # Detect language
        language = detect_language(relative)

        # Check if binary
        binary = is_binary_file(path)
        if binary and not include_binary:
            continue

        yield FileInfo(
            path=path,
            relative_path=relative.as_posix(),
            language=language,
            size=size,
            is_binary=binary,
        )


def iter_python_files(
    repository_root: Path,
    config: Config = DEFAULT_CONFIG,
) -> Iterator[FileInfo]:
    """Iterate over Python files in repository.

    Args:
        repository_root: Root directory of repository
        config: Configuration to use

    Yields:
        FileInfo for each Python file
    """
    for info in traverse_repository(repository_root, config, include_binary=False):
        if info.language == "python":
            yield info


def count_files(
    repository_root: Path,
    config: Config = DEFAULT_CONFIG,
) -> dict[str, int]:
    """Count files by language.

    Args:
        repository_root: Root directory of repository
        config: Configuration to use

    Returns:
        Dictionary mapping language to file count
    """
    counts: dict[str, int] = {}
    for info in traverse_repository(repository_root, config):
        counts[info.language] = counts.get(info.language, 0) + 1
    return counts


def build_repository_tree(
    repository_root: Path,
    max_depth: int = 10,
    max_entries: int = 1000,
) -> tuple[list[dict], bool]:
    """Build a bounded repository tree structure.

    Args:
        repository_root: Root directory of repository
        max_depth: Maximum directory depth
        max_entries: Maximum number of entries

    Returns:
        Tuple of (tree_entries, truncated)
    """
    resolved_root = repository_root.expanduser().resolve()
    entries: list[dict] = []
    truncated = _walk_tree(resolved_root, resolved_root, 0, max_depth, max_entries, entries)
    return entries, truncated


def _walk_tree(
    current: Path,
    resolved_root: Path,
    depth: int,
    max_depth: int,
    max_entries: int,
    entries: list[dict],
) -> bool:
    """Recursively collect tree entries; returns True when truncated."""
    if depth > max_depth or len(entries) >= max_entries:
        return len(entries) >= max_entries

    try:
        items = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return False

    truncated = False
    for item in items:
        if len(entries) >= max_entries:
            return True

        relative = item.relative_to(resolved_root)
        if is_excluded_path(relative):
            continue

        entry = {
            "path": relative.as_posix(),
            "name": item.name,
            "type": "directory" if item.is_dir() else "file",
        }

        if item.is_file():
            entry["language"] = detect_language(relative)
            try:
                entry["size"] = item.stat().st_size
            except OSError:
                entry["size"] = 0

        entries.append(entry)

        if item.is_dir():
            truncated = _walk_tree(item, resolved_root, depth + 1, max_depth, max_entries, entries) or truncated
    return truncated
