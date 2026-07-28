"""POSIX process-group isolation regression tests for command execution.

The command runner must spawn every POSIX child in its own session so the
timeout path's group termination (os.killpg) can never signal the caller's
-- the pytest runner's -- process group. Every timeout test here embeds an
isolation guard in the child: if the child does not lead its own process
group, it exits immediately, before any sleep, so a regression fails these
tests without ever triggering group termination against the runner.
"""

from __future__ import annotations

import os
import signal
import sys
import time

import pytest

from audisor.repo_intelligence.commands import run_command

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-only: Windows uses the scoped taskkill process-tree path",
)

# Child preamble: refuse to sleep into the timeout unless the child owns its
# process group. Exit code 42 marks a detected isolation regression.
ISOLATION_GUARD = (
    "import os, sys\n"
    "if os.getpgid(0) != os.getpid():\n"
    "    sys.exit(42)\n"
)


def _is_dead(pid: int) -> bool:
    """True when the pid no longer exists or is a terminated (zombie) orphan.

    A killed grandchild reparented to an init that never reaps it stays
    visible as a zombie; it can no longer execute, so it counts as dead.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as handle:
            stat = handle.read()
        return stat.rpartition(")")[2].split()[0] == "Z"
    except OSError:
        return False


def _wait_dead(pid: int, deadline_seconds: float = 10.0) -> bool:
    """Poll until the pid is dead per _is_dead."""
    deadline = time.time() + deadline_seconds
    while time.time() < deadline:
        if _is_dead(pid):
            return True
        time.sleep(0.05)
    return False


class TestPosixProcessGroupIsolation:
    """Prove POSIX subprocess-group isolation and scoped termination."""

    def test_child_runs_in_isolated_process_group(self, tmp_path):
        """Child leads its own process group, distinct from the runner's.

        Runs to completion with no timeout, so isolation is inspected
        before any group termination can occur.
        """
        result = run_command(
            tmp_path,
            [sys.executable, "-c", "import os; print(os.getpid(), os.getpgid(0))"],
        )
        assert result.exit_code == 0
        child_pid, child_pgid = (int(part) for part in result.stdout.split())
        assert child_pgid == child_pid
        assert child_pgid != os.getpgid(0)

    def test_timeout_termination_leaves_runner_alive(self, tmp_path):
        """Timeout group-kill must not signal the pytest runner."""
        received: list[int] = []
        previous = signal.signal(
            signal.SIGTERM, lambda signum, frame: received.append(signum)
        )
        runner_pgid = os.getpgid(0)
        try:
            result = run_command(
                tmp_path,
                [sys.executable, "-c", ISOLATION_GUARD + "import time; time.sleep(30)"],
                timeout_seconds=1,
            )
        finally:
            signal.signal(signal.SIGTERM, previous)
        assert result.timed_out is True
        assert received == []
        assert os.getpgid(0) == runner_pgid

    def test_timeout_terminates_child_and_grandchild(self, tmp_path):
        """Group termination reaches the direct child and its descendants."""
        child_code = ISOLATION_GUARD + (
            "import subprocess, time\n"
            "grandchild = subprocess.Popen("
            "[sys.executable, '-c', 'import time; time.sleep(30)'])\n"
            "print(os.getpid(), grandchild.pid, flush=True)\n"
            "time.sleep(30)\n"
        )
        result = run_command(
            tmp_path, [sys.executable, "-c", child_code], timeout_seconds=2
        )
        assert result.timed_out is True
        child_pid, grandchild_pid = (int(part) for part in result.stdout.split())
        assert _wait_dead(child_pid)
        assert _wait_dead(grandchild_pid)

    def test_escalation_kills_child_ignoring_sigterm(self, tmp_path):
        """The SIGKILL escalation terminates a child that ignores SIGTERM."""
        child_code = ISOLATION_GUARD + (
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print(os.getpid(), flush=True)\n"
            "time.sleep(30)\n"
        )
        result = run_command(
            tmp_path, [sys.executable, "-c", child_code], timeout_seconds=1
        )
        assert result.timed_out is True
        child_pid = int(result.stdout.strip())
        assert _wait_dead(child_pid)
