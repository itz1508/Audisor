"""Configuration contract for repository intelligence tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Configuration for repository intelligence operations."""

    # File size limits
    max_file_size_bytes: int = 1_000_000  # 1MB
    max_search_result_bytes: int = 100_000  # 100KB per search result
    max_command_output_bytes: int = 500_000  # 500KB

    # Result limits
    max_search_results: int = 100
    max_symbol_results: int = 100
    max_git_diff_bytes: int = 1_000_000  # 1MB
    max_git_history_commits: int = 100
    max_tree_depth: int = 10
    max_tree_entries: int = 1000

    # Timeouts
    command_timeout_seconds: int = 300  # 5 minutes
    index_timeout_seconds: int = 600  # 10 minutes

    # Index location
    index_directory: str = ".audisor"
    index_database_name: str = "repo-intelligence.db"

    # FTS5 configuration
    fts_tokenizer: str = "unicode61"

    # Command execution
    use_uv_run_python: bool = True  # Use 'uv run python' on Windows

    def index_path(self, repository_root: Path) -> Path:
        """Return the path to the index database."""
        return repository_root / self.index_directory / self.index_database_name

    def index_directory_path(self, repository_root: Path) -> Path:
        """Return the path to the index directory."""
        return repository_root / self.index_directory


DEFAULT_CONFIG = Config()
