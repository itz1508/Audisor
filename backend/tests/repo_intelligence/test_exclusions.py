"""Tests for exclusions module."""

from __future__ import annotations

import pytest
from pathlib import Path

from audisor.repo_intelligence.exclusions import (
    HARD_EXCLUSIONS,
    BINARY_EXTENSIONS,
    is_excluded_by_name,
    is_excluded_path,
    is_binary_file,
    is_credential_file,
    should_index_file,
)


class TestIsExcludedByName:
    """Tests for is_excluded_by_name."""

    def test_git_excluded(self):
        assert is_excluded_by_name(".git")

    def test_venv_excluded(self):
        assert is_excluded_by_name(".venv")

    def test_node_modules_excluded(self):
        assert is_excluded_by_name("node_modules")

    def test_pycache_excluded(self):
        assert is_excluded_by_name("__pycache__")

    def test_audisor_excluded(self):
        assert is_excluded_by_name(".audisor")

    def test_normal_name_not_excluded(self):
        assert not is_excluded_by_name("src")
        assert not is_excluded_by_name("tests")


class TestIsExcludedPath:
    """Tests for is_excluded_path."""

    def test_nested_excluded(self):
        assert is_excluded_path(Path("src/__pycache__/module.pyc"))

    def test_normal_path_not_excluded(self):
        assert not is_excluded_path(Path("src/module.py"))

    def test_git_subdirectory_excluded(self):
        assert is_excluded_path(Path(".git/config"))


class TestIsBinaryFile:
    """Tests for is_binary_file."""

    def test_png_is_binary(self, tmp_path):
        png_file = tmp_path / "image.png"
        png_file.touch()
        assert is_binary_file(png_file)

    def test_py_not_binary(self, tmp_path):
        py_file = tmp_path / "module.py"
        py_file.write_text("print('hello')")
        assert not is_binary_file(py_file)

    def test_file_with_null_bytes_is_binary(self, tmp_path):
        binary_file = tmp_path / "data.bin"
        binary_file.write_bytes(b"hello\x00world")
        assert is_binary_file(binary_file)


class TestIsCredentialFile:
    """Tests for is_credential_file."""

    def test_env_file_is_credential(self):
        assert is_credential_file(Path(".env"))

    def test_env_local_is_credential(self):
        assert is_credential_file(Path(".env.local"))

    def test_secrets_yaml_is_credential(self):
        assert is_credential_file(Path("secrets.yml"))

    def test_normal_file_not_credential(self):
        assert not is_credential_file(Path("config.py"))


class TestShouldIndexFile:
    """Tests for should_index_file."""

    def test_normal_python_file(self):
        assert should_index_file(Path("src/module.py"))

    def test_excluded_directory(self):
        assert not should_index_file(Path(".git/config"))

    def test_credential_file_excluded(self):
        assert not should_index_file(Path(".env"))
