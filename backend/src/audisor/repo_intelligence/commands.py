"""Command execution with timeout, output limits, and process management."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import Config, DEFAULT_CONFIG
from .contracts import RepositoryIntelligenceError
from .operations import (
    Operation,
    complete_operation,
    create_operation,
    fail_operation,
    start_operation,
)
from .path_security import validate_repository_root


class CommandError(RepositoryIntelligenceError):
    """Raised when command execution fails."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(code, detail)


@dataclass
class CommandResult:
    """Result of command execution."""

    operation_id: str
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    elapsed_seconds: float
    truncated: bool

    def as_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "truncated": self.truncated,
        }


# Validation profiles derived from repository inspection
VALIDATION_PROFILES = {
    "focused": {
        "description": "Run focused tests for changed files",
        "command_template": ["uv", "run", "python", "-m", "pytest", "-x", "-v", "{path}"],
    },
    "runtime": {
        "description": "Run runtime/lifecycle tests",
        "command_template": ["uv", "run", "--directory", "openai_project/runtime", "pytest", "tests/audisor_lifecycle/"],
    },
    "backend": {
        "description": "Run backend toolkit tests",
        "command_template": ["uv", "run", "--directory", "audisor/backend", "pytest", "tests/"],
    },
    "aflow": {
        "description": "Run A-Flow lifecycle tests",
        "command_template": ["uv", "run", "--directory", "audisor/backend", "pytest", "tests/", "-k", "aflow"],
    },
    "scripts": {
        "description": "Run scripts tests",
        "command_template": ["uv", "run", "pytest", "scripts/tests/"],
    },
    "fixtures": {
        "description": "Run fixture tests",
        "command_template": ["uv", "run", "--directory", "audisor/backend", "pytest", "tests/", "-k", "fixture"],
    },
    "size": {
        "description": "Check repository size",
        "command_template": ["uv", "run", "python", "scripts/check_size.py"],
    },
    "build": {
        "description": "Build the package",
        "command_template": ["uv", "build", "--directory", "audisor/backend"],
    },
    "compile": {
        "description": "Compile check Python files",
        "command_template": ["uv", "run", "--directory", "audisor/backend", "python", "-m", "compileall", "src/audisor/repo_intelligence/"],
    },
}


def _terminate_process_tree(process: subprocess.Popen) -> None:
    """Terminate a process and all its children.

    Args:
        process: Process to terminate
    """
    pid = process.pid

    if sys.platform == "win32":
        # Windows: use taskkill to terminate process tree
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=5,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass
    else:
        # Unix: use process group kill
        try:
            import signal
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass

    try:
        process.kill()
    except (OSError, ProcessLookupError):
        pass


def _enforce_python_policy(command: list[str]) -> None:
    """Reject bare python/python3/py interpreters (use 'uv run python')."""
    if not command:
        return
    first_arg = command[0].lower()
    # Check for bare python interpreters (not uv run python)
    if first_arg in ("python", "python3", "py"):
        raise CommandError(
            "policy_rejected",
            f"Bare Python interpreter '{command[0]}' is not permitted. "
            "Use 'uv run python' for consistent environment management.",
        )
    # Check for py -3 pattern
    if first_arg == "py" and len(command) > 1 and command[1] == "-3":
        raise CommandError(
            "policy_rejected",
            "Bare Python launcher 'py -3' is not permitted. "
            "Use 'uv run python' for consistent environment management.",
        )


def _resolve_cwd(repository_root: Path, working_directory: str | None) -> Path:
    """Resolve the working directory for command execution."""
    if working_directory:
        cwd = repository_root / working_directory
        if not cwd.is_dir():
            raise CommandError("working_directory_not_found", f"Working directory not found: {working_directory}")
        return cwd
    return repository_root


def _truncate_output(text: str, max_output_bytes: int) -> tuple[str, bool]:
    """Truncate output to the byte limit; returns (text, truncated)."""
    if len(text.encode("utf-8")) > max_output_bytes:
        return text.encode("utf-8")[:max_output_bytes].decode("utf-8", errors="ignore"), True
    return text, False


def _execute_command(
    operation_id: str,
    command: list[str],
    cwd: Path,
    timeout_seconds: int,
    max_output_bytes: int,
    start_time: float,
) -> CommandResult:
    """Run the process, enforce timeout and output limits, build the result."""
    timed_out = False
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()

    stdout, out_truncated = _truncate_output(stdout, max_output_bytes)
    stderr, err_truncated = _truncate_output(stderr, max_output_bytes)

    return CommandResult(
        operation_id=operation_id,
        command=command,
        exit_code=process.returncode if not timed_out else -1,
        stdout=stdout or "",
        stderr=stderr or "",
        timed_out=timed_out,
        elapsed_seconds=time.time() - start_time,
        truncated=out_truncated or err_truncated,
    )


def _record_outcome(repository_root: Path, result: CommandResult, config: Config) -> None:
    """Persist the operation outcome for a completed command."""
    if result.timed_out:
        fail_operation(repository_root, result.operation_id, "timeout", "Command timed out", config)
    elif result.exit_code != 0:
        fail_operation(repository_root, result.operation_id, "non_zero_exit", f"Exit code: {result.exit_code}", config)
    else:
        complete_operation(repository_root, result.operation_id, result.as_dict(), config)


def _error_result(
    repository_root: Path,
    operation_id: str,
    command: list[str],
    error_code: str,
    detail: str,
    stderr_text: str,
    start_time: float,
    config: Config,
) -> CommandResult:
    """Record a failed operation and build the error CommandResult."""
    elapsed = time.time() - start_time
    fail_operation(repository_root, operation_id, error_code, detail, config)
    return CommandResult(
        operation_id=operation_id,
        command=command,
        exit_code=-1,
        stdout="",
        stderr=stderr_text,
        timed_out=False,
        elapsed_seconds=elapsed,
        truncated=False,
    )


def run_command(
    repository_root: Path,
    command: list[str],
    timeout_seconds: int | None = None,
    max_output_bytes: int | None = None,
    working_directory: str | None = None,
    config: Config = DEFAULT_CONFIG,
) -> CommandResult:
    """Execute a command with timeout and output limits.

    Raises CommandError if the command is rejected by policy.
    """
    repository_root = validate_repository_root(repository_root)
    _enforce_python_policy(command)

    if timeout_seconds is None:
        timeout_seconds = config.command_timeout_seconds
    if max_output_bytes is None:
        max_output_bytes = config.max_command_output_bytes

    cwd = _resolve_cwd(repository_root, working_directory)

    operation = create_operation(repository_root, "command", config)
    start_operation(repository_root, operation.operation_id, config)
    start_time = time.time()

    try:
        result = _execute_command(
            operation.operation_id, command, cwd,
            timeout_seconds, max_output_bytes, start_time,
        )
        _record_outcome(repository_root, result, config)
        return result

    except FileNotFoundError as exc:
        return _error_result(
            repository_root, operation.operation_id, command,
            "command_not_found", str(exc), f"Command not found: {exc}",
            start_time, config,
        )
    except PermissionError as exc:
        return _error_result(
            repository_root, operation.operation_id, command,
            "permission_denied", str(exc), f"Permission denied: {exc}",
            start_time, config,
        )
    except Exception as exc:
        return _error_result(
            repository_root, operation.operation_id, command,
            "execution_error", str(exc), f"Execution error: {exc}",
            start_time, config,
        )


def run_validation(
    repository_root: Path,
    profile: str,
    path: str | None = None,
    timeout_seconds: int | None = None,
    config: Config = DEFAULT_CONFIG,
) -> CommandResult:
    """Run a validation profile.

    Args:
        repository_root: Repository root directory
        profile: Validation profile name
        path: Optional path for focused tests
        timeout_seconds: Command timeout
        config: Configuration to use

    Returns:
        CommandResult with execution details
    """
    if profile not in VALIDATION_PROFILES:
        raise CommandError(
            "unknown_profile",
            f"Unknown validation profile: {profile}. Available: {', '.join(VALIDATION_PROFILES.keys())}",
        )

    profile_config = VALIDATION_PROFILES[profile]
    command = list(profile_config["command_template"])

    # Substitute path if provided and needed
    if path and "{path}" in " ".join(command):
        command = [arg.replace("{path}", path) for arg in command]

    return run_command(
        repository_root=repository_root,
        command=command,
        timeout_seconds=timeout_seconds,
        config=config,
    )


def get_python_command(config: Config = DEFAULT_CONFIG) -> list[str]:
    """Get the Python command to use.

    Args:
        config: Configuration to use

    Returns:
        Command array for running Python
    """
    if config.use_uv_run_python and sys.platform == "win32":
        return ["uv", "run", "python"]
    return [sys.executable]
