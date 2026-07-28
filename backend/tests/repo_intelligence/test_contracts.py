"""Tests for contracts module."""

from __future__ import annotations

import pytest

from audisor.repo_intelligence.contracts import (
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


class TestToolResult:
    """Tests for ToolResult envelope."""

    def test_success_result_has_required_fields(self):
        result = success("test_tool", {"key": "value"})
        d = result.as_dict()
        assert d["schema_version"] == SCHEMA_VERSION
        assert d["tool_name"] == "test_tool"
        assert d["status"] == "success"
        assert d["result"] == {"key": "value"}

    def test_error_result_has_error_field(self):
        result = error("test_tool", "test_error", "Something went wrong")
        d = result.as_dict()
        assert d["status"] == "error"
        assert len(d["errors"]) == 1
        assert d["errors"][0]["code"] == "test_error"
        assert d["errors"][0]["detail"] == "Something went wrong"

    def test_blocked_result(self):
        result = blocked("test_tool", "not_allowed", "Operation not permitted")
        d = result.as_dict()
        assert d["status"] == "blocked"
        assert d["errors"][0]["code"] == "not_allowed"

    def test_partial_result_has_truncation(self):
        truncation = TruncationInfo(True, "max_results", 100, 50)
        result = partial("test_tool", {"items": []}, truncation)
        d = result.as_dict()
        assert d["status"] == "partial"
        assert d["truncation"]["truncated"] is True
        assert d["truncation"]["reason"] == "max_results"

    def test_warnings_included_when_present(self):
        result = success("test_tool", {}, warnings=[{"code": "warn", "detail": "test"}])
        d = result.as_dict()
        assert len(d["warnings"]) == 1


class TestTruncationInfo:
    """Tests for TruncationInfo."""

    def test_not_truncated(self):
        info = TruncationInfo(False)
        d = info.as_dict()
        assert d["truncated"] is False
        assert "reason" not in d

    def test_truncated_with_details(self):
        info = TruncationInfo(True, "byte_limit", None, None, 1000)
        d = info.as_dict()
        assert d["truncated"] is True
        assert d["reason"] == "byte_limit"
        assert d["byte_limit"] == 1000


class TestExceptions:
    """Tests for exception classes."""

    def test_repository_intelligence_error(self):
        exc = RepositoryIntelligenceError("test_code", "test detail")
        assert exc.code == "test_code"
        assert exc.detail == "test detail"
        assert str(exc) == "test detail"

    def test_path_security_error(self):
        exc = PathSecurityError("path escapes root")
        assert exc.code == "path_security_violation"

    def test_command_execution_error(self):
        exc = CommandExecutionError("timeout", "command timed out")
        assert exc.code == "timeout"

    def test_patch_error(self):
        exc = PatchError("hash_mismatch", "hashes don't match")
        assert exc.code == "hash_mismatch"


class TestEvidenceMetadata:
    """Tests for EvidenceMetadata."""

    def test_minimal_metadata(self):
        meta = EvidenceMetadata("/repo", "file.py")
        d = meta.as_dict()
        assert d["repository_root"] == "/repo"
        assert d["relative_path"] == "file.py"
        assert "sha256" not in d

    def test_full_metadata(self):
        meta = EvidenceMetadata("/repo", "file.py", "abc123", 10, 5)
        d = meta.as_dict()
        assert d["sha256"] == "abc123"
        assert d["line"] == 10
        assert d["column"] == 5
