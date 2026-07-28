"""Tests for language module."""

from __future__ import annotations

import pytest
from pathlib import Path

from audisor.repo_intelligence.language import (
    detect_language,
    is_text_file,
    validate_utf8,
    safe_decode_utf8,
    read_text_file,
)


class TestDetectLanguage:
    """Tests for detect_language."""

    def test_python_extension(self):
        assert detect_language(Path("module.py")) == "python"

    def test_javascript_extension(self):
        assert detect_language(Path("script.js")) == "javascript"

    def test_typescript_extension(self):
        assert detect_language(Path("module.ts")) == "typescript"

    def test_json_extension(self):
        assert detect_language(Path("config.json")) == "json"

    def test_yaml_extension(self):
        assert detect_language(Path("config.yaml")) == "yaml"
        assert detect_language(Path("config.yml")) == "yaml"

    def test_toml_extension(self):
        assert detect_language(Path("pyproject.toml")) == "toml"

    def test_unknown_extension(self):
        assert detect_language(Path("file.xyz")) == "unknown"

    def test_dockerfile(self):
        assert detect_language(Path("Dockerfile")) == "dockerfile"

    def test_makefile(self):
        assert detect_language(Path("Makefile")) == "makefile"


class TestIsTextFile:
    """Tests for is_text_file."""

    def test_python_is_text(self):
        assert is_text_file(Path("module.py"))

    def test_json_is_text(self):
        assert is_text_file(Path("config.json"))

    def test_unknown_may_not_be_text(self):
        # Unknown extensions are not recognized as text
        assert not is_text_file(Path("file.xyz"))


class TestValidateUtf8:
    """Tests for validate_utf8."""

    def test_valid_utf8(self):
        valid, error = validate_utf8(b"hello world")
        assert valid is True
        assert error is None

    def test_valid_utf8_unicode(self):
        valid, error = validate_utf8("héllo wörld".encode("utf-8"))
        assert valid is True
        assert error is None

    def test_invalid_utf8(self):
        valid, error = validate_utf8(b"hello \xff world")
        assert valid is False
        assert error is not None
        assert "UTF-8" in error


class TestSafeDecodeUtf8:
    """Tests for safe_decode_utf8."""

    def test_valid_decode(self):
        text, error = safe_decode_utf8(b"hello world")
        assert text == "hello world"
        assert error is None

    def test_invalid_decode(self):
        text, error = safe_decode_utf8(b"hello \xff world")
        assert text is None
        assert error is not None


class TestReadTextFile:
    """Tests for read_text_file."""

    def test_read_valid_file(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        content, error = read_text_file(file_path)
        assert content == "hello world"
        assert error is None

    def test_read_with_max_bytes(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello world", encoding="utf-8")
        content, error = read_text_file(file_path, max_bytes=5)
        assert content == "hello"
        assert error is None

    def test_read_nonexistent_file(self, tmp_path):
        file_path = tmp_path / "nonexistent.txt"
        content, error = read_text_file(file_path)
        assert content is None
        assert error is not None
