from __future__ import annotations

import json
from typing import Any

from importlib.metadata import version

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from .artifacts import ArtifactError
from .contracts import ContractError, InspectionRequest
from .inspection import inspect_repository
from .normalization import normalize_inspection
from .replay import replay_inspection
from .scanner import scan_report
from .trace import trace_inspection
from .validation import validate_inspection

_INSTRUCTIONS = (
    "Read-only issue inspection, validation, and replay tools. "
    "Codex remains the only repair writer."
)


def _error(code: str, detail: str) -> dict[str, Any]:
    return {"status": "blocked", "error": {"code": code, "detail": detail}}


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    """Build a strict JSON Schema that rejects unknown properties.

    The low-level MCP server validates call arguments against this schema with
    jsonschema; ``additionalProperties: False`` makes unknown properties a
    validation error instead of being silently dropped.
    """
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


_TOOLS: list[types.Tool] = [
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
]

_TOOL_INDEX = {tool.name: tool for tool in _TOOLS}


def _dispatch(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "audisor_scan":
        from pathlib import Path

        root = Path(arguments["repository_root"])
        if not root.is_dir():
            return _error("repository_not_found", arguments["repository_root"])
        return scan_report(root, baseline=arguments.get("baseline")).as_dict()
    if name == "audisor_inspect":
        try:
            request = InspectionRequest.from_mapping(
                {
                    "inspection_id": arguments["inspection_id"],
                    "repository_root": arguments["repository_root"],
                    "issue": arguments["issue"],
                    "baseline": arguments.get("baseline"),
                }
            )
            return inspect_repository(request)
        except (ArtifactError, ContractError, ValueError) as exc:
            return _error("invalid_inspection_request", str(exc))
    if name == "audisor_normalize":
        try:
            return normalize_inspection(arguments["inspection"], arguments["llm_statement"])
        except (ArtifactError, ValueError) as exc:
            return _error("normalization_blocked", str(exc))
    if name == "audisor_validate":
        try:
            return validate_inspection(arguments["inspection"], arguments["evaluation"])
        except (ArtifactError, ValueError) as exc:
            return _error("validation_blocked", str(exc))
    if name == "audisor_replay":
        try:
            return replay_inspection(arguments["inspection"], arguments["validation"])
        except (ArtifactError, ValueError) as exc:
            return _error("replay_blocked", str(exc))
    if name == "audisor_trace":
        try:
            return trace_inspection(arguments["inspection"])
        except ArtifactError as exc:
            return _error("trace_blocked", str(exc))
    return _error("unknown_tool", name)


def create_server() -> Server:
    server: Server = Server("Audisor", version=version("audisor-local"), instructions=_INSTRUCTIONS)

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return _TOOLS

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
        payload = _dispatch(name, arguments or {})
        return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=True, sort_keys=True))]

    return server


def main() -> None:
    import anyio

    server = create_server()

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(_run)
