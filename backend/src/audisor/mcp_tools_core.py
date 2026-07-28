"""Tool definitions: original Audisor plus discovery, index, search, symbols."""

from __future__ import annotations

import mcp.types as types

from .mcp_schemas import strict_schema as _schema

CORE_TOOLS: list[types.Tool] = [
    # Original Audisor tools
    types.Tool(
        name="audisor_scan",
        description="Create a deterministic ScanReport for a repository without modifying it.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "baseline": {"type": ["string", "null"]},
            },
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="audisor_inspect",
        description="Create immutable original-issue evidence and a safe source snapshot.",
        inputSchema=_schema(
            {
                "inspection_id": {"type": "string"},
                "repository_root": {"type": "string"},
                "issue": {"type": "string"},
                "baseline": {"type": ["string", "null"]},
            },
            ["inspection_id", "repository_root", "issue"],
        ),
    ),
    types.Tool(
        name="audisor_normalize",
        description="Create a no-snapshot Normalize Package from Inspection, Dossier, Handoff, and an LLM Statement.",
        inputSchema=_schema(
            {
                "inspection": {"type": "object"},
                "llm_statement": {"type": "object"},
            },
            ["inspection", "llm_statement"],
        ),
    ),
    types.Tool(
        name="audisor_validate",
        description="Hash-lock inspection evidence and validate a complete Gap Evaluation before repair.",
        inputSchema=_schema(
            {
                "inspection": {"type": "object"},
                "evaluation": {"type": "object"},
            },
            ["inspection", "evaluation"],
        ),
    ),
    types.Tool(
        name="audisor_replay",
        description="Compare original evidence with current source after Codex repairs it.",
        inputSchema=_schema(
            {
                "inspection": {"type": "object"},
                "validation": {"type": "object"},
            },
            ["inspection", "validation"],
        ),
    ),
    types.Tool(
        name="audisor_trace",
        description="Trace static parents, entrypoints, and direct tests from immutable inspection evidence.",
        inputSchema=_schema(
            {"inspection": {"type": "object"}},
            ["inspection"],
        ),
    ),
    # Repository Intelligence - Discovery
    types.Tool(
        name="repo_status",
        description="Get repository status including branch, HEAD, dirty state, and index status.",
        inputSchema=_schema(
            {"repository_root": {"type": "string"}},
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="repo_tree",
        description="Get a bounded tree view of the repository structure.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "max_depth": {"type": "integer"},
                "max_entries": {"type": "integer"},
            },
            ["repository_root"],
        ),
    ),
    # Repository Intelligence - Index
    types.Tool(
        name="index_repository",
        description="Build or refresh the repository index for fast searching.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "incremental": {"type": "boolean"},
                "paths": {"type": "array", "items": {"type": "string"}},
            },
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="index_status",
        description="Get the current status of the repository index.",
        inputSchema=_schema(
            {"repository_root": {"type": "string"}},
            ["repository_root"],
        ),
    ),
    # Repository Intelligence - Search
    types.Tool(
        name="search_text",
        description="Search for text in repository files using FTS5 index or ripgrep.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "query": {"type": "string"},
                "backend": {"type": "string", "enum": ["auto", "index", "ripgrep"]},
                "path_scope": {"type": "string"},
                "language": {"type": "string"},
                "max_results": {"type": "integer"},
                "is_regex": {"type": "boolean"},
            },
            ["repository_root", "query"],
        ),
    ),
    types.Tool(
        name="read_file_range",
        description="Read a specific range of lines from a file.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            ["repository_root", "path"],
        ),
    ),
    types.Tool(
        name="read_file_outline",
        description="Read the structural outline of a file (imports, classes, functions).",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "path": {"type": "string"},
            },
            ["repository_root", "path"],
        ),
    ),
    # Repository Intelligence - Symbols
    types.Tool(
        name="list_symbols",
        description="List Python symbols in the repository.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "kind": {"type": "string", "enum": ["class", "function", "method", "property", "variable"]},
                "path_prefix": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="find_symbol",
        description="Find symbols by name with optional exact match.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "name": {"type": "string"},
                "exact": {"type": "boolean"},
                "kind": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            ["repository_root", "name"],
        ),
    ),
    types.Tool(
        name="find_references",
        description="Find references to a symbol with confidence classification.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "symbol_name": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            ["repository_root", "symbol_name"],
        ),
    ),
    types.Tool(
        name="find_imports",
        description="Find import relationships in the repository.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "path": {"type": "string"},
                "module": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            ["repository_root"],
        ),
    ),
    types.Tool(
        name="dependency_neighbourhood",
        description="Find the dependency neighbourhood of a module.",
        inputSchema=_schema(
            {
                "repository_root": {"type": "string"},
                "module": {"type": "string"},
                "depth": {"type": "integer"},
                "max_results": {"type": "integer"},
            },
            ["repository_root", "module"],
        ),
    ),
]
