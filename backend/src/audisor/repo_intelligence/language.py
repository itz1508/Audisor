"""Language detection and UTF-8 validation utilities."""

from __future__ import annotations

from pathlib import Path


# File extension to language mapping
EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".pyi": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".xml": "xml",
    ".svg": "xml",
    ".sql": "sql",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".pl": "perl",
    ".pm": "perl",
    ".dockerfile": "dockerfile",
    ".makefile": "makefile",
    ".cmake": "cmake",
}

# Special filenames
FILENAME_TO_LANGUAGE = {
    "Dockerfile": "dockerfile",
    "Makefile": "makefile",
    "CMakeLists.txt": "cmake",
    "Justfile": "just",
    "Rakefile": "ruby",
    "Gemfile": "ruby",
    "Vagrantfile": "ruby",
    "BUILD": "bazel",
    "WORKSPACE": "bazel",
}


def detect_language(path: Path) -> str:
    """Detect the programming language of a file.

    Args:
        path: Path to the file

    Returns:
        Language identifier string, or "unknown" if not detected
    """
    # Check special filenames first
    if path.name in FILENAME_TO_LANGUAGE:
        return FILENAME_TO_LANGUAGE[path.name]

    # Check extension
    suffix = path.suffix.lower()
    if suffix in EXTENSION_TO_LANGUAGE:
        return EXTENSION_TO_LANGUAGE[suffix]

    return "unknown"


def is_text_file(path: Path) -> bool:
    """Check if a file is likely a text file.

    Args:
        path: Path to check

    Returns:
        True if the file is likely text
    """
    # Check if we recognize the language
    language = detect_language(path)
    if language != "unknown":
        return True

    # Check for common text extensions
    text_extensions = {
        ".cfg", ".ini", ".conf", ".config",
        ".log", ".csv", ".tsv",
        ".env", ".properties",
        ".gitignore", ".gitattributes", ".editorconfig",
        ".dockerignore",
    }
    if path.suffix.lower() in text_extensions:
        return True

    return False


def validate_utf8(content: bytes) -> tuple[bool, str | None]:
    """Validate UTF-8 encoding of content.

    Args:
        content: Bytes to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        content.decode("utf-8")
        return True, None
    except UnicodeDecodeError as exc:
        return False, f"UTF-8 decode error at position {exc.start}: {exc.reason}"


def safe_decode_utf8(content: bytes) -> tuple[str | None, str | None]:
    """Safely decode UTF-8 content.

    Args:
        content: Bytes to decode

    Returns:
        Tuple of (decoded_string, error_message)
        If decoding fails, decoded_string is None
    """
    try:
        return content.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"UTF-8 decode error at position {exc.start}: {exc.reason}"


def read_text_file(path: Path, max_bytes: int | None = None) -> tuple[str | None, str | None]:
    """Read a text file with UTF-8 validation.

    Args:
        path: Path to read
        max_bytes: Maximum bytes to read (None for unlimited)

    Returns:
        Tuple of (content, error_message)
        If reading fails, content is None
    """
    try:
        if max_bytes is not None:
            with open(path, "rb") as f:
                content = f.read(max_bytes)
        else:
            with open(path, "rb") as f:
                content = f.read()

        return safe_decode_utf8(content)
    except (OSError, IOError) as exc:
        return None, f"Read error: {exc}"
