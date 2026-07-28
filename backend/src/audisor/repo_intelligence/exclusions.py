"""Path exclusion policy for repository intelligence tools."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator


# Hard safety exclusions - never index these
HARD_EXCLUSIONS = frozenset({
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    "*.egg-info",
    ".audisor",  # Our own index directory
})

# Binary file extensions
BINARY_EXTENSIONS = frozenset({
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    # Audio/Video
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # Executables
    ".exe", ".dll", ".so", ".dylib", ".bin",
    # Documents
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Databases
    ".db", ".sqlite", ".sqlite3",
    # Compiled
    ".pyc", ".pyo", ".class", ".o", ".obj",
    # Other
    ".woff", ".woff2", ".ttf", ".eot",
})

# Credential file patterns
CREDENTIAL_PATTERNS = frozenset({
    ".env",
    ".env.local",
    ".env.*.local",
    "secrets.yml",
    "secrets.yaml",
    "credentials.json",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
})


def is_excluded_by_name(name: str) -> bool:
    """Check if a path component should be excluded by name."""
    if name in HARD_EXCLUSIONS:
        return True
    # Check glob patterns
    if name.endswith(".egg-info"):
        return True
    return False


def is_excluded_path(relative_path: Path) -> bool:
    """Check if a relative path should be excluded.

    Args:
        relative_path: Path relative to repository root

    Returns:
        True if the path should be excluded
    """
    # Check each path component
    for part in relative_path.parts:
        if is_excluded_by_name(part):
            return True
    return False


def is_binary_file(path: Path) -> bool:
    """Check if a file appears to be binary.

    Args:
        path: Path to check

    Returns:
        True if the file is likely binary
    """
    # Check extension
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True

    # Check content for null bytes (common binary indicator)
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, IOError):
        return False


def is_credential_file(relative_path: Path) -> bool:
    """Check if a path looks like a credentials file.

    Args:
        relative_path: Path relative to repository root

    Returns:
        True if the file appears to contain credentials
    """
    name = relative_path.name.lower()

    # Direct pattern matches
    if name in {p.lower() for p in CREDENTIAL_PATTERNS}:
        return True

    # Check for .env files with local suffix
    if name.startswith(".env") and ".local" in name:
        return True

    # Check for private keys
    if "private" in name and "key" in name:
        return True

    return False


def should_index_file(relative_path: Path) -> bool:
    """Determine if a file should be indexed.

    Args:
        relative_path: Path relative to repository root

    Returns:
        True if the file should be indexed
    """
    # Exclude by path
    if is_excluded_path(relative_path):
        return False

    # Exclude credentials
    if is_credential_file(relative_path):
        return False

    return True


def iter_gitignore_patterns(repository_root: Path) -> Iterator[str]:
    """Read patterns from .gitignore file.

    Args:
        repository_root: Repository root directory

    Yields:
        Pattern strings from .gitignore
    """
    gitignore_path = repository_root / ".gitignore"
    if not gitignore_path.is_file():
        return

    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                yield line
    except (OSError, IOError):
        return


def matches_gitignore_pattern(relative_path: Path, patterns: list[str]) -> bool:
    """Check if a path matches any gitignore pattern.

    This is a simplified implementation that handles common patterns.

    Args:
        relative_path: Path relative to repository root
        patterns: List of gitignore patterns

    Returns:
        True if the path matches any pattern
    """
    path_str = str(relative_path)

    for pattern in patterns:
        # Handle negation
        if pattern.startswith("!"):
            continue  # Simplified: ignore negation for now

        # Handle directory-only patterns
        dir_only = pattern.endswith("/")
        if dir_only:
            pattern = pattern[:-1]

        # Simple glob matching
        if "*" in pattern or "?" in pattern:
            # Convert glob to simple matching
            import fnmatch
            if fnmatch.fnmatch(path_str, pattern) or fnmatch.fnmatch(relative_path.name, pattern):
                if not dir_only or relative_path.is_dir():
                    return True
        else:
            # Exact match or prefix match
            if path_str == pattern or path_str.startswith(pattern + "/") or relative_path.name == pattern:
                if not dir_only or relative_path.is_dir():
                    return True

    return False
