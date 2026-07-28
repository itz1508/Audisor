"""Diagnostics - pytest failure parsing, traceback parsing, and failure summarization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .contracts import RepositoryIntelligenceError


FailureType = Literal[
    "assertion",
    "import_error",
    "collection_error",
    "syntax_error",
    "timeout",
    "exception",
    "unknown",
]


class DiagnosticError(RepositoryIntelligenceError):
    """Raised when diagnostic operations fail."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class PytestFailure:
    """A parsed pytest failure."""

    test_name: str
    failure_type: FailureType
    file_path: str | None
    line_number: int | None
    message: str
    traceback: list[str]
    confidence: str  # "high", "medium", "low"

    def as_dict(self) -> dict:
        return {
            "test_name": self.test_name,
            "failure_type": self.failure_type,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "message": self.message,
            "traceback": self.traceback,
            "confidence": self.confidence,
        }


@dataclass
class TracebackFrame:
    """A frame in a Python traceback."""

    file_path: str
    line_number: int
    function_name: str
    code: str | None

    def as_dict(self) -> dict:
        result = {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "function_name": self.function_name,
        }
        if self.code:
            result["code"] = self.code
        return result


@dataclass
class ParsedTraceback:
    """A parsed Python traceback."""

    exception_type: str
    exception_message: str
    frames: list[TracebackFrame]

    def as_dict(self) -> dict:
        return {
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "frames": [f.as_dict() for f in self.frames],
        }


@dataclass
class FailureSummary:
    """A deterministic failure summary."""

    exit_code: int | None
    timed_out: bool
    failure_type: str
    primary_error: str | None
    file_path: str | None
    line_number: int | None
    summary: str
    is_speculative: bool  # True if root cause is not certain

    def as_dict(self) -> dict:
        result = {
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "failure_type": self.failure_type,
            "summary": self.summary,
            "is_speculative": self.is_speculative,
        }
        if self.primary_error:
            result["primary_error"] = self.primary_error
        if self.file_path:
            result["file_path"] = self.file_path
        if self.line_number:
            result["line_number"] = self.line_number
        return result


# Patterns for parsing pytest output
_PYTEST_HEADER = re.compile(r"=+ FAILURES =+")
_PYTEST_TEST_LINE = re.compile(r"_+\s+(.+?)\s+_+")
_PYTEST_ASSERTION = re.compile(r"E\s+AssertionError[:\s]*(.*)")
_PYTEST_IMPORT_ERROR = re.compile(r"E\s+(?:ImportError|ModuleNotFoundError)[:\s]*(.*)")
_PYTEST_FILE_LINE = re.compile(r"([^\s:]+):(\d+):")
_PYTEST_ERROR_LINE = re.compile(r"E\s+(\w+(?:Error|Exception))[:\s]*(.*)")


def _failure_from_parts(
    test_name: str,
    traceback: list[str],
    file_path: str | None,
    line_number: int | None,
) -> PytestFailure:
    """Build a PytestFailure from collected section parts."""
    failure_type, message, confidence = _classify_failure(traceback)
    return PytestFailure(
        test_name=test_name,
        failure_type=failure_type,
        file_path=file_path,
        line_number=line_number,
        message=message,
        traceback=traceback,
        confidence=confidence,
    )


def parse_test_failures(output: str) -> list[PytestFailure]:
    """Parse pytest output for failures."""
    failures: list[PytestFailure] = []

    lines = output.splitlines()
    in_failure_section = False
    current_test: str | None = None
    current_traceback: list[str] = []
    current_file: str | None = None
    current_line: int | None = None

    for line in lines:
        # Check for failure section start
        if _PYTEST_HEADER.search(line):
            in_failure_section = True
            continue

        if not in_failure_section:
            continue

        # Check for test name line
        test_match = _PYTEST_TEST_LINE.search(line)
        if test_match:
            # Save previous failure if any
            if current_test and current_traceback:
                failures.append(_failure_from_parts(
                    current_test, current_traceback, current_file, current_line,
                ))

            current_test = test_match.group(1).strip()
            current_traceback = []
            current_file = None
            current_line = None
            continue

        # Collect traceback lines
        if current_test:
            current_traceback.append(line)

            # Try to extract file/line
            file_match = _PYTEST_FILE_LINE.search(line)
            if file_match:
                current_file = file_match.group(1)
                current_line = int(file_match.group(2))

    # Don't forget the last failure
    if current_test and current_traceback:
        failures.append(_failure_from_parts(
            current_test, current_traceback, current_file, current_line,
        ))

    return failures


def _classify_failure(traceback: list[str]) -> tuple[FailureType, str, str]:
    """Classify a failure from its traceback; returns (type, message, confidence)."""
    text = "\n".join(traceback)

    # Check for assertion errors
    assertion_match = _PYTEST_ASSERTION.search(text)
    if assertion_match:
        message = assertion_match.group(1).strip() or "Assertion failed"
        return "assertion", message, "high"

    # Check for import errors
    import_match = _PYTEST_IMPORT_ERROR.search(text)
    if import_match:
        message = import_match.group(1).strip()
        return "import_error", message, "high"

    # Check for other errors
    error_match = _PYTEST_ERROR_LINE.search(text)
    if error_match:
        error_type = error_match.group(1)
        message = error_match.group(2).strip()

        if "SyntaxError" in error_type:
            return "syntax_error", message, "high"
        if "Timeout" in error_type:
            return "timeout", message, "high"

        return "exception", f"{error_type}: {message}", "medium"

    # Unknown
    return "unknown", "Unknown failure", "low"


# Patterns for parsing Python tracebacks
_TB_FILE_LINE = re.compile(r'File "([^"]+)", line (\d+), in (\w+)')
_TB_EXCEPTION = re.compile(r"^(\w+(?:Error|Exception|\w+)):\s*(.*)$")


def _tb_frame(
    file_path: str,
    line_number: int | None,
    function_name: str | None,
) -> TracebackFrame:
    """Build a TracebackFrame with defaults for missing parts."""
    return TracebackFrame(
        file_path=file_path,
        line_number=line_number or 0,
        function_name=function_name or "<module>",
        code=None,
    )


def parse_python_traceback(output: str) -> ParsedTraceback | None:
    """Parse a Python traceback; returns None if no traceback found."""
    lines = output.splitlines()
    frames: list[TracebackFrame] = []
    exception_type = "Unknown"
    exception_message = ""

    in_traceback = False
    current_file: str | None = None
    current_line: int | None = None
    current_func: str | None = None

    for line in lines:
        # Check for traceback start
        if "Traceback (most recent call last)" in line:
            in_traceback = True
            continue

        if not in_traceback:
            continue

        # Check for file/line
        file_match = _TB_FILE_LINE.match(line.strip())
        if file_match:
            # Save previous frame
            if current_file and current_line:
                frames.append(_tb_frame(current_file, current_line, current_func))

            current_file = file_match.group(1)
            current_line = int(file_match.group(2))
            current_func = file_match.group(3)
            continue

        # Check for exception line (not indented, contains Error/Exception)
        if current_file and not line.startswith(" ") and not line.startswith("File "):
            exc_match = _TB_EXCEPTION.match(line)
            if exc_match:
                exception_type = exc_match.group(1)
                exception_message = exc_match.group(2)
                # Save last frame
                frames.append(_tb_frame(current_file, current_line, current_func))
                break

    if not frames:
        return None

    return ParsedTraceback(
        exception_type=exception_type,
        exception_message=exception_message,
        frames=frames,
    )


def _classify_exit_failure(exit_code: int, combined: str) -> tuple[str, str, bool]:
    """Classify a non-zero exit; returns (failure_type, primary_error, is_speculative)."""
    if "ModuleNotFoundError" in combined or "ImportError" in combined:
        return "import_error", "Module not found", False
    if "SyntaxError" in combined:
        return "syntax_error", "Syntax error in code", False
    if "No such file or directory" in combined:
        return "file_not_found", "Required file not found", False
    if "Permission denied" in combined:
        return "permission_error", "Permission denied", False
    if "command not found" in combined.lower() or "not recognized" in combined.lower():
        return "command_not_found", "Command not found", False
    # Can't determine root cause
    return "unknown_error", f"Command failed with exit code {exit_code}", True


def _locate_failure(
    combined: str,
    pytest_failures: list[PytestFailure] | None,
) -> tuple[str | None, int | None]:
    """Extract file path and line number from failures or raw output."""
    if pytest_failures:
        return pytest_failures[0].file_path, pytest_failures[0].line_number
    file_match = _PYTEST_FILE_LINE.search(combined)
    if file_match:
        return file_match.group(1), int(file_match.group(2))
    return None, None


def _summary_text(
    failure_type: str,
    primary_error: str | None,
    pytest_failures: list[PytestFailure] | None,
) -> str:
    """Build the one-line failure summary."""
    if failure_type == "success":
        return "Command completed successfully"
    if failure_type == "timeout":
        return "Command exceeded time limit"
    if failure_type == "test_failure":
        test_count = len(pytest_failures) if pytest_failures else 0
        return f"{test_count} test(s) failed"
    return primary_error or "Command failed"


def summarise_command_failure(
    exit_code: int | None,
    timed_out: bool,
    stdout: str,
    stderr: str,
    pytest_failures: list[PytestFailure] | None = None,
) -> FailureSummary:
    """Create a deterministic failure summary."""
    combined = stdout + "\n" + stderr

    # Determine failure type
    if timed_out:
        failure_type, primary_error, is_speculative = "timeout", "Command timed out", False
    elif pytest_failures:
        failure_type = "test_failure"
        primary_error = pytest_failures[0].message if pytest_failures else "Test failed"
        is_speculative = False
    elif exit_code and exit_code != 0:
        failure_type, primary_error, is_speculative = _classify_exit_failure(exit_code, combined)
    else:
        failure_type, primary_error, is_speculative = "success", None, False

    file_path, line_number = _locate_failure(combined, pytest_failures)

    return FailureSummary(
        exit_code=exit_code,
        timed_out=timed_out,
        failure_type=failure_type,
        primary_error=primary_error,
        file_path=file_path,
        line_number=line_number,
        summary=_summary_text(failure_type, primary_error, pytest_failures),
        is_speculative=is_speculative,
    )
