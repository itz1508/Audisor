"""Repository intelligence toolkit for persistent local repository analysis."""

from .config import Config, DEFAULT_CONFIG
from .contracts import (
    SCHEMA_VERSION,
    ErrorInfo,
    EvidenceMetadata,
    RepositoryIntelligenceError,
    PathSecurityError,
    CommandExecutionError,
    PatchError,
    ToolResult,
    TruncationInfo,
    blocked,
    error,
    partial,
    success,
)
from .exclusions import (
    HARD_EXCLUSIONS,
    BINARY_EXTENSIONS,
    is_binary_file,
    is_excluded_path,
    should_index_file,
)
from .language import detect_language, is_text_file, validate_utf8, safe_decode_utf8, read_text_file
from .path_security import (
    validate_repository_root,
    validate_relative_path,
    validate_path_containment,
    to_repository_relative,
)
from .traversal import (
    FileInfo,
    traverse_repository,
    iter_python_files,
    count_files,
    build_repository_tree,
)

__all__ = [
    # Config
    "Config",
    "DEFAULT_CONFIG",
    # Contracts
    "SCHEMA_VERSION",
    "ErrorInfo",
    "EvidenceMetadata",
    "RepositoryIntelligenceError",
    "PathSecurityError",
    "CommandExecutionError",
    "PatchError",
    "ToolResult",
    "TruncationInfo",
    "blocked",
    "error",
    "partial",
    "success",
    # Exclusions
    "HARD_EXCLUSIONS",
    "BINARY_EXTENSIONS",
    "is_binary_file",
    "is_excluded_path",
    "should_index_file",
    # Language
    "detect_language",
    "is_text_file",
    "validate_utf8",
    "safe_decode_utf8",
    "read_text_file",
    # Path security
    "validate_repository_root",
    "validate_relative_path",
    "validate_path_containment",
    "to_repository_relative",
    # Traversal
    "FileInfo",
    "traverse_repository",
    "iter_python_files",
    "count_files",
    "build_repository_tree",
]
