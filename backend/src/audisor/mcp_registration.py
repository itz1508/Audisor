"""Tool registration and dispatch assembly for the Audisor MCP server."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mcp.types as types

from .mcp_dispatch_core import (
    dispatch_audisor,
    dispatch_discovery,
    dispatch_search,
    dispatch_symbol_lookup,
    dispatch_symbol_relations,
)
from .mcp_dispatch_ops import (
    dispatch_commands,
    dispatch_diagnostics,
    dispatch_gap,
    dispatch_git,
    dispatch_mutation,
    dispatch_operations,
)
from .mcp_schemas import blocked_payload
from .mcp_tools_core import CORE_TOOLS
from .mcp_tools_ops import OPS_TOOLS

TOOLS: list[types.Tool] = CORE_TOOLS + OPS_TOOLS

TOOL_INDEX: dict[str, types.Tool] = {tool.name: tool for tool in TOOLS}


def dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call to the matching category handler."""
    result = dispatch_audisor(name, arguments)
    if result is not None:
        return result
    result = dispatch_gap(name, arguments)
    if result is not None:
        return result
    result = dispatch_diagnostics(name, arguments)
    if result is not None:
        return result

    root = Path(arguments.get("repository_root", "")) if "repository_root" in arguments else None
    for handler in (
        dispatch_discovery,
        dispatch_search,
        dispatch_symbol_lookup,
        dispatch_symbol_relations,
        dispatch_git,
        dispatch_commands,
        dispatch_operations,
        dispatch_mutation,
    ):
        result = handler(name, root, arguments)
        if result is not None:
            return result
    return blocked_payload("invalid_request", f"Unknown tool: {name}")
