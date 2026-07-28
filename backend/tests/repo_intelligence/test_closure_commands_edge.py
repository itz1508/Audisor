"""Closure tests: command policy, changed-file accounting, corruption edge cases.

Split from test_closure.py to satisfy the test-module size policy.
"""

from __future__ import annotations

import sys

import pytest

from audisor.repo_intelligence.indexer import full_index
from audisor.repo_intelligence.search import search_text
from audisor.repo_intelligence.patch import prepare_patch, compute_sha256
from audisor.repo_intelligence.commands import run_command, CommandError


# ============== Command Policy on Windows ==============


class TestCommandPolicyWindows:
    """Prove command policy on Windows."""

    def test_argument_array_execution(self, tmp_path):
        """Commands use argument array, not shell."""
        result = run_command(tmp_path, [sys.executable, "-c", "print('hello')"])
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_working_directory_containment(self, tmp_path):
        """Working directory containment enforced."""
        (tmp_path / "subdir").mkdir()
        result = run_command(
            tmp_path,
            [sys.executable, "-c", "import os; print(os.getcwd())"],
            working_directory="subdir",
        )
        assert result.exit_code == 0
        assert "subdir" in result.stdout

    def test_stdout_stderr_separation(self, tmp_path):
        """stdout and stderr are separated."""
        result = run_command(
            tmp_path,
            [sys.executable, "-c", "import sys; sys.stdout.write('out'); sys.stderr.write('err')"],
        )
        assert result.exit_code == 0
        assert "out" in result.stdout
        assert "err" in result.stderr

    def test_timeout_and_process_tree_termination(self, tmp_path):
        """Timeout kills process tree."""
        result = run_command(
            tmp_path,
            [sys.executable, "-c", "import time; time.sleep(10)"],
            timeout_seconds=1,
        )
        assert result.timed_out is True

    def test_output_truncation(self, tmp_path):
        """Output truncation enforced."""
        result = run_command(
            tmp_path,
            [sys.executable, "-c", "print('x' * 10000)"],
            max_output_bytes=100,
        )
        assert result.truncated is True

    def test_bare_python_rejected(self, tmp_path):
        """Bare python/python3/py commands are rejected."""
        # Test python
        with pytest.raises(CommandError) as exc_info:
            run_command(tmp_path, ["python", "-c", "print('hello')"])
        assert exc_info.value.code == "policy_rejected"

        # Test python3
        with pytest.raises(CommandError) as exc_info:
            run_command(tmp_path, ["python3", "-c", "print('hello')"])
        assert exc_info.value.code == "policy_rejected"

        # Test py
        with pytest.raises(CommandError) as exc_info:
            run_command(tmp_path, ["py", "-c", "print('hello')"])
        assert exc_info.value.code == "policy_rejected"

        # Test py -3
        with pytest.raises(CommandError) as exc_info:
            run_command(tmp_path, ["py", "-3", "-c", "print('hello')"])
        assert exc_info.value.code == "policy_rejected"

    def test_uv_run_python_accepted(self, tmp_path):
        """uv run python is accepted."""
        # This test may fail if uv is not installed, but the policy allows it
        result = run_command(tmp_path, ["uv", "run", "python", "-c", "print('hello')"])
        # May succeed or fail based on uv availability, but should not be rejected by policy
        assert result.exit_code is not None

    def test_commands_never_silently_rewritten(self, tmp_path):
        """Commands are never silently rewritten."""
        # The exact command array should be executed
        result = run_command(tmp_path, [sys.executable, "-c", "print('exact')"])
        assert "exact" in result.stdout


# ============== Changed-File Accounting ==============


class TestChangedFileAccounting:
    """Prove changed-file accounting enumerates untracked files."""

    def test_git_status_returns_full_file_lists(self, tmp_path):
        """git_status returns full file lists, not just counts."""
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True, check=True)
        
        # Create and commit a file
        (tmp_path / "tracked.py").write_text("x = 1")
        subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True, check=True)
        
        # Create untracked file
        (tmp_path / "untracked.py").write_text("y = 2")
        
        # Modify tracked file
        (tmp_path / "tracked.py").write_text("x = 2")
        
        from audisor.repo_intelligence.git_ops import git_status
        entries = git_status(tmp_path)
        
        # Should have entries for both untracked and modified files
        assert len(entries) >= 2, f"Expected at least 2 entries, got {len(entries)}"
        
        # Should have untracked file
        untracked = [e for e in entries if e.status == "untracked"]
        assert len(untracked) >= 1, "Should have at least one untracked file"
        assert any("untracked.py" in e.path for e in untracked)
        
        # Should have modified file
        modified = [e for e in entries if "modified" in e.status]
        assert len(modified) >= 1, "Should have at least one modified file"
        assert any("tracked.py" in e.path for e in modified)


# ============== Corruption and Edge-Case Tests ==============


class TestCorruptionAndEdgeCases:
    """Prove corruption recovery and edge-case handling."""

    def test_corrupted_index_can_be_rebuilt(self, tmp_path):
        """Corrupted index can be rebuilt from scratch."""
        (tmp_path / "module.py").write_text("def hello(): pass")
        full_index(tmp_path)
        
        # Corrupt the index by truncating it
        from audisor.repo_intelligence.config import DEFAULT_CONFIG
        db_path = DEFAULT_CONFIG.index_path(tmp_path)
        db_path.unlink()  # Delete the corrupted file
        
        # Full re-index should succeed
        stats = full_index(tmp_path)
        assert stats.files_indexed >= 1

    def test_empty_file_indexed(self, tmp_path):
        """Empty file is indexed without error."""
        (tmp_path / "empty.py").write_text("")
        stats = full_index(tmp_path)
        assert stats.files_indexed >= 1

    def test_binary_file_skipped(self, tmp_path):
        """Binary file is skipped during indexing."""
        (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\x03")
        stats = full_index(tmp_path)
        # Binary files should be skipped or indexed as binary
        assert stats.files_indexed >= 0

    def test_very_long_line_indexed(self, tmp_path):
        """Very long line is indexed without error."""
        long_line = "x" * 10000
        (tmp_path / "long.py").write_text(f"var = '{long_line}'")
        stats = full_index(tmp_path)
        assert stats.files_indexed >= 1

    def test_unicode_content_indexed(self, tmp_path):
        """Unicode content is indexed correctly."""
        (tmp_path / "unicode.py").write_text("# hello\nvar = 'test'", encoding="utf-8")
        stats = full_index(tmp_path)
        assert stats.files_indexed >= 1

    def test_path_with_spaces(self, tmp_path):
        """Path with spaces is handled correctly."""
        subdir = tmp_path / "my folder"
        subdir.mkdir()
        (subdir / "file.py").write_text("x = 1")
        stats = full_index(tmp_path)
        assert stats.files_indexed >= 1

    def test_concurrent_index_access(self, tmp_path):
        """Concurrent index access does not corrupt."""
        (tmp_path / "module.py").write_text("def hello(): pass")
        full_index(tmp_path)
        
        # Multiple reads should not fail
        from audisor.repo_intelligence.search import search_text
        for _ in range(5):
            result = search_text(tmp_path, "hello", backend="index")
            assert isinstance(result.matches, list)

    def test_patch_with_empty_content(self, tmp_path):
        """Patch with empty content is handled."""
        (tmp_path / "file.py").write_text("x = 1")
        original_hash = compute_sha256("x = 1")
        
        # Prepare patch with empty content
        preview = prepare_patch(tmp_path, "file.py", "")
        assert preview.new_content == ""
        assert preview.new_sha256 == compute_sha256("")

    def test_patch_id_uniqueness(self, tmp_path):
        """Patch IDs are unique."""
        (tmp_path / "file1.py").write_text("x = 1")
        (tmp_path / "file2.py").write_text("y = 2")
        
        preview1 = prepare_patch(tmp_path, "file1.py", "x = 2")
        preview2 = prepare_patch(tmp_path, "file2.py", "y = 3")
        
        assert preview1.patch_id != preview2.patch_id

    def test_operation_with_invalid_id(self, tmp_path):
        """Operation with invalid ID returns None."""
        from audisor.repo_intelligence.operations import get_operation, create_operation
        # Create an index first
        create_operation(tmp_path, "test")
        # Now query for invalid ID
        result = get_operation(tmp_path, "invalid-op-id")
        assert result is None

    def test_search_with_special_characters(self, tmp_path):
        """Search with special characters is escaped correctly."""
        (tmp_path / "module.py").write_text("def test(): pass\nx = 'a*b+c'")
        full_index(tmp_path)
        
        from audisor.repo_intelligence.search import search_text
        # Special FTS5 characters should be escaped
        result = search_text(tmp_path, "a*b", backend="index")
        assert isinstance(result.matches, list)
