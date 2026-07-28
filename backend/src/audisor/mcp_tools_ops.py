"""Tool definitions: git, commands, diagnostics, mutation, and gap analysis."""

from __future__ import annotations

import mcp.types as types

from .mcp_schemas import strict_schema as _schema

OPS_TOOLS: list[types.Tool] = [
    # Repository Intelligence - Git
    types.Tool(
        name="git_status",
        description="Get structured git status with staged/unstaged/untracked files.",
        inputSchema=_schema(
            {"repository_root": {"type": "string"}},
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="git_diff",
        description="Get git diff with optional path and staging filters.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "path": {"type": "string"},
                "staged": {"type": "boolean"},
            },
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="git_history",
        description="Get git commit history.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "path": {"type": "string"},
                "max_commits": {"type": "integer"},
            },
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="git_show_file",
        description="Get file content from a historical revision.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "revision": {"type": "string"},
                "path": {"type": "string"},
            },
            ["repository_root", "revision", "path"],
        ),
    ),
    # Repository Intelligence - Commands
    types.Tool(
        name="run_command",
        description="Execute a command with timeout and output limits.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "command": {"type": "array", "items": {"type": "string"}},
                "timeout_seconds": {"type": "integer"},
                "working_directory": {"type": "string"},
            },
            ["repository_root", "command"],
        ),
    ),
    types.Tool(
        name="run_validation",
        description="Run a validation profile (focused, runtime, backend, aflow, scripts, fixtures, size, build, compile).",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "profile": {"type": "string"},
                "path": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
            ["repository_root", "profile"],
        ),
    ),
    types.Tool(
        name="operation_status",
        description="Get the status of a long-running operation.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "operation_id": {"type": "string"},
            },
            ["repository_root", "operation_id"],
        ),
    ),
    types.Tool(
        name="refresh_paths",
        description="Refresh specific paths in the index (incremental update).",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
            ["repository_root", "paths"],
        ),
    ),
    types.Tool(
        name="operation_result",
        description="Get the result of a completed operation.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "operation_id": {"type": "string"},
            },
            ["repository_root", "operation_id"],
        ),
    ),
    # Repository Intelligence - Diagnostics
    types.Tool(
        name="parse_test_failures",
        description="Parse pytest output for failures.",
        inputSchema=_schema(
            {"output": {"type": "string"}},
            ["output"],
        ),
    ),
    types.Tool(
        name="parse_python_traceback",
        description="Parse a Python traceback.",
        inputSchema=_schema(
            {"output": {"type": "string"}},
            ["output"],
        ),
    ),
    types.Tool(
        name="summarise_command_failure",
        description="Create a deterministic failure summary.",
        inputSchema=_schema(
            {
                "exit_code": {"type": "integer"},
                "timed_out": {"type": "boolean"},
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
            },
            ["exit_code", "timed_out", "stdout", "stderr"],
        ),
    ),
    # Repository Intelligence - Mutation
    types.Tool(
        name="prepare_patch",
        description="Prepare a patch without applying it (preview only).",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "path": {"type": "string"},
                "new_content": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            ["repository_root", "path", "new_content"],
        ),
    ),
    types.Tool(
        name="apply_patch",
        description="Apply a patch to a file after hash verification.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "path": {"type": "string"},
                "new_content": {"type": "string"},
                "expected_sha256": {"type": "string"},
                "patch_id": {"type": "string"},
            },
            ["repository_root", "path", "new_content", "expected_sha256"],
        ),
    ),
    # Gap analysis tools
    types.Tool(
        name="create_gap",
        description="Create a gap analysis plan for a task, plan, or operation.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "task_id": {"type": ["string", "null"]},
                "plan_id": {"type": ["string", "null"]},
                "operation_id": {"type": ["string", "null"]},
                "trigger_type": {"type": "string"},
            },
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="find_gap",
        description="Perform read-only evidence-based gap analysis.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "trigger_type": {"type": "string"},
                "trigger_level": {"type": "string"},
                "task_id": {"type": ["string", "null"]},
                "plan_id": {"type": ["string", "null"]},
                "operation_id": {"type": ["string", "null"]},
                "changed_paths": {"type": "array", "items": {"type": "string"}},
                "success_definition": {"type": ["string", "null"]},
            },
            ["repository_root", "trigger_type", "trigger_level"],
        ),
    ),
    types.Tool(
        name="gap_record",
        description="Persist a gap analysis record.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "gap_run_id": {"type": "string"},
                "task_id": {"type": ["string", "null"]},
                "plan_id": {"type": ["string", "null"]},
                "operation_id": {"type": ["string", "null"]},
                "trigger_type": {"type": "string"},
                "trigger_digest": {"type": "string"},
                "trigger_level": {"type": "string"},
                "repository_state": {"type": "object"},
                "changed_paths": {"type": "array", "items": {"type": "string"}},
                "path_hashes": {"type": "object"},
                "findings": {"type": "array", "items": {"type": "object"}},
                "no_material_gap": {"type": "boolean"},
                "previous_run_id": {"type": ["string", "null"]},
                "final_result": {"type": "string"},
            },
            ["repository_root", "gap_run_id", "trigger_type", "trigger_digest", "trigger_level"],
        ),
    ),
]
