"""Tests for indexer module."""

from __future__ import annotations

import pytest
from pathlib import Path

from audisor.repo_intelligence.indexer import (
    full_index,
    incremental_refresh,
    get_index_status,
    compute_file_hash,
    IndexingStats,
)
from audisor.repo_intelligence.config import Config


class TestComputeFileHash:
    """Tests for compute_file_hash."""

    def test_hash_consistent(self):
        content = b"hello world"
        hash1 = compute_file_hash(content)
        hash2 = compute_file_hash(content)
        assert hash1 == hash2

    def test_hash_different_content(self):
        hash1 = compute_file_hash(b"hello")
        hash2 = compute_file_hash(b"world")
        assert hash1 != hash2


class TestIndexingStats:
    """Tests for IndexingStats."""

    def test_as_dict(self):
        stats = IndexingStats(
            files_examined=10,
            files_indexed=8,
            files_reparsed=2,
            elapsed_seconds=1.5,
        )
        d = stats.as_dict()
        assert d["files_examined"] == 10
        assert d["files_indexed"] == 8
        assert d["elapsed_seconds"] == 1.5


class TestFullIndex:
    """Tests for full_index."""

    def test_index_empty_directory(self, tmp_path):
        stats = full_index(tmp_path)
        assert stats.files_examined == 0
        assert stats.files_indexed == 0

    def test_index_python_file(self, tmp_path):
        (tmp_path / "module.py").write_text("def hello(): pass")
        stats = full_index(tmp_path)
        assert stats.files_examined >= 1
        assert stats.files_indexed >= 1

    def test_index_multiple_files(self, tmp_path):
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        (tmp_path / "c.txt").write_text("text")
        stats = full_index(tmp_path)
        assert stats.files_examined >= 3

    def test_index_excludes_git_directory(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")
        (tmp_path / "module.py").write_text("x = 1")
        stats = full_index(tmp_path)
        # .git should be excluded
        assert stats.files_examined == 1

    def test_index_excludes_pycache(self, tmp_path):
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "module.pyc").write_bytes(b"\x00\x00")
        (tmp_path / "module.py").write_text("x = 1")
        stats = full_index(tmp_path)
        assert stats.files_examined == 1


class TestIncrementalRefresh:
    """Tests for incremental_refresh."""

    def test_refresh_no_changes(self, tmp_path):
        (tmp_path / "module.py").write_text("x = 1")
        full_index(tmp_path)
        stats = incremental_refresh(tmp_path)
        # No changes, should not reparse
        assert stats.files_reparsed == 0

    def test_refresh_with_changes(self, tmp_path):
        (tmp_path / "module.py").write_text("x = 1")
        full_index(tmp_path)
        (tmp_path / "module.py").write_text("x = 2")
        stats = incremental_refresh(tmp_path)
        # File changed, should reparse
        assert stats.files_reparsed >= 1


class TestGetIndexStatus:
    """Tests for get_index_status."""

    def test_status_no_index(self, tmp_path):
        status = get_index_status(tmp_path)
        assert status["exists"] is False
        assert status["status"] == "not_found"

    def test_status_after_index(self, tmp_path):
        (tmp_path / "module.py").write_text("x = 1")
        full_index(tmp_path)
        status = get_index_status(tmp_path)
        assert status["exists"] is True
        assert status["status"] == "ready"
        assert status["file_count"] >= 1
