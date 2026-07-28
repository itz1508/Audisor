"""Tests for path_security module."""

from __future__ import annotations

import pytest
from pathlib import Path

from audisor.repo_intelligence.path_security import (
    validate_repository_root,
    validate_relative_path,
    validate_path_containment,
    to_repository_relative,
)
from audisor.repo_intelligence.contracts import PathSecurityError


class TestValidateRepositoryRoot:
    """Tests for validate_repository_root."""

    def test_valid_directory(self, tmp_path):
        result = validate_repository_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_nonexistent_directory(self, tmp_path):
        with pytest.raises(PathSecurityError):
            validate_repository_root(tmp_path / "nonexistent")

    def test_file_not_directory(self, tmp_path):
        file_path = tmp_path / "file.txt"
        file_path.touch()
        with pytest.raises(PathSecurityError):
            validate_repository_root(file_path)


class TestValidateRelativePath:
    """Tests for validate_relative_path."""

    def test_valid_relative_path(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.py").touch()
        result = validate_relative_path(tmp_path, "subdir/file.py")
        assert result.exists()

    def test_absolute_path_rejected(self, tmp_path):
        with pytest.raises(PathSecurityError):
            validate_relative_path(tmp_path, "/etc/passwd")

    def test_traversal_rejected(self, tmp_path):
        with pytest.raises(PathSecurityError, match="Path traversal not allowed"):
            validate_relative_path(tmp_path, "../outside")

    def test_nested_traversal_rejected(self, tmp_path):
        with pytest.raises(PathSecurityError, match="Path traversal not allowed"):
            validate_relative_path(tmp_path, "subdir/../../outside")


class TestValidatePathContainment:
    """Tests for validate_path_containment."""

    def test_contained_path(self, tmp_path):
        (tmp_path / "file.py").touch()
        result = validate_path_containment(tmp_path, tmp_path / "file.py")
        assert result.exists()

    def test_escaping_path_rejected(self, tmp_path):
        with pytest.raises(PathSecurityError, match="escapes repository root"):
            validate_path_containment(tmp_path, tmp_path.parent / "outside")


class TestToRepositoryRelative:
    """Tests for to_repository_relative."""

    def test_converts_to_posix(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.py").touch()
        result = to_repository_relative(tmp_path / "subdir" / "file.py", tmp_path)
        assert result == "subdir/file.py"
        assert "\\" not in result
