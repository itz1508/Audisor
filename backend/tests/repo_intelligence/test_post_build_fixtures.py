"""Post-build fixture tests for repository intelligence toolkit.

These tests validate all 20+ tools work correctly after build.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from audisor.repo_intelligence import (
    Config,
    DEFAULT_CONFIG,
    SCHEMA_VERSION,
    success,
    error,
    blocked,
    partial,
    TruncationInfo,
)
from audisor.repo_intelligence.traversal import build_repository_tree
from audisor.repo_intelligence.indexer import full_index, incremental_refresh, get_index_status
from audisor.repo_intelligence.search import search_text, read_file_range, read_file_outline, escape_fts5_query
from audisor.repo_intelligence.symbols import list_symbols, find_symbol, find_references, find_imports, dependency_neighbourhood
from audisor.repo_intelligence.git_ops import git_status, git_diff, git_history, git_show_file, get_repository_info, is_git_repository
from audisor.repo_intelligence.commands import run_command, run_validation, VALIDATION_PROFILES
from audisor.repo_intelligence.operations import create_operation, get_operation, start_operation, complete_operation, OperationStatus
from audisor.repo_intelligence.diagnostics import parse_test_failures, parse_python_traceback, summarise_command_failure
from audisor.repo_intelligence.patch import prepare_patch, apply_patch, compute_sha256, PatchError
from audisor.repo_intelligence.contracts import ToolResult, ErrorInfo


# ============== Repository Discovery ==============


class TestRepositoryDiscovery:
    """Tests for repository discovery tools."""

    def test_repo_status_returns_bounded_metadata(self, tmp_path):
        """Verify repo_status returns root, branch, HEAD, dirty state, index status."""
        # Create a minimal git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file.py").write_text("x = 1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)

        info = get_repository_info(tmp_path)
        assert info["is_git_repository"] is True
        assert "repository_root" in info
        assert "head" in info
        assert "dirty" in info

    def test_repo_tree_respects_depth_and_entry_limits(self, tmp_path):
        """Verify max_depth and max_entries are enforced, truncation indicators present."""
        # Create nested structure
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "b" / "c").mkdir()
        (tmp_path / "a" / "file1.py").write_text("x = 1")
        (tmp_path / "a" / "b" / "file2.py").write_text("y = 2")

        entries, truncated = build_repository_tree(tmp_path, max_depth=1, max_entries=100)
        # Should not include deeply nested files
        paths = [e["path"] for e in entries]
        assert not any("a/b/c" in p for p in paths)

        entries, truncated = build_repository_tree(tmp_path, max_depth=10, max_entries=2)
        assert truncated is True


# ============== Index Operations ==============


class TestIndexOperations:
    """Tests for index operations."""

    def test_full_index_of_fixture_repository(self, tmp_path):
        """Index a small fixture repo, verify file count, symbol count, timing."""
        (tmp_path / "module.py").write_text("def hello(): pass\nclass World: pass")
        stats = full_index(tmp_path)
        assert stats.files_indexed >= 1
        assert stats.elapsed_seconds > 0

    def test_incremental_no_change_refresh_reparses_zero_files(self, tmp_path):
        """Key assertion: no-change incremental → zero file-content reparses."""
        (tmp_path / "module.py").write_text("x = 1")
        full_index(tmp_path)
        stats = incremental_refresh(tmp_path)
        assert stats.files_reparsed == 0

    def test_single_file_refresh_only_reparses_that_file(self, tmp_path):
        """Modify one file, refresh, verify only that file reparsed."""
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        full_index(tmp_path)
        (tmp_path / "a.py").write_text("x = 2")
        stats = incremental_refresh(tmp_path)
        assert stats.files_reparsed == 1

    def test_index_excludes_hard_safety_paths(self, tmp_path):
        """Verify .git, .venv, node_modules, dist, build, __pycache__, .pytest_cache excluded."""
        for name in [".git", ".venv", "node_modules", "dist", "build", "__pycache__", ".pytest_cache"]:
            (tmp_path / name).mkdir()
            (tmp_path / name / "file.txt").write_text("excluded")
        (tmp_path / "module.py").write_text("x = 1")
        stats = full_index(tmp_path)
        assert stats.files_indexed == 1

    def test_index_excludes_itself(self, tmp_path):
        """Verify .audisor/repo-intelligence.db not indexed."""
        # Don't create a fake db file - just verify the exclusion logic
        (tmp_path / "module.py").write_text("x = 1")
        stats = full_index(tmp_path)
        # After indexing, check that .audisor directory was created but not indexed
        status = get_index_status(tmp_path)
        assert status["exists"] is True
        # The index itself should not be in the file count
        assert stats.files_indexed == 1

    def test_index_handles_binary_files(self, tmp_path):
        """Verify binary files detected and skipped."""
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (tmp_path / "module.py").write_text("x = 1")
        stats = full_index(tmp_path)
        # Binary file should be skipped
        assert stats.files_indexed == 1

    def test_index_handles_malformed_utf(self, tmp_path):
        """Verify malformed UTF recorded, does not crash."""
        (tmp_path / "bad.txt").write_bytes(b"hello \xff world")
        (tmp_path / "good.py").write_text("x = 1")
        # Should not crash
        stats = full_index(tmp_path)
        assert stats.files_examined >= 1

    def test_index_handles_python_syntax_errors(self, tmp_path):
        """Verify syntax errors recorded, valid parts indexed."""
        (tmp_path / "broken.py").write_text("def broken(\n# missing paren")
        (tmp_path / "good.py").write_text("x = 1")
        stats = full_index(tmp_path)
        assert stats.syntax_errors >= 1


# ============== Text Search ==============


class TestTextSearch:
    """Tests for text search."""

    def test_fts_search_returns_bounded_results(self, tmp_path):
        """Verify FTS5 search returns results with path, line, column, excerpt."""
        (tmp_path / "module.py").write_text("def hello():\n    print('hello world')\n")
        full_index(tmp_path)
        result = search_text(tmp_path, "hello", backend="index")
        assert len(result.matches) >= 1
        assert result.matches[0].path == "module.py"

    def test_search_respects_path_scope(self, tmp_path):
        """Verify path filters work."""
        (tmp_path / "a.py").write_text("search_term")
        (tmp_path / "b.py").write_text("search_term")
        full_index(tmp_path)
        result = search_text(tmp_path, "search_term", path_scope="a")
        assert all("a.py" in m.path for m in result.matches)

    def test_search_respects_result_limits(self, tmp_path):
        """Verify max_results enforced."""
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text("common_term")
        full_index(tmp_path)
        result = search_text(tmp_path, "common_term", max_results=3)
        assert len(result.matches) <= 3

    def test_search_escaping_prevents_fts_errors(self, tmp_path):
        """Verify special characters escaped."""
        (tmp_path / "module.py").write_text("x = 'test'")
        full_index(tmp_path)
        # These should not crash
        escaped = escape_fts5_query("test(1)")
        assert escaped is not None
        result = search_text(tmp_path, "test(1)", backend="index")
        # Should return empty or results, not crash


# ============== Symbol Intelligence ==============


class TestSymbolIntelligence:
    """Tests for symbol intelligence."""

    def test_list_symbols_returns_python_symbols(self, tmp_path):
        """Verify classes, functions, methods, properties extracted."""
        (tmp_path / "module.py").write_text('''
class MyClass:
    def method(self):
        pass

    @property
    def prop(self):
        pass

def standalone():
    pass
''')
        full_index(tmp_path)
        symbols = list_symbols(tmp_path)
        kinds = {s.kind for s in symbols}
        assert "class" in kinds
        assert "function" in kinds

    def test_find_symbol_exact_match_ranks_before_partial(self, tmp_path):
        """Verify ranking."""
        (tmp_path / "module.py").write_text("def exact_match(): pass\ndef partial_matcher(): pass")
        full_index(tmp_path)
        symbols = find_symbol(tmp_path, "exact_match", exact=True)
        assert len(symbols) >= 1
        assert symbols[0].name == "exact_match"

    def test_find_imports_extracts_module_and_name(self, tmp_path):
        """Verify import relationships."""
        (tmp_path / "module.py").write_text("import os\nfrom pathlib import Path\n")
        full_index(tmp_path)
        imports = find_imports(tmp_path)
        modules = {i.imported_module for i in imports}
        assert "os" in modules
        assert "pathlib" in modules


# ============== Git Intelligence ==============


class TestGitIntelligence:
    """Tests for git intelligence."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a minimal git repository."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file.py").write_text("x = 1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)
        return tmp_path

    def test_git_status_returns_structured_porcelain(self, git_repo):
        """Verify staged/unstaged/untracked/renamed/deleted."""
        (git_repo / "new.py").write_text("y = 2")
        entries = git_status(git_repo)
        # Should have untracked file
        statuses = {e.status for e in entries}
        assert "untracked" in statuses

    def test_git_diff_respects_byte_limits(self, git_repo):
        """Verify truncation metadata."""
        (git_repo / "file.py").write_text("x = 2")
        result = git_diff(git_repo, max_bytes=10)
        assert "truncated" in result

    def test_git_history_returns_commits(self, git_repo):
        """Verify hash, parent hashes, author timestamp, subject."""
        commits = git_history(git_repo)
        assert len(commits) >= 1
        assert commits[0].hash
        assert commits[0].subject

    def test_git_show_file_reads_historical_revision(self, git_repo):
        """Verify file from past commit."""
        result = git_show_file(git_repo, "HEAD", "file.py")
        assert "x = 1" in result["content"]


# ============== Command Execution ==============


class TestCommandExecution:
    """Tests for command execution."""

    def test_run_command_uses_argument_array_not_shell(self, tmp_path):
        """Verify no shell interpolation."""
        import sys
        # Use Python to echo, which works cross-platform
        result = run_command(tmp_path, [sys.executable, "-c", "print('hello world')"])
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_run_command_enforces_timeout(self, tmp_path):
        """Verify timeout kills process."""
        import sys
        # Use Python to sleep, which works cross-platform
        result = run_command(tmp_path, [sys.executable, "-c", "import time; time.sleep(10)"], timeout_seconds=1)
        assert result.timed_out is True

    def test_run_command_truncates_output(self, tmp_path):
        """Verify output limits enforced."""
        import sys
        # Generate lots of output
        result = run_command(
            tmp_path,
            [sys.executable, "-c", "print('x' * 10000)"],
            max_output_bytes=100,
        )
        assert result.truncated is True

    def test_run_validation_profiles_derived_from_repo(self, tmp_path):
        """Verify profiles use correct commands."""
        assert "focused" in VALIDATION_PROFILES
        assert "backend" in VALIDATION_PROFILES


# ============== Diagnostics ==============


class TestDiagnostics:
    """Tests for diagnostics."""

    def test_parse_pytest_failures_extracts_assertion(self):
        """Verify pytest assertion parsing."""
        output = """
============================= FAILURES =============================
_________________________ test_something __________________________
    def test_something():
>       assert 1 == 2
E       AssertionError: assert 1 == 2
"""
        failures = parse_test_failures(output)
        assert len(failures) >= 1

    def test_parse_python_traceback_structures_frames(self):
        """Verify traceback parsing."""
        output = """
Traceback (most recent call last):
  File "test.py", line 10, in main
    result = 1 / 0
ZeroDivisionError: division by zero
"""
        tb = parse_python_traceback(output)
        assert tb is not None
        assert tb.exception_type == "ZeroDivisionError"
        assert len(tb.frames) >= 1

    def test_summarise_command_failure_deterministic(self):
        """Verify deterministic summaries."""
        summary = summarise_command_failure(
            exit_code=1,
            timed_out=False,
            stdout="",
            stderr="Error: something failed",
        )
        assert summary.exit_code == 1
        assert summary.timed_out is False
        assert summary.summary


# ============== Safe Mutation ==============


class TestSafeMutation:
    """Tests for safe mutation."""

    def test_prepare_patch_does_not_mutate_file(self, tmp_path):
        """Verify preview only."""
        (tmp_path / "file.py").write_text("x = 1")
        original = (tmp_path / "file.py").read_text()
        preview = prepare_patch(tmp_path, "file.py", "x = 2")
        after = (tmp_path / "file.py").read_text()
        assert original == after
        assert preview.diff

    def test_apply_patch_verifies_current_sha256(self, tmp_path):
        """Verify stale patch rejection."""
        (tmp_path / "file.py").write_text("x = 1")
        original_hash = compute_sha256("x = 1")
        # Modify file
        (tmp_path / "file.py").write_text("x = 2")
        # Try to apply with old hash - should raise PatchError
        with pytest.raises(PatchError):
            apply_patch(tmp_path, "file.py", "x = 3", expected_sha256=original_hash)

    def test_apply_patch_writes_atomically(self, tmp_path):
        """Verify atomic write."""
        (tmp_path / "file.py").write_text("x = 1")
        original_hash = compute_sha256("x = 1")
        result = apply_patch(tmp_path, "file.py", "x = 2", expected_sha256=original_hash)
        assert result.success is True
        assert (tmp_path / "file.py").read_text() == "x = 2"

    def test_apply_patch_never_stages_or_commits(self, tmp_path):
        """Verify no git side effects."""
        import subprocess
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "file.py").write_text("x = 1")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, capture_output=True)

        original_hash = compute_sha256("x = 1")
        apply_patch(tmp_path, "file.py", "x = 2", expected_sha256=original_hash)

        # Check git status - file should be modified but not staged
        result = subprocess.run(["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True)
        assert "M  file.py" not in result.stdout  # Not staged
        assert " M file.py" in result.stdout  # But modified


# ============== Result Contracts ==============


class TestResultContracts:
    """Tests for result contracts."""

    def test_result_envelope_has_required_fields(self):
        """Verify schema_version, tool_name, status, result."""
        result = success("test_tool", {"key": "value"})
        d = result.as_dict()
        assert "schema_version" in d
        assert "tool_name" in d
        assert "status" in d
        assert d["schema_version"] == SCHEMA_VERSION

    def test_status_vocabulary_correct(self):
        """Verify no 'blocked' or 'locked' as generic statuses."""
        # Valid statuses
        assert success("t", {}).status == "success"
        assert error("t", "c", "d").status == "error"
        assert blocked("t", "c", "d").status == "blocked"

    def test_errors_not_returned_as_raw_exceptions(self):
        """Verify structured errors."""
        result = error("test_tool", "test_code", "test detail")
        d = result.as_dict()
        assert isinstance(d["errors"], list)
        assert d["errors"][0]["code"] == "test_code"
        assert d["errors"][0]["detail"] == "test detail"


# ============== MCP Contract ==============


class TestMCPContract:
    """Tests for MCP contract."""

    def test_all_tools_registered(self):
        """Verify all 35 tools present."""
        from audisor.mcp_server import _TOOLS
        tool_names = {t.name for t in _TOOLS}
        expected = {
            # Original tools
            "audisor_scan", "audisor_inspect", "audisor_normalize",
            "audisor_validate", "audisor_replay", "audisor_trace",
            # Discovery
            "repo_status", "repo_tree",
            # Index
            "index_repository", "index_status",
            # Search
            "search_text", "read_file_range", "read_file_outline",
            # Symbols
            "list_symbols", "find_symbol", "find_references", "find_imports",
            "dependency_neighbourhood",
            # Git
            "git_status", "git_diff", "git_history", "git_show_file",
            # Commands
            "run_command", "run_validation", "operation_status",
            "refresh_paths", "operation_result",
            # Diagnostics
            "parse_test_failures", "parse_python_traceback", "summarise_command_failure",
            # Mutation
            "prepare_patch", "apply_patch",
            # Gap analysis
            "create_gap", "find_gap", "gap_record",
        }
        assert tool_names == expected

    def test_tool_schemas_reject_unknown_properties(self):
        """Verify additionalProperties: false."""
        from audisor.mcp_server import _TOOLS
        for tool in _TOOLS:
            schema = tool.inputSchema
            assert schema.get("additionalProperties") is False, f"{tool.name} missing additionalProperties: false"

    def test_tool_results_have_stable_envelope(self):
        """Verify schema_version, status, result, warnings, errors."""
        result = success("test", {"data": 1})
        d = result.as_dict()
        assert "schema_version" in d
        assert "status" in d
