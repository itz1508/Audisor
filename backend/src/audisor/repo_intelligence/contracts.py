"""Result envelopes, status vocabulary, and error classification for repository intelligence tools."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SCHEMA_VERSION = "1.0.0"


class RepositoryIntelligenceError(Exception):
    """Base exception for repository intelligence operations."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class PathSecurityError(RepositoryIntelligenceError):
    """Raised when a path violates security constraints."""

    def __init__(self, detail: str) -> None:
        super().__init__("path_security_violation", detail)


class IndexError(RepositoryIntelligenceError):
    """Raised when index operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


class CommandExecutionError(RepositoryIntelligenceError):
    """Raised when command execution fails."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


class PatchError(RepositoryIntelligenceError):
    """Raised when patch operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass(frozen=True)
class ErrorInfo:
    """Structured error information."""

    code: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class TruncationInfo:
    """Information about truncated results."""

    truncated: bool
    reason: str | None = None
    original_count: int | None = None
    returned_count: int | None = None
    byte_limit: int | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"truncated": self.truncated}
        if self.reason is not None:
            result["reason"] = self.reason
        if self.original_count is not None:
            result["original_count"] = self.original_count
        if self.returned_count is not None:
            result["returned_count"] = self.returned_count
        if self.byte_limit is not None:
            result["byte_limit"] = self.byte_limit
        return result


@dataclass(frozen=True)
class EvidenceMetadata:
    """Metadata about evidence collection."""

    repository_root: str
    relative_path: str
    sha256: str | None = None
    line: int | None = None
    column: int | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "repository_root": self.repository_root,
            "relative_path": self.relative_path,
        }
        if self.sha256 is not None:
            result["sha256"] = self.sha256
        if self.line is not None:
            result["line"] = self.line
        if self.column is not None:
            result["column"] = self.column
        return result


@dataclass(frozen=True)
class ToolResult:
    """Standard result envelope for all repository intelligence tools."""

    schema_version: str
    tool_name: str
    status: str
    result: dict[str, Any] | None = None
    warnings: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    truncation: TruncationInfo | None = None

    def as_dict(self) -> dict[str, Any]:
        result_dict: dict[str, Any] = {
            "schema_version": self.schema_version,
            "tool_name": self.tool_name,
            "status": self.status,
        }
        if self.result is not None:
            result_dict["result"] = self.result
        if self.warnings:
            result_dict["warnings"] = [w.as_dict() if isinstance(w, ErrorInfo) else w for w in self.warnings]
        if self.errors:
            result_dict["errors"] = [e.as_dict() if isinstance(e, ErrorInfo) else e for e in self.errors]
        if self.truncation is not None:
            result_dict["truncation"] = self.truncation.as_dict() if isinstance(self.truncation, TruncationInfo) else self.truncation
        return result_dict


def success(tool_name: str, result: dict[str, Any], warnings: list[dict[str, str]] | None = None) -> ToolResult:
    """Create a success result."""
    return ToolResult(
        schema_version=SCHEMA_VERSION,
        tool_name=tool_name,
        status="success",
        result=result,
        warnings=warnings or [],
    )


def partial(tool_name: str, result: dict[str, Any], truncation: TruncationInfo, warnings: list[dict[str, str]] | None = None) -> ToolResult:
    """Create a partial success result with truncation info."""
    return ToolResult(
        schema_version=SCHEMA_VERSION,
        tool_name=tool_name,
        status="partial",
        result=result,
        warnings=warnings or [],
        truncation=truncation,
    )


def error(tool_name: str, code: str, detail: str) -> ToolResult:
    """Create an error result."""
    return ToolResult(
        schema_version=SCHEMA_VERSION,
        tool_name=tool_name,
        status="error",
        errors=[ErrorInfo(code=code, detail=detail).as_dict()],
    )


def blocked(tool_name: str, code: str, detail: str) -> ToolResult:
    """Create a blocked result (operation not permitted)."""
    return ToolResult(
        schema_version=SCHEMA_VERSION,
        tool_name=tool_name,
        status="blocked",
        errors=[ErrorInfo(code=code, detail=detail).as_dict()],
    )
